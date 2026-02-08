from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from backend.market_data import get_market_regime
from dotenv import load_dotenv
import os
import google.generativeai as genai
from pydantic import BaseModel
from PIL import Image
import io

# Load environment variables from backend/.env file
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=env_path)

# Configure Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

app = FastAPI()

# Allow frontend to communicate with backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development; restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include new routers
from backend.main_integration import router as advanced_router
from backend.dashboard_integration import router as dashboard_router

app.include_router(advanced_router)
app.include_router(dashboard_router)

@app.get("/")
def read_root():
    # API Key configured in .env file
    return {"status": "Edge-Ops Backend Running"}

@app.get("/api/regime")
def read_regime(ticker: str = "^NSEI"):
    """
    Fetch market regime for a given ticker.
    Default: ^NSEI (Nifty 50)
    """
    return get_market_regime(ticker)

@app.get("/api/history")
def read_history(ticker: str = "^NSEI", period: str = "1y", interval: str = "1d"):
    """
    Fetch historical price data with indicators and signals.
    """
    from backend.market_data import get_market_history
    return get_market_history(ticker, period, interval)

@app.get("/api/quant_analysis")
def get_quant_data(ticker: str = "^NSEI", period: str = "1y"):
    """
    Fetch Advanced Quant Analysis: Regime Detection (Wasserstein), A-Vol, Unsupervised State.
    """
    from backend.quant_engine import get_quant_analysis
    try:
        data = get_quant_analysis(ticker, period=period)
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

class ChatRequest(BaseModel):
    context: str
    question: str

@app.post("/api/chat_analysis")
def chat_with_analysis(request: ChatRequest):
    """
    Run the Strategy Optimizer to learn the best parameters from historical data.
    """
    from backend.optimizer import StrategyOptimizer
    try:
        tester = Backtester(ticker=ticker, interval=interval, period=period)
        tester.fetch_data()
        tester.run()
        return tester.get_results()
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/train")
def train_model(ticker: str = "^NSEI"):
    """
    Run the Strategy Optimizer to learn the best parameters from historical data.
    """
    from backend.optimizer import StrategyOptimizer
    try:
        opt = StrategyOptimizer(ticker=ticker)
        result = opt.optimize() # Now returns dict with best_params and logs
        return {"status": "success", "data": result}
    except Exception as e:
        # Return error but don't crash 
        return {"status": "error", "message": str(e)}

