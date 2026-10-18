"""Live news + social radar for things that move NIFTY/SENSEX, directly or indirectly.

Sources verified reachable Oct 2026: ET Markets, Moneycontrol, LiveMint, Business Standard,
NDTV Profit, CNBC-TV18, RBI, SEBI, Google News search (RSS), Reddit (Atom; rate-limited,
polled slowly). X/Twitter has no free API: set X_BEARER_TOKEN to enable the paid search API.
Scoring is a transparent keyword lexicon (direction x impact x recency), not a black box.
"""
from __future__ import annotations

import hashlib
import html
import logging
import math
import os
import re
import threading
import time as _time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import requests

from .config import IST

log = logging.getLogger("engine.news")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) c0mr4des-terminal/2.0 (personal research)"}

FEEDS = [
    ("ET Markets", "news", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("Moneycontrol", "news", "https://www.moneycontrol.com/rss/marketreports.xml"),
    ("Moneycontrol Buzz", "news", "https://www.moneycontrol.com/rss/buzzingstocks.xml"),
    ("LiveMint", "news", "https://www.livemint.com/rss/markets"),
    ("Business Standard", "news", "https://www.business-standard.com/rss/markets-106.rss"),
    ("NDTV Profit", "news", "https://feeds.feedburner.com/ndtvprofit-latest"),
    ("CNBC-TV18", "news", "https://www.cnbctv18.com/commonfeeds/v1/cne/rss/market.xml"),
    ("RBI", "official", "https://www.rbi.org.in/pressreleases_rss.xml"),
    ("SEBI", "official", "https://www.sebi.gov.in/sebirss.xml"),
    ("Google News", "news", "https://news.google.com/rss/search?q=" + quote_plus(
        "(nifty OR sensex OR \"dalal street\" OR RBI OR FII) when:1d") + "&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Google News Global", "news", "https://news.google.com/rss/search?q=" + quote_plus(
        "(Fed OR \"crude oil\" OR tariff OR \"US markets\" OR \"treasury yields\") when:1d") + "&hl=en-IN&gl=IN&ceid=IN:en"),
]
REDDIT = ["IndianStreetBets", "IndianStockMarket", "IndiaInvestments", "StockMarketIndia"]

# (pattern, direction, impact 1-3, scope, plain-English why)
LEXICON = [
    (r"rate cut|cuts? repo|dovish|liquidity infusion|crr cut", 1, 3, "direct", "Cheaper money is good for stocks, especially banks."),
    (r"rate hike|hikes? repo|hawkish|tightening", -1, 3, "direct", "Costlier money usually hurts stock prices."),
    (r"repo rate|monetary policy|mpc", 0, 3, "direct", "RBI policy event: expect volatility around the announcement."),
    (r"fii (selling|outflow)|fpi (selling|outflow)|foreign investors? (sold|pull|dump)|fii sold|fpis? sold|fiis? (sell|dump|offload|pull)", -1, 3, "direct", "Foreign funds selling drags index heavyweights."),
    (r"fii (buying|inflow)|fpi (buying|inflow)|foreign investors? (bought|pour)|fii bought|fpis? bought", 1, 3, "direct", "Foreign funds buying lifts index heavyweights."),
    (r"dii (buying|bought)|sip inflows? (record|high)", 1, 1, "direct", "Domestic funds are supporting the market."),
    (r"sensex (crash|tank|plunge|slump|sink)|nifty (crash|tank|plunge|slump|sink)", -1, 2, "direct", "Strong selling momentum in Indian markets."),
    (r"market crash|bloodbath|sell-?off|worst (week|day) since", -1, 1, "indirect", "Heavy selling in a major market spills over into risk appetite."),
    (r"sensex (surge|soar|jump|rall)|nifty (surge|soar|jump|rall)|record high|all-time high|fresh high", 1, 2, "direct", "Strong buying momentum in Indian markets."),
    (r"inflation (eases|cools|falls|lower)|cpi (eases|falls|lower)", 1, 2, "direct", "Lower inflation opens room for rate cuts."),
    (r"inflation (rises|jumps|surges|higher|spike)|cpi (rises|jumps|higher)", -1, 2, "direct", "Higher inflation delays rate cuts."),
    (r"gdp (grows|beats|surges|strong)|growth (beats|accelerat)", 1, 2, "direct", "Strong growth supports earnings."),
    (r"gdp (slows|misses|contracts|weak)|slowdown|recession", -1, 2, "direct", "Weaker growth hurts earnings outlook."),
    (r"sebi.{0,40}(f&o|derivative|option|expiry|curb|tighten)", 0, 2, "direct", "F&O rule changes can change volumes and volatility."),
    (r"union budget|fiscal deficit|\bltcg\b|\bstt\b", 0, 2, "direct", "Tax/budget news can swing the whole market."),
    (r"gift nifty (up|higher|gain|rise|indicat.{0,10}positive)", 1, 2, "direct", "GIFT Nifty points to a higher open."),
    (r"gift nifty (down|lower|fall|slip|indicat.{0,10}negative)", -1, 2, "direct", "GIFT Nifty points to a lower open."),
    (r"hdfc bank|reliance|icici bank|infosys|tcs|bharti airtel|larsen|itc\b|sbi\b|axis bank|kotak", 0, 1, "direct", "Index heavyweight news moves NIFTY/SENSEX directly."),
    (r"(beats?|tops?) estimates|profit (jumps|rises|surges)|strong (q[1-4]|results|earnings)", 1, 1, "direct", "Good results from a large company."),
    (r"(misses?|below) estimates|profit (falls|drops|slumps|declines)|weak (q[1-4]|results|earnings)", -1, 1, "direct", "Weak results from a large company."),
    (r"crude (surges|jumps|spikes|soars|rises)|oil (surges|jumps|spikes|soars)|brent (rises|jumps)", -1, 2, "indirect", "India imports most of its oil: costlier crude hurts the rupee and margins."),
    (r"crude (falls|slumps|drops|eases|tumbles)|oil (falls|slumps|drops|eases)|brent (falls|drops)", 1, 2, "indirect", "Cheaper crude is good for India's import bill and inflation."),
    (r"rupee (falls|slumps|weakens|record low|hits low)|inr (falls|weakens)", -1, 2, "indirect", "A weak rupee pushes foreign investors out."),
    (r"rupee (rises|gains|strengthens)|inr (gains|strengthens)", 1, 1, "indirect", "A strong rupee attracts foreign money."),
    (r"fed (cuts|signals? cut|dovish)|powell.{0,30}(cut|dovish)", 1, 2, "indirect", "Easier US money tends to flow into emerging markets like India."),
    (r"fed (hikes|hawkish|holds? higher)|powell.{0,30}(hike|hawkish)", -1, 2, "indirect", "Tighter US money pulls funds out of emerging markets."),
    (r"(treasury|bond) yields? (surge|jump|spike|rise|climb)", -1, 2, "indirect", "Higher US yields pull foreign money out of India."),
    (r"(treasury|bond) yields? (fall|drop|ease|slip)", 1, 1, "indirect", "Lower US yields make emerging markets more attractive."),
    (r"dollar (surges|strengthens|jumps)|dxy (rises|jumps)", -1, 1, "indirect", "A strong dollar tends to pressure emerging markets."),
    (r"(new|higher|reciprocal|retaliatory|steep) tariffs?|tariffs? (hike|war|threat)|trade war|sanctions?\b", -1, 2, "indirect", "Trade tensions hurt exporters and risk appetite."),
    (r"free trade agreement|\bfta\b|trade deal (signed|sealed|agreed)|tariff (cut|relief|concession)", 1, 1, "indirect", "Trade deals help exporters and sentiment."),
    (r"wall street (rall|surge|jump|record)|s&p 500 (record|rall|jump)|nasdaq (rall|surge|jump|record)|dow (rall|surge|jump)", 1, 1, "indirect", "A strong US market lifts global risk appetite."),
    (r"wall street (fall|slump|tumble|sell)|s&p 500 (fall|slump|drop)|nasdaq (fall|slump|tumble)|dow (fall|slump|tumble)", -1, 1, "indirect", "A weak US market hurts global risk appetite."),
    (r"wars?\b|military (action|strike|escalat)|missiles?\b|air ?strikes?|border tension|terror attack|ceasefire violat", -1, 3, "indirect", "Geopolitical risk makes markets nervous."),
    (r"ceasefire|peace (deal|talks)|de-?escalat", 1, 2, "indirect", "Easing geopolitical risk calms markets."),
    (r"election|exit poll|poll result", 0, 2, "direct", "Elections cause large volatility around results."),
]
# Leading word boundary so "war" never matches "software"/"award", "itc" never matches "switch".
_LEX = [(re.compile(r"\b(?:" + p + r")", re.I), d, imp, scope, why) for p, d, imp, scope, why in LEXICON]


NEGATORS = re.compile(r"(probability|odds|chances?|bets?)( of [\w ]{0,20})? (falls?|drops?|fades?|slips?|recedes?)|"
                      r"unlikely|rules? out|\bno (rate )?(hike|cut)|on hold|\bpause", re.I)


def score_text(text: str) -> dict:
    hits, direction, impact = [], 0.0, 0
    negated = bool(NEGATORS.search(text))
    for rx, d, imp, scope, why in _LEX:
        m = rx.search(text)
        if m and negated and d != 0 and re.search(r"hike|cut|hawkish|dovish", m.group(0), re.I):
            # "hike odds fall" means the opposite of "hike": flip direction, soften impact
            d, imp, why = -d, max(1, imp - 1), "Markets now see this as less likely, which reverses the effect."
        if m:
            hits.append({"match": m.group(0), "direction": d, "impact": imp, "scope": scope, "why": why})
            direction += d * imp
            impact = max(impact, imp)
    d = 1 if direction > 0 else -1 if direction < 0 else 0
    scope = "direct" if any(h["scope"] == "direct" for h in hits) else ("indirect" if hits else "none")
    why = next((h["why"] for h in hits if h["direction"] == d), hits[0]["why"] if hits else "")
    return {"direction": d, "impact": impact, "scope": scope, "keywords": [h["match"] for h in hits], "why": why}


def _parse_time(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return parsedate_to_datetime(s).astimezone(IST)
    except Exception:  # noqa: BLE001
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(IST)
        except Exception:  # noqa: BLE001
            return None


def _clean(s: str | None) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def _parse_feed(xml: str, source: str, kind: str) -> list[dict]:
    items = []
    try:
        root = ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    except ET.ParseError:
        return items
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for it in root.iter("item"):
        items.append({"title": _clean(it.findtext("title")), "url": (it.findtext("link") or "").strip(),
                      "summary": _clean(it.findtext("description"))[:300],
                      "published": _parse_time(it.findtext("pubDate"))})
    for it in root.findall("a:entry", ns):
        link = it.find("a:link", ns)
        items.append({"title": _clean(it.findtext("a:title", namespaces=ns)),
                      "url": link.get("href") if link is not None else "",
                      "summary": _clean(it.findtext("a:content", namespaces=ns))[:300],
                      "published": _parse_time(it.findtext("a:updated", namespaces=ns) or it.findtext("a:published", namespaces=ns))})
    for i in items:
        i["source"], i["kind"] = source, kind
    return [i for i in items if i["title"]]


class NewsRadar:
    def __init__(self):
        self.items: dict[str, dict] = {}
        self.status: dict[str, str] = {}
        self.last_refresh = 0.0
        self._reddit_idx = 0
        self._lock = threading.Lock()

    def _fetch(self, url: str) -> str | None:
        try:
            r = requests.get(url, headers=UA, timeout=12)
            return r.text if r.status_code == 200 else None
        except Exception:  # noqa: BLE001
            return None

    def refresh(self, force: bool = False) -> None:
        if not force and _time.time() - self.last_refresh < 90:
            return
        self.last_refresh = _time.time()
        fetched: list[dict] = []
        for name, kind, url in FEEDS:
            xml = self._fetch(url)
            self.status[name] = "ok" if xml else "unreachable"
            if xml:
                fetched += _parse_feed(xml, name, kind)
        # Reddit throttles hard: one subreddit per refresh, rotating.
        sub = REDDIT[self._reddit_idx % len(REDDIT)]
        self._reddit_idx += 1
        xml = self._fetch(f"https://www.reddit.com/r/{sub}/new/.rss?limit=25")
        self.status[f"r/{sub}"] = "ok" if xml else "rate-limited"
        if xml:
            fetched += _parse_feed(xml, f"r/{sub}", "reddit")
        fetched += self._x_search()
        now = datetime.now(IST)
        with self._lock:
            for it in fetched:
                key = hashlib.sha1(re.sub(r"\W+", "", it["title"].lower())[:90].encode()).hexdigest()
                if key in self.items:
                    self.items[key]["sources"] = sorted(set(self.items[key]["sources"]) | {it["source"]})
                    continue
                pub = it["published"] or now
                if (now - pub).total_seconds() > 3 * 86400:
                    continue
                it.update(score_text(it["title"] + " " + it["summary"]))
                it["published"] = pub.isoformat(timespec="seconds")
                it["sources"] = [it["source"]]
                it["id"] = key
                self.items[key] = it
            cutoff = now.timestamp() - 3 * 86400
            self.items = {k: v for k, v in self.items.items() if datetime.fromisoformat(v["published"]).timestamp() > cutoff}

    def _x_search(self) -> list[dict]:
        token = os.getenv("X_BEARER_TOKEN")
        if not token:
            self.status["X / Twitter"] = "disabled (no X_BEARER_TOKEN - X API is paid)"
            return []
        q = "(nifty OR sensex OR #stockmarketindia OR RBI) lang:en -is:retweet"
        try:
            r = requests.get("https://api.twitter.com/2/tweets/search/recent",
                             params={"query": q, "max_results": 25, "tweet.fields": "created_at,author_id"},
                             headers={"Authorization": f"Bearer {token}"}, timeout=12)
            if r.status_code != 200:
                self.status["X / Twitter"] = f"error {r.status_code}"
                return []
            self.status["X / Twitter"] = "ok"
            return [{"title": _clean(t["text"])[:240], "url": f"https://x.com/i/web/status/{t['id']}", "summary": "",
                     "published": _parse_time(t.get("created_at")), "source": "X", "kind": "x"}
                    for t in r.json().get("data", [])]
        except Exception:  # noqa: BLE001
            self.status["X / Twitter"] = "unreachable"
            return []

    def feed(self, query: str | None = None, kind: str | None = None, only_relevant: bool = False, limit: int = 80) -> list[dict]:
        self.refresh()
        now = datetime.now(IST)
        with self._lock:
            items = list(self.items.values())
        if query:
            terms = [t.strip().lower() for t in re.split(r"[,\s]+", query) if t.strip()]
            items = [i for i in items if all(t in (i["title"] + " " + i["summary"]).lower() for t in terms)]
        if kind:
            items = [i for i in items if i["kind"] == kind]
        if only_relevant:
            items = [i for i in items if i["impact"] > 0]
        for i in items:
            age_h = (now - datetime.fromisoformat(i["published"])).total_seconds() / 3600
            i["age_minutes"] = int(age_h * 60)
            social = 0.4 if i["kind"] in ("reddit", "x") else 1.0  # social chatter is noisier than reported news
            i["score"] = round(social * i["direction"] * i["impact"] * math.exp(-age_h / 6) * (1 + 0.3 * (len(i["sources"]) - 1)), 3)
        items.sort(key=lambda i: i["published"], reverse=True)
        return items[:limit]

    def sentiment(self) -> dict:
        """Recency-weighted news bias over the last ~12 hours, in [-1, 1]."""
        items = [i for i in self.feed(limit=400) if i["impact"] > 0 and i["age_minutes"] <= 720]
        if not items:
            return {"bias": 0.0, "count": 0, "text": "No market-moving headlines in the last 12 hours.", "drivers": []}
        total = sum(i["score"] for i in items)
        weight = sum(abs(i["score"]) for i in items) or 1
        bias = max(-1.0, min(1.0, total / max(weight, 3)))
        drivers = sorted(items, key=lambda i: abs(i["score"]), reverse=True)[:3]
        mood = "positive" if bias > 0.15 else "negative" if bias < -0.15 else "mixed/neutral"
        return {"bias": round(bias, 2), "count": len(items),
                "text": f"News flow is {mood} ({len(items)} relevant headlines in 12h).",
                "drivers": [{"title": d["title"], "direction": d["direction"], "why": d["why"], "source": d["source"]} for d in drivers]}


radar = NewsRadar()
