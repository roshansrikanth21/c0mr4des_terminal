import pandas as pd
import numpy as np
from typing import Dict

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

def analyze_intraday_vbp(df: pd.DataFrame, bins: int = 20) -> Dict:
    """
    Calculates Intraday Volume By Price (VBP) and Point of Control (POC).
    Essential for identifying 'Hidden Support/Resistance' in Nifty/BankNifty.
    """
    if df.empty or 'volume' not in [c.lower() for c in df.columns]:
        return {"error": "Volume data unavailable for VBP"}

    df_copy = df.copy()
    df_copy.columns = [c.lower() for c in df_copy.columns]
    
    price_min = df_copy['low'].min()
    price_max = df_copy['high'].max()
    
    if price_min == price_max:
        return {"error": "Price range zero"}

    price_bins = np.linspace(price_min, price_max, bins + 1)
    df_copy['bin'] = pd.cut(df_copy['close'], bins=price_bins)
    
    vbp = df_copy.groupby('bin', observed=True)['volume'].sum()
    
    poc_bin = vbp.idxmax()
    poc_price = float(poc_bin.mid)
    
    hvn_nodes = vbp.sort_values(ascending=False).head(3)
    nodes = []
    for b, vol in hvn_nodes.items():
        nodes.append({
            "price": float(b.mid),
            "volume_percent": float(vol / vbp.sum() * 100) if vbp.sum() > 0 else 0
        })

    return {
        "poc": poc_price,
        "hvn": nodes,
        "total_volume": float(vbp.sum()),
        "distribution": {str(b): float(v) for b, v in vbp.items()}
    }

if __name__ == "__main__":
    print(analyze_market_microstructure("^NSEI"))
