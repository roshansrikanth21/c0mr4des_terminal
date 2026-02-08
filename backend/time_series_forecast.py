import numpy as np
import pandas as pd
import yfinance as yf
from statsmodels.tsa.statespace.sarimax import SARIMAX
from arch import arch_model

def advanced_forecast(ticker, forecast_days=5):
    """
    Combined SARIMA (trend/seasonality) + GARCH (volatility) model.
    Particularly useful for Nifty/Sensex intraday patterns.
    """
    try:
        # Fetch Data - 3 months of 15m data provides good granularity for recent patterns
        # Note: yfinance limits 15m data to 60 days usually. Adjusting to '59d' or '1mo' as safer.
        df = yf.download(ticker, period="1mo", interval="15m", progress=False)
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        if len(df) < 200:
            return {"error": "Not enough data for SARIMA/GARCH (Need >200 points)"}

        prices = df['Close']
        
        # --- 1. SARIMA for Price Mean ---
        # Order (1,1,1) is a standard starting point for non-stationary financial data
        # Seasonal Order (1,1,1,75) - 75 candles approx per day in 15m (375 mins / 5?? No, 6.25 hrs * 4 = 25 candles/hr * 6 = 150... wait)
        # Market open 9:15 to 3:30 = 6 hours 15 mins = 375 mins.
        # 15m candles: 375 / 15 = 25 candles per day.
        # So seasonality is 25.
        
        try:
            model_sarima = SARIMAX(prices, order=(1,1,1), seasonal_order=(1,1,1,25))
            results_sarima = model_sarima.fit(disp=False)
            price_forecast = results_sarima.forecast(steps=forecast_days * 25) # Forecast 'days' worth of 15m candles
        except Exception as e:
            return {"error": f"SARIMA Fit Failed: {str(e)}"}

        # --- 2. GARCH for Volatility ---
        returns = prices.pct_change().dropna() * 100
        
        try:
            model_garch = arch_model(returns, vol='Garch', p=1, q=1)
            results_garch = model_garch.fit(disp='off')
            vol_forecast = results_garch.forecast(horizon=forecast_days * 25)
        except Exception as e:
            return {"error": f"GARCH Fit Failed: {str(e)}"}
        
        # Get the final forecasted values (end of horizon)
        final_price_mean = price_forecast.iloc[-1]
        final_vol_variance = vol_forecast.variance.values[-1, -1]
        
        # Confidence Bands (95%)
        # Volatility is in variance of percentage returns. Need to convert to price scale.
        # Approx: Price +/- 1.96 * (Price * Volatility_StdDev / 100)
        vol_std_dev = np.sqrt(final_vol_variance)
        
        upper_band = final_price_mean * (1 + 1.96 * vol_std_dev / 100)
        lower_band = final_price_mean * (1 - 1.96 * vol_std_dev / 100)
        
        return {
            "forecast_horizon_days": forecast_days,
            "projected_close": round(final_price_mean, 2),
            "volatility_forecast_annualized": f"{round(vol_std_dev * np.sqrt(252*25), 1)}%", # Approx annualization
            "confidence_band_95": {
                "upper": round(upper_band, 2),
                "lower": round(lower_band, 2)
            },
            "model_status": "Converged"
        }

    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    print(advanced_forecast("^NSEI", forecast_days=1))
