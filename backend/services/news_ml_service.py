import os
import asyncio
import logging
import copy
from datetime import datetime
from typing import List, Dict, Any, Optional

import numpy as np
import requests
try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except Exception:
    xgb = None
    XGBOOST_AVAILABLE = False
from google import genai
from sklearn.linear_model import LinearRegression
try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except Exception:
    TextBlob = None
    TEXTBLOB_AVAILABLE = False
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
except Exception:
    SentimentIntensityAnalyzer = None
    VADER_AVAILABLE = False

from backend.config.secure_config import config_manager
from backend.services.memory_service import memory_service

logger = logging.getLogger(__name__)


class NewsMLService:
    def __init__(self):
        self.vader = SentimentIntensityAnalyzer() if VADER_AVAILABLE and SentimentIntensityAnalyzer is not None else None

        # Secure config first, then plain env fallbacks.
        self.news_api_key = config_manager.get_api_key("news") or os.getenv("NEWS_API_KEY")
        self.alpha_vantage_key = config_manager.get_api_key("alpha_vantage") or os.getenv("ALPHA_VANTAGE_API_KEY")

        self.newsapi_url = "https://newsapi.org/v2/top-headlines"
        self.alpha_vantage_url = "https://www.alphavantage.co/query"
        self.request_timeout_sec = float(os.getenv("NEWS_PROVIDER_TIMEOUT_SEC", "8"))
        self.max_headlines = int(os.getenv("NEWS_PROVIDER_LIMIT", "10"))
        # Keep first-load latency bounded: generate AI insights for top N headlines only.
        self.gemini_timeout_sec = float(os.getenv("NEWS_GEMINI_TIMEOUT_SEC", "2.2"))
        self.max_ai_insights = int(os.getenv("NEWS_AI_INSIGHT_LIMIT", "2"))
        self.cache_ttl_sec = int(os.getenv("NEWS_CACHE_TTL_SEC", "120"))
        self._cached_news: List[Dict[str, Any]] = []
        self._cached_at: Optional[datetime] = None
        self._cached_benchmark_ticker: Optional[str] = None
        self._cached_interval: Optional[str] = None
        self._inflight_task: Optional[asyncio.Task] = None
        self._inflight_key: Optional[str] = None

        # Configure Gemini API
        gemini_key = config_manager.get_api_key("gemini") or os.getenv("GEMINI_API_KEY")
        self.ai_client = genai.Client(api_key=gemini_key) if gemini_key else None
        self._gemini_disabled = False
        self.runtime_status: Dict[str, Any] = {
            "last_fetch_at": None,
            "last_provider": None,
            "last_mode": "uninitialized",
            "last_live_count": 0,
            "last_error": None,
            "last_duration_ms": 0.0,
            "gemini_disabled": False,
            "gemini_available": self.ai_client is not None,
            "xgboost_available": XGBOOST_AVAILABLE,
            "textblob_available": TEXTBLOB_AVAILABLE,
            "vader_available": VADER_AVAILABLE,
            "cache_hit": False,
        }

        # Initialize Base Models
        self._init_models()

    def _init_models(self):
        """
        Initialize the XGBoost and Linear Regression models.
        In production, these can be loaded from persisted model artifacts.
        """
        self.lr_model = LinearRegression()
        self.xgb_model = None
        if XGBOOST_AVAILABLE and xgb is not None:
            self.xgb_model = xgb.XGBRegressor(
                objective="reg:squarederror",
                n_estimators=100,
                learning_rate=0.1,
                max_depth=4
            )

        # Features: [Vader Compound, TextBlob Polarity, Keyword Severity, Volatility Proxy]
        X_train = np.array([
            [0.8, 0.7, 0.1, 0.2],   # Good news, low severity
            [-0.9, -0.8, 0.9, 0.8], # War/Crisis, high severity
            [0.1, 0.0, 0.2, 0.5],   # Neutral/Mixed
            [-0.5, -0.3, 0.6, 0.7], # Bad earnings, medium severity
            [0.6, 0.5, 0.3, 0.4]    # Economic growth
        ])
        y_train = np.array([20, 95, 15, 65, 30])

        self.lr_model.fit(X_train, y_train)
        if self.xgb_model is not None:
            self.xgb_model.fit(X_train, y_train)

    def _synthetic_news_fallback(self) -> List[Dict[str, Any]]:
        """Fallback sample feed used only when live providers are unavailable."""
        return [
            {
                "title": "Escalation in Eastern Europe: Artillery Strikes Reported Near Border",
                "description": "Tensions soar as reports of heavy artillery strikes hit the border region, prompting emergency UN meetings and a spike in crude oil prices.",
                "source": {"name": "Global Defense Monitor"},
                "publishedAt": datetime.utcnow().isoformat() + "Z",
                "url": "#"
            },
            {
                "title": "Federal Reserve Signals Aggressive Rate Cuts Amid Slowing Economy",
                "description": "The central bank unexpectedly indicated that multiple rate cuts are on the table for the next quarter to stimulate borrowing and investment.",
                "source": {"name": "Financial Times"},
                "publishedAt": datetime.utcnow().isoformat() + "Z",
                "url": "#"
            },
            {
                "title": "Tech Giant Unveils Revolutionary Quantum Processor",
                "description": "A major breakthrough in quantum computing was announced today, potentially rendering current encryption methods obsolete within a decade.",
                "source": {"name": "TechCrunch"},
                "publishedAt": datetime.utcnow().isoformat() + "Z",
                "url": "#"
            },
            {
                "title": "Global Supply Chain Disruptions: Major Shipping Route Blocked",
                "description": "A massive cargo ship has run aground, completely blocking a critical shipping lane. Analysts warn of severe supply shortages if not cleared quickly.",
                "source": {"name": "Reuters"},
                "publishedAt": datetime.utcnow().isoformat() + "Z",
                "url": "#"
            }
        ]

    def _normalize_newsapi_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "title": article.get("title"),
            "description": article.get("description") or article.get("content", ""),
            "source": {"name": (article.get("source") or {}).get("name", "NewsAPI")},
            "publishedAt": article.get("publishedAt") or datetime.utcnow().isoformat() + "Z",
            "url": article.get("url")
        }

    def _normalize_alpha_published_at(self, raw: Any) -> str:
        """
        Alpha Vantage uses `YYYYMMDDTHHMMSS` for `time_published`.
        Normalize to ISO8601 UTC string to avoid frontend date-parse crashes.
        """
        if not raw:
            return datetime.utcnow().isoformat() + "Z"
        raw_str = str(raw).strip()
        try:
            if len(raw_str) == 15 and raw_str[8] == "T":
                dt = datetime.strptime(raw_str, "%Y%m%dT%H%M%S")
                return dt.isoformat() + "Z"
            if len(raw_str) == 16 and raw_str.endswith("Z") and raw_str[8] == "T":
                dt = datetime.strptime(raw_str, "%Y%m%dT%H%M%SZ")
                return dt.isoformat() + "Z"
            parsed = datetime.fromisoformat(raw_str.replace("Z", "+00:00"))
            return parsed.isoformat().replace("+00:00", "Z")
        except Exception:
            return datetime.utcnow().isoformat() + "Z"

    def _normalize_alpha_vantage_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "title": article.get("title"),
            "description": article.get("summary", ""),
            "source": {"name": article.get("source", "AlphaVantage")},
            "publishedAt": self._normalize_alpha_published_at(article.get("time_published")),
            "url": article.get("url")
        }

    def _fetch_from_newsapi(self, limit: int) -> List[Dict[str, Any]]:
        if not self.news_api_key:
            return []

        params = {
            "apiKey": self.news_api_key,
            "country": os.getenv("NEWSAPI_COUNTRY", "us"),
            "category": "business",
            "pageSize": max(1, min(limit, 50))
        }

        response = requests.get(self.newsapi_url, params=params, timeout=self.request_timeout_sec)
        response.raise_for_status()
        payload = response.json()

        if payload.get("status") != "ok":
            raise RuntimeError(f"NewsAPI returned non-ok status: {payload.get('status')}")

        articles = payload.get("articles", [])
        normalized = [
            self._normalize_newsapi_article(a)
            for a in articles
            if (a or {}).get("title")
        ]
        return normalized[:limit]

    def _fetch_from_alpha_vantage(self, limit: int) -> List[Dict[str, Any]]:
        if not self.alpha_vantage_key:
            return []

        params = {
            "function": "NEWS_SENTIMENT",
            "topics": "financial_markets,economy_macro,finance",
            "sort": "LATEST",
            "limit": max(1, min(limit, 50)),
            "apikey": self.alpha_vantage_key
        }

        response = requests.get(self.alpha_vantage_url, params=params, timeout=self.request_timeout_sec)
        response.raise_for_status()
        payload = response.json()
        feed = payload.get("feed", [])

        normalized = [
            self._normalize_alpha_vantage_article(item)
            for item in feed
            if (item or {}).get("title")
        ]
        return normalized[:limit]

    def _fetch_live_news(self, limit: int) -> List[Dict[str, Any]]:
        """Try NewsAPI first, then Alpha Vantage, return empty list if both fail."""
        if self.news_api_key:
            try:
                news = self._fetch_from_newsapi(limit)
                if news:
                    logger.info("Loaded %d live headlines from NewsAPI.", len(news))
                    self.runtime_status["last_provider"] = "newsapi"
                    self.runtime_status["last_live_count"] = len(news)
                    return news
            except Exception as e:
                logger.warning("NewsAPI fetch failed: %s", e)
                self.runtime_status["last_error"] = f"NewsAPI: {e}"

        if self.alpha_vantage_key:
            try:
                news = self._fetch_from_alpha_vantage(limit)
                if news:
                    logger.info("Loaded %d live headlines from Alpha Vantage.", len(news))
                    self.runtime_status["last_provider"] = "alpha_vantage"
                    self.runtime_status["last_live_count"] = len(news)
                    return news
            except Exception as e:
                logger.warning("Alpha Vantage news fetch failed: %s", e)
                self.runtime_status["last_error"] = f"AlphaVantage: {e}"

        return []

    def _calculate_keyword_severity(self, text: str) -> float:
        """Assign a severity score based on high-impact geopolitical/financial keywords."""
        text = text.lower()

        tier_1 = ["war", "missile", "strike", "invasion", "crash", "collapse", "bankruptcy", "pandemic", "emergency", "nuclear"]
        tier_2 = ["sanctions", "inflation", "recession", "hike", "tariffs", "shortage", "escalate"]
        tier_3 = ["earnings", "merger", "acquisition", "guidance", "agreement"]

        for word in tier_1:
            if word in text:
                return 1.0
        for word in tier_2:
            if word in text:
                return 0.6
        for word in tier_3:
            if word in text:
                return 0.2
        return 0.0

    def analyze_news_item(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """Run a single news article through the NLP and Ensemble ML pipeline."""
        text = f"{article.get('title', '')} {article.get('description', '')}"

        # 1. NLP Feature Extraction
        vader_scores = self.vader.polarity_scores(text) if self.vader is not None else {"compound": 0.0}
        tb_polarity = TextBlob(text).sentiment.polarity if TEXTBLOB_AVAILABLE and TextBlob is not None else 0.0
        severity = self._calculate_keyword_severity(text)

        volatility_base = 0.5
        features = np.array([[
            vader_scores["compound"],
            tb_polarity,
            severity,
            volatility_base
        ]])

        # 2. ML Ensemble Prediction
        try:
            lr_pred = self.lr_model.predict(features)[0]
            if self.xgb_model is not None:
                xgb_pred = self.xgb_model.predict(features)[0]
                xgb_weight = 0.7 if severity >= 0.6 else 0.4
                lr_weight = 1.0 - xgb_weight
                affect_rate = (xgb_pred * xgb_weight) + (lr_pred * lr_weight)
            else:
                xgb_pred = lr_pred
                affect_rate = lr_pred
        except Exception as ml_err:
            logger.warning("ML models failed: %s. Falling back to rule-based scoring.", ml_err)
            affect_rate = (severity * 85) + (abs(vader_scores["compound"]) * 15)
            lr_pred = affect_rate * 0.9
            xgb_pred = affect_rate * 1.1

        affect_rate = float(np.clip(affect_rate, 0, 100))

        direction = (
            "BEARISH" if vader_scores["compound"] < -0.2
            else ("BULLISH" if vader_scores["compound"] > 0.2 else "NEUTRAL")
        )
        if severity >= 0.8 and vader_scores["compound"] < 0:
            direction = "CRASH_WARNING"

        return {
            "title": article.get("title"),
            "source": article.get("source", {}).get("name", "Unknown"),
            "published_at": article.get("publishedAt"),
            "url": article.get("url"),
            "assistant_insight": "Analyzing...",
            "nlp_metrics": {
                "vader_compound": round(vader_scores["compound"], 3),
                "textblob_polarity": round(tb_polarity, 3),
                "keyword_severity": severity
            },
            "ml_votes": {
                "xgboost_score": round(float(xgb_pred), 1),
                "linear_reg_score": round(float(lr_pred), 1)
            },
            "affect_rate": round(affect_rate, 1),
            "market_direction": direction
        }

    async def _generate_quick_insight_async(self, title: str, affect_rate: float, direction: str) -> str:
        """Async query Gemini to get an insight."""
        if self.ai_client is None or self._gemini_disabled:
            return "AI Analysis unavailable: missing API key or quota exhausted."

        try:
            prompt = (
                "As a professional market analyst assistant, provide a 1-sentence concise insight "
                f"on what this news title affects and how: '{title}'. "
                f"Impact Score: {affect_rate}/100. Bias: {direction}. "
                "Focus on sectors, volatility, or specific asset classes."
            )

            def call_gemini():
                response = self.ai_client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt
                )
                return response.text.strip()

            return await asyncio.wait_for(
                asyncio.to_thread(call_gemini),
                timeout=self.gemini_timeout_sec
            )
        except Exception as e:
            err_text = str(e)
            if "RESOURCE_EXHAUSTED" in err_text or "quota" in err_text.lower():
                if not self._gemini_disabled:
                    logger.warning("Gemini quota exhausted, disabling remote insights for this runtime.")
                self._gemini_disabled = True
                self.runtime_status["gemini_disabled"] = True
            else:
                logger.error("Gemini insight error: %s", e)
            return "Statistical model suggests monitoring high-volatility sectors related to this event."

    async def get_global_news_impact(self, benchmark_ticker: str = "^NSEI", interval: str = "15m") -> List[Dict[str, Any]]:
        """Fetch live financial news and run the analysis pipeline in parallel."""
        request_key = f"{benchmark_ticker}|{interval}"
        t0 = datetime.utcnow()
        self.runtime_status["last_fetch_at"] = t0.isoformat() + "Z"
        self.runtime_status["last_error"] = None
        self.runtime_status["cache_hit"] = False

        # Serve recent results from in-memory cache to keep endpoint responsive.
        if (
            self._cached_at
            and self._cached_news
            and self._cached_benchmark_ticker == benchmark_ticker
            and self._cached_interval == interval
        ):
            age_sec = (datetime.utcnow() - self._cached_at).total_seconds()
            if age_sec < self.cache_ttl_sec:
                self.runtime_status["cache_hit"] = True
                self.runtime_status["last_duration_ms"] = max((datetime.utcnow() - t0).total_seconds() * 1000.0, 0.0)
                return copy.deepcopy(self._cached_news)

        if self._inflight_task is not None and self._inflight_key == request_key:
            try:
                shared = await self._inflight_task
                self.runtime_status["cache_hit"] = True
                self.runtime_status["last_duration_ms"] = max((datetime.utcnow() - t0).total_seconds() * 1000.0, 0.0)
                return copy.deepcopy(shared)
            except Exception:
                self._inflight_task = None
                self._inflight_key = None

        async def _compute() -> List[Dict[str, Any]]:
            live_news = await asyncio.to_thread(self._fetch_live_news, self.max_headlines)
            if not live_news:
                logger.warning("Live news providers unavailable. Falling back to synthetic feed.")
                live_news_local = self._synthetic_news_fallback()
                self.runtime_status["last_mode"] = "synthetic_fallback"
                self.runtime_status["last_provider"] = "synthetic"
                self.runtime_status["last_live_count"] = len(live_news_local)
            else:
                live_news_local = live_news
                self.runtime_status["last_mode"] = "live"

            live_news_local = live_news_local[:self.max_headlines]
            analyzed_news = [self.analyze_news_item(item) for item in live_news_local]

            if self.ai_client is None or self._gemini_disabled:
                for item in analyzed_news:
                    item["assistant_insight"] = "Statistical model suggests monitoring high-volatility sectors related to this event."
                analyzed_news.sort(key=lambda x: x["affect_rate"], reverse=True)
                self.runtime_status["gemini_disabled"] = self._gemini_disabled
                self.runtime_status["gemini_available"] = self.ai_client is not None
                try:
                    from backend.services.news_event_study_service import news_event_study_service

                    news_event_study_service.record_items(analyzed_news, benchmark_ticker=benchmark_ticker)
                    analyzed_news = news_event_study_service.calibrate_items(
                        analyzed_news,
                        benchmark_ticker=benchmark_ticker,
                        interval=interval,
                    )
                except Exception as exc:
                    self.runtime_status["last_error"] = str(exc)
                self._cached_news = copy.deepcopy(analyzed_news)
                self._cached_at = datetime.utcnow()
                self._cached_benchmark_ticker = benchmark_ticker
                self._cached_interval = interval
                return analyzed_news

            ai_limit = max(0, min(self.max_ai_insights, len(analyzed_news)))
            tasks = [
                self._generate_quick_insight_async(
                    analyzed_news[i]["title"],
                    analyzed_news[i]["affect_rate"],
                    analyzed_news[i]["market_direction"]
                )
                for i in range(ai_limit)
            ]

            insights = await asyncio.gather(*tasks, return_exceptions=True)

            for i in range(len(analyzed_news)):
                analyzed_news[i]["assistant_insight"] = (
                    "Statistical model suggests monitoring high-volatility sectors related to this event."
                )

            for i, insight in enumerate(insights):
                if isinstance(insight, Exception):
                    self.runtime_status["last_error"] = str(insight)
                else:
                    analyzed_news[i]["assistant_insight"] = insight
            
            # [NEW] Store high-impact stories in long-term memory
            for item in analyzed_news:
                if item.get("affect_rate", 0) > 75:
                    memory_service.add_memory(
                        content=f"High Impact News: {item['title']}. Impact: {item['affect_rate']}. Bias: {item['market_direction']}. Insight: {item['assistant_insight']}",
                        source="news_ml_service",
                        metadata={
                            "memory_type": "news",
                            "ticker": benchmark_ticker,
                            "interval": interval,
                            "title": item.get("title"),
                            "published_at": item.get("published_at") or item.get("publishedAt"),
                            "url": item.get("url"),
                            "market_direction": item.get("market_direction"),
                            "affect_rate": item.get("affect_rate"),
                            "confidence": min(max(float(item.get("affect_rate", 0.0) or 0.0) / 100.0, 0.35), 0.95),
                        }
                    )

            analyzed_news.sort(key=lambda x: x["affect_rate"], reverse=True)
            self.runtime_status["gemini_disabled"] = self._gemini_disabled
            self.runtime_status["gemini_available"] = self.ai_client is not None
            try:
                from backend.services.news_event_study_service import news_event_study_service

                news_event_study_service.record_items(analyzed_news, benchmark_ticker=benchmark_ticker)
                analyzed_news = news_event_study_service.calibrate_items(
                    analyzed_news,
                    benchmark_ticker=benchmark_ticker,
                    interval=interval,
                )
            except Exception as exc:
                self.runtime_status["last_error"] = str(exc)
            self._cached_news = copy.deepcopy(analyzed_news)
            self._cached_at = datetime.utcnow()
            self._cached_benchmark_ticker = benchmark_ticker
            self._cached_interval = interval
            return analyzed_news

        self._inflight_key = request_key
        self._inflight_task = asyncio.create_task(_compute())
        try:
            result = await self._inflight_task
            self.runtime_status["last_duration_ms"] = max((datetime.utcnow() - t0).total_seconds() * 1000.0, 0.0)
            return result
        finally:
            self._inflight_task = None
            self._inflight_key = None

    def get_runtime_status(self) -> Dict[str, Any]:
        degraded = not (TEXTBLOB_AVAILABLE and VADER_AVAILABLE and XGBOOST_AVAILABLE)
        return {
            "status": "degraded" if degraded else "operational",
            "news_api_configured": bool(self.news_api_key),
            "alpha_vantage_configured": bool(self.alpha_vantage_key),
            "gemini_available": bool(self.ai_client),
            "gemini_disabled": bool(self._gemini_disabled),
            **self.runtime_status,
        }


# Singleton instance
news_ml_service = NewsMLService()