@app.get("/api/intraday")
def get_intraday_data(ticker: str = "^NSEI", interval: str = "5m"):
    """
    Fetch live intraday data for options trading (5m, 15m intervals)
    Optimized for intraday with VWAP, faster indicators, and strike recommendations
    """
    import yfinance as yf
    import pandas as pd
    import numpy as np
    from backend.market_data import calculate_sma, calculate_rsi, calculate_atr
    from backend.intraday_utils import (
        is_market_open, calculate_vwap, calculate_option_strikes, 
        get_next_expiry, should_square_off, load_params
    )
    
    # Load learned parameters
    PARAMS = load_params()
    
    try:
        # Fetch 5 days of data to ensure we catch the latest open candles (avoid yf 1d bug)
        df = yf.download(ticker, period="5d", interval=interval, progress=False)
        
        if df.empty:
            return {
                "data": [],
                "market_open": is_market_open(),
                "message": "No data available"
            }
        
        # Handle multi-index columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']
        
        # DEBUG: Print latest index
        if not df.empty:
            print(f"DEBUG: Latest data point time: {df.index[-1]}")
            
            # Filter for TODAY only if market is open, otherwise show last available
            # But for now, let's just return the last 75 candles to show context
            # This fixes the 'empty chart' issue if '1d' returns nothing at 9:16 AM
            if len(df) > 75:
                 df = df.iloc[-75:]
                 close = df['Close']
                 high = df['High']
                 low = df['Low']
                 volume = df['Volume']
        
        # Intraday indicators (faster periods)
        sma_9 = calculate_sma(close, 9)
        sma_21 = calculate_sma(close, 21)
        rsi_9 = calculate_rsi(close, 9)
        atr = calculate_atr(high, low, close, 14)
        vwap = calculate_vwap(high, low, close, volume)
        vol_sma = volume.rolling(window=20).mean()
        
        history = []
        in_position = False
        entry_price = 0
        stop_loss = None
        take_profit = None
        
        for i in range(len(df)):
            date_obj = df.index[i]
            date_str = date_obj.strftime('%H:%M')  # Just time for intraday
            
            price = float(close.iloc[i])
            s9 = float(sma_9.iloc[i]) if not np.isnan(sma_9.iloc[i]) else None
            s21 = float(sma_21.iloc[i]) if not np.isnan(sma_21.iloc[i]) else None
            r_val = float(rsi_9.iloc[i]) if not np.isnan(rsi_9.iloc[i]) else 50
            atr_val = float(atr.iloc[i]) if not np.isnan(atr.iloc[i]) else 0
            vwap_val = float(vwap.iloc[i]) if not np.isnan(vwap.iloc[i]) else price
            vol_val = float(volume.iloc[i]) if not np.isnan(volume.iloc[i]) else 0
            v_sma = float(vol_sma.iloc[i]) if not np.isnan(vol_sma.iloc[i]) else 0
            
            signal = None
            confidence = 0.0
            reason = ""
            action = "WAIT"
            
            # Intraday Signal Logic
            if s9 and s21 and atr_val > 0:
                # ENTRY CONDITIONS (Intraday specific)
                if not in_position:
                    entry_signal = False
                    
                    # Scenario A: VWAP Pullback (price dips to VWAP in uptrend)
                    if price > s21 and price < vwap_val and r_val < PARAMS['rsi_entry']:
                        entry_signal = True
                        reason = "VWAP Pullback"
                        confidence = 0.75
                    
                    # Scenario B: Breakout with volume
                    prev_high = float(high.iloc[max(0, i-3):i].max()) if i > 3 else price
                    volume_spike = vol_val > (v_sma * 1.5) if v_sma > 0 else False
                    
                    if price > prev_high and volume_spike and price > vwap_val:
                        entry_signal = True
                        reason = "Breakout + Volume"
                        confidence = 0.85
                    
                    # Scenario C: Oversold bounce
                    if r_val < 30 and price > s9:
                        entry_signal = True
                        reason = "Oversold Bounce"
                        confidence = 0.65
                    
                    if entry_signal and confidence > 0.6:
                        signal = "ENTRY"
                        in_position = True
                        entry_price = price
                        stop_loss = price - (1.5 * atr_val)  # Tighter stop for intraday
                        take_profit = price + (2 * (price - stop_loss))  # 2:1 R/R
                        action = "ENTER NOW"
                
                # EXIT CONDITIONS
                elif in_position:
                    # Trail stop loss
                    current_stop = price - (1.5 * atr_val)
                    if stop_loss and current_stop > stop_loss:
                        stop_loss = current_stop
                    
                    stop_hit = price < stop_loss if stop_loss else False
                    take_profit_hit = price > take_profit if take_profit else False
                    trend_break = price < s9 and price < vwap_val
                    
                    # Force exit if market closing soon
                    if should_square_off():
                        signal = "EXIT"
                        reason = "Square Off (Market Close)"
                        in_position = False
                        action = "EXIT NOW"
                    elif stop_hit:
                        signal = "EXIT"
                        reason = "Stop Loss Hit"
                        in_position = False
                        action = "EXIT NOW"
                    elif take_profit_hit:
                        signal = "EXIT"
                        reason = "Target Hit"
                        in_position = False
                        action = "EXIT NOW"
                    elif trend_break:
                        signal = "EXIT"
                        reason = "Trend Broken"
                        in_position = False
                        action = "EXIT NOW"
                    else:
                        action = "HOLD"
            
            history.append({
                "time": date_str,
                "price": price,
                "sma9": s9,
                "sma21": s21,
                "rsi": r_val,
                "vwap": vwap_val,
                "stop_loss": stop_loss if in_position or signal == "ENTRY" else None,
                "take_profit": take_profit if in_position or signal == "ENTRY" else None,
                "confidence": confidence if signal == "ENTRY" else None,
                "reason": reason if signal else None,
                "signal": signal,
                "action": action
            })
        
        # Get latest signal for options recommendation
        latest = history[-1] if history else None
        options_data = None
        
        if latest and latest["signal"] == "ENTRY":
            # Determine index type
            index_type = "NIFTY" if "NSEI" in ticker else "BANKNIFTY"
            strikes = calculate_option_strikes(latest["price"], "ENTRY", index_type)
            expiry = get_next_expiry()
            
            options_data = {
                "type": strikes["type"],
                "atm_strike": strikes["atm"],
                "otm_strike": strikes["otm"],
                "itm_strike": strikes["itm"],
                "recommended_strike": strikes["atm"],  # Default to ATM
                "expiry": expiry,
                "entry_range": f"₹{latest['price']:.2f}",
                "stop_loss": f"₹{latest['stop_loss']:.2f}" if latest['stop_loss'] else None,
                "target": f"₹{latest['take_profit']:.2f}" if latest['take_profit'] else None
            }
        
        return {
            "data": history,
            "market_open": is_market_open(),
            "latest_signal": latest,
            "options": options_data,
            "interval": interval
        }
    
    except Exception as e:
        return {
            "data": [],
            "market_open": is_market_open(),
            "error": str(e)
        }

