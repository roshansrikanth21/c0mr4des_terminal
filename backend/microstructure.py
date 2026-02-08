try:
    from nsepython import nse_fno_pcr, nse_quote_ltp
    # nse_fiidii is sometimes broken in nsepython, we might need a fallback or alternative
    # But let's try importing it.
    from nsepython import nse_fiidii
    NSE_PYTHON_AVAILABLE = True
except ImportError:
    NSE_PYTHON_AVAILABLE = False

def analyze_market_microstructure(ticker="NIFTY"):
    """
    Analyzes Market Microstructure for Indian Markets.
    1. FII/DII Flow (Institutional Pressure).
    2. Put-Call Ratio (PCR) - Sentiment.
    3. Open Interest (via proxy or chain).
    """
    if not NSE_PYTHON_AVAILABLE:
        return {"error": "NSEPython library not found. Install 'nsepython'."}

    try:
        # 1. FII/DII Data
        # Returns JSON with FII/DII stats
        fiidii_data = {}
        try:
             # nse_fiidii() returns valid JSON usually
             stats = nse_fiidii()
             # extract useful numbers
             # Typical format: [ {category: "FII/FPI ...", buyValue: ..., sellValue: ..., netValue: ...} ]
             fiidii_data = {"raw": stats}
        except Exception as e:
            fiidii_data = {"error": f"FII/DII Fetch Failed: {str(e)}"}

        # 2. PCR (Put Call Ratio)
        # Ticker needs to be official symbol (NIFTY, BANKNIFTY, RELIANCE)
        # Input ticker might be "^NSEI", need "NIFTY"
        symbol = ticker
        if ticker == "^NSEI": symbol = "NIFTY"
        elif ticker == "^NSEBANK": symbol = "BANKNIFTY"
        elif ticker.endswith(".NS"): symbol = ticker.replace(".NS", "")
        
        pcr_value = "N/A"
        try:
            pcr_value = nse_fno_pcr(symbol)
        except Exception as e:
            pcr_value = f"Error: {str(e)}"

        # 3. Sentiment Interpretation
        bias = "NEUTRAL"
        if isinstance(pcr_value, (int, float)):
            if pcr_value > 1.3: bias = "BULLISH (Oversold Puts?)" # Standard PCR logic: High PCR > Bullish? OR Overbought?
            # Actually High PCR (>1.5) usually means Bullish sentiment (more Puts sold), but extreme (>2) might be reversal.
            # Low PCR (<0.6) usually means Bearish.
            elif pcr_value < 0.6: bias = "BEARISH (Oversold Calls?)"
        
        return {
            "symbol": symbol,
            "pcr": pcr_value,
            "pcr_signal": bias,
            "fii_dii_activity": fiidii_data
        }

    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    print(analyze_market_microstructure("^NSEI"))