# --- HELPER: Robust Generation with Fallback ---
def generate_content_with_fallback(prompt, image=None):
    """
    Attempts to generate content using a prioritized list of models.
    Falls back to the next model if 404 (Not Found) or 429 (Quota) errors occur.
    """
    # Priority list based on availability and capability
    MODELS = [
        'gemini-2.5-flash',       # Latest preview (often free/separate quota)
        'gemini-flash-latest',    # Stable alias
        'gemini-2.0-flash-lite',  # Lightweight backup
        'gemini-1.5-flash'        # Old reliable (if available)
    ]

    last_error = None

    for model_name in MODELS:
        try:
            print(f"DEBUG: Attempting generation with model: {model_name}")
            model = genai.GenerativeModel(model_name)
            
            if image:
                response = model.generate_content([prompt, image])
            else:
                response = model.generate_content(prompt)
                
            return response
        except Exception as e:
            error_str = str(e)
            print(f"WARNING: Model {model_name} failed: {error_str}")
            last_error = e
            # Continue to next model
            continue

    # If all failed, raise the last error
    if last_error:
        raise last_error
    else:
        raise Exception("No models available.")

@app.post("/api/analyze")
async def analyze_image_file(file: UploadFile = File(...)):
    """
    Analyze chart image for patterns using Gemini Vision API with Autonomous Agents.
    """
    try:
        import google.generativeai as genai
        import os
        from PIL import Image
        import io
        
        # Configure Gemini API
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return {
                "patterns": ["API Key Missing"],
                "sentiment": "Neutral",
                "confidence": 0.0,
                "recommendation": "Please set GEMINI_API_KEY environment variable.",
                "analysis": "Cannot analyze without API key."
            }
        
        genai.configure(api_key=api_key)
        
        # Read uploaded file
        contents = await file.read()
        image = Image.open(io.BytesIO(contents))
        
        # Craft detailed prompt for chart analysis
        prompt = """Analyze this financial chart image autonomously.

Your goal is to act as an elite Hedge Fund Analyst.
1. **OCR & Context**: EXTRACT the Ticker Symbol (e.g., RELIANCE, TSLA), Timeframe (e.g., 5m, 1D), and Current Price.
2. **Technical Analysis**: deeply analyze patterns (ICT, Price Action), Support/Resistance, and Momentum.
3. **Sentiment**: Determine if the structure is Bullish, Bearish, or Neutral.
4. **Action**: Recommend a trade (LONG/SHORT/WAIT).

Return ONLY a valid JSON object:
{
    "is_chart": true,
    "ticker_detected": "SYMBOL OR NULL",
    "timeframe": "15m OR NULL",
    "current_price": 123.45,
    "patterns": ["Pattern1", "Pattern2"],
    "sentiment": "Bullish/Bearish/Neutral",
    "confidence": 0.85,
    "recommendation": "Specific action",
    "analysis": "Detailed technical analysis..."
}"""

        # Generate INITIAL Visual analysis using Fallback
        try:
            response = generate_content_with_fallback(prompt, image)
        except Exception as e:
             # Return error JSON directly if all models fail
             return {
                "patterns": ["System Error"],
                "sentiment": "Neutral",
                "confidence": 0.0,
                "recommendation": "Analysis Failed",
                "analysis": f"All AI Models failed. Last error: {str(e)}"
            }
        
        # Parse response
        import json
        try:
            # Extract JSON from response
            response_text = response.text.strip()
            
            if response_text.startswith("```json"):
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif response_text.startswith("```"):
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            result = json.loads(response_text)
            
            # --- AUTONOMOUS AGENT UPGRADE: NEWS INTEGRATION ---
            ticker = result.get("ticker_detected")
            if ticker and ticker != "NULL" and ticker != "Unknown":
                print(f"Autonomous Entity: Detected Ticker {ticker}. Initiating Deep Research...")
                
                # 1. Fetch News & Technical Hard Data (Hybrid Intelligence)
                from backend.news_engine import fetch_market_news
                from backend.market_intelligence import get_market_intelligence
                from backend.quant_engine import get_quant_analysis
                
                # Auto-correction for NSE if needed
                search_ticker = ticker
                if not ticker.endswith(".NS") and not ticker.startswith("^") and ticker.isalpha():
                    # Check if likely Indian context
                    search_ticker = f"{ticker}.NS" 
                
                news_summary = fetch_market_news(search_ticker)
                tech_data = get_market_intelligence(search_ticker)
                quant_data = get_quant_analysis(search_ticker)
                
                # Format Quant Data safely
                if "error" in quant_data:
                    quant_text = "Quant Data Unavailable."
                else:
                    quant_text = f"""
                    - Market Regime: {quant_data['regime']['status']} (Drift: {quant_data['regime']['drift_score']})
                    - Volatility State: {quant_data['volatility']['status']} (Z-Score: {quant_data['volatility']['z_score']})
                    - Predictability (Entropy): {quant_data['chaos_theory']['predictability']}
                    """
                
                # 2. Synthesis Call (Text only)
                synthesis_prompt = f"""
                You are a Portfolio Manager with 20+ years of experience.
                
                Your Task: "THE JUDGE"
                Reconcile the Visual Analysis with the HARD DATA FACTS.
                
                1. Visual Analysis (Subjective):
                {result.get('analysis')}
                Sentiment: {result.get('sentiment')}
                
                2. HARD DATA FACTS (Objective Truth):
                - Trend: {tech_data.get('trend', 'N/A')}
                - RSI: {tech_data.get('momentum_rsi', 'N/A')}
                - Volatility: {tech_data.get('volatility_atr', 'N/A')}
                - Structure: {tech_data.get('structure', 'N/A')}
                
                3. ADVANCED QUANT METRICS (The "Rocket Science"):
                {quant_text}
                
                4. Market News:
                {news_summary}
                
                CORE RULES:
                - If Visual says "SHORT" but Hard Data says "Bullish Trend & RSI 40", REJECT the visual bias.
                - If Quant says "Regime Shift Detected", enable MAXIMUM CAUTION.
                - If Entropy says "Random Walk", ignore minimal ICT patterns.
                - DATA > VISION.
                
                Output: A unified final analysis paragraph blending Chart + Data + Quant + News.
                And a final 'recommendation' (e.g. "LONG (High Conviction)" or "WAIT (Regime Unstable)").
                
                Return JSON: {{"new_analysis": "...", "new_recommendation": "..."}}
                """
                
                try:
                    # Use Fallback for Synthesis too
                    synth_response = generate_content_with_fallback(synthesis_prompt)
                    
                    synth_text = synth_response.text.strip()
                    if synth_text.startswith("```json"):
                         synth_text = synth_text.split("```json")[1].split("```")[0].strip()
                    elif synth_text.startswith("```"):
                         synth_text = synth_text.split("```")[1].split("```")[0].strip()
                    
                    synth_json = json.loads(synth_text)
                    
                    # Merge Logic
                    result['analysis'] = f"**Technical & Fundamental Synthesis**:\n{synth_json['new_analysis']}\n\n**Technical Basis**:\n{result['analysis']}"
                    result['recommendation'] = synth_json['new_recommendation']
                    result['patterns'].append("News Analyzed")
                    
                except Exception as e:
                    print(f"Synthesis failed: {e}")
                    result['analysis'] += f"\n\n[News Fetched]: {news_summary.splitlines()[0]}..."

            # Validate required fields
            if "is_chart" in result and not result["is_chart"]:
                return result
            
            required_fields = ["patterns", "sentiment", "confidence", "recommendation", "analysis"]
            for field in required_fields:
                if field not in result:
                    result[field] = "Unknown" if field != "confidence" else 0.5
            
            return result
            
        except Exception as e:
            return {
                "patterns": ["Error"],
                "sentiment": "Neutral",
                "confidence": 0.0,
                "recommendation": "Analysis failed.",
                "analysis": f"JSON Error: {str(e)}"
            }
            
    except Exception as e:
        return {
            "patterns": ["Error"],
            "sentiment": "Neutral",
            "confidence": 0.0,
            "recommendation": "Analysis failed.",
            "analysis": f"System Error: {str(e)}"
        }

@app.get("/api/ict_analysis")
def get_ict_data(ticker: str = "^NSEI", period: str = "60d"):
    """
    Fetch Smart Money Concepts (ICT) analysis: FVGs, Swings, Order Blocks.
    """
    from backend.ict_smart_money import get_ict_analysis
    try:
        data = get_ict_analysis(ticker, period=period)
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/quant_analysis")
def get_quant_data(ticker: str = "^NSEI", period: str = "1y"):
    """
    Fetch Advanced Quant Analysis: Regime Detection (Wasserstein), A-Vol, Unsupervised State.
    """
    from backend.quant_engine import get_quant_analysis
    try:
        data = get_quant_analysis(ticker, period=period)
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/chat_analysis")
async def chat_with_analysis(
    context: str = Form(...),
    question: str = Form(...),
    file: UploadFile = File(None)
):
    """
    Follow-up chat with the AI. Supports optional image upload for context.
    Using Form data to allow file upload alongside text.
    """
    try:
        prompt = f"""
        You are an expert financial analyst assistant. 
        
        Previous Analysis Context:
        {context}
        
        User Question: {question}
        
        Answer the user's question concisely based on the context provided.
        If an image is attached, the user is referring to it in their question.
        """
        
        image = None
        if file:
            contents = await file.read()
            image = Image.open(io.BytesIO(contents))
            print("Chat: Image attached to message.")
        
        response = generate_content_with_fallback(prompt, image)
        return {"status": "success", "answer": response.text}

    except Exception as e:
        return {"status": "error", "message": str(e)}

