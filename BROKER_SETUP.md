# Broker API Setup Guide

This guide explains how to configure broker APIs (Angel One, Zerodha, Groww) for enhanced market data and order flow analysis.

## Overview

The system now supports **broker-level data providers** that give you:
- ✅ **Real-time, accurate OHLCV data** (faster than Yahoo Finance)
- ✅ **Level 2 Order Book** (bid/ask depth)
- ✅ **Institutional Flow Detection** (large orders, absorption, delta)
- ✅ **Option Chain Data** (for options trading)
- ✅ **Order Flow Analysis** (using concepts from Varsity & Order Flow Trading books)

## Why Use Broker APIs?

1. **Speed & Accuracy**: Broker APIs provide real-time data directly from exchanges
2. **Order Flow Depth**: Level 2 data shows where institutions are positioned
3. **Better Entry Timing**: Detect absorption, large orders, and momentum shifts
4. **Options Data**: Access to full option chains with OI, IV, Greeks

---

## 1. Angel One SmartAPI Setup

### Step 1: Get API Credentials

1. Log in to [Angel One](https://www.angelone.in/)
2. Go to **Settings → API → SmartAPI**
3. Generate API Key
4. Note down:
   - **API Key**
   - **Client ID** (your Angel One user ID)
   - **Password** (your Angel One password)
   - **TOTP Secret** (for 2FA)

### Step 2: Install Package

```bash
pip install smartapi-python pyotp
```

### Step 3: Configure Environment Variables

Add to your `.env` file:

```env
# Angel One SmartAPI
ANGEL_API_KEY=your_api_key_here
ANGEL_CLIENT_ID=your_client_id
ANGEL_PASSWORD=your_password
ANGEL_TOTP_KEY=your_totp_secret
```

### Step 4: Test Connection

The system will automatically try to connect when you run it. Check logs for:
```
✓ Angel One data provider enabled
Connected to Angel One for market data
```

---

## 2. Zerodha Kite Connect Setup

### Step 1: Create Kite Connect App

1. Log in to [Zerodha Kite](https://kite.zerodha.com/)
2. Go to **Developer → My Apps**
3. Create a new app
4. Note down:
   - **API Key**
   - **API Secret**

### Step 2: Generate Access Token

**Option A: Using Kite Connect Login Flow (Recommended for Production)**

```python
from kiteconnect import KiteConnect

kite = KiteConnect(api_key="your_api_key")
print(kite.login_url())  # Visit this URL to authorize
# After authorization, you'll get a request_token
# Exchange it for access_token:
data = kite.generate_session("request_token", api_secret="your_api_secret")
access_token = data["access_token"]
```

**Option B: Manual Token Generation**

1. Visit: `https://kite.zerodha.com/connect/login?api_key=YOUR_API_KEY`
2. Authorize the app
3. Copy the `request_token` from the redirect URL
4. Exchange it for `access_token` using the API

### Step 3: Install Package

```bash
pip install kiteconnect
```

### Step 4: Configure Environment Variables

Add to your `.env` file:

```env
# Zerodha Kite Connect
ZERODHA_API_KEY=your_api_key
ZERODHA_API_SECRET=your_api_secret
ZERODHA_ACCESS_TOKEN=your_access_token
```

**Note**: Access tokens expire. You may need to regenerate them periodically or implement auto-refresh.

### Step 5: Test Connection

Check logs for:
```
✓ Zerodha Kite data provider enabled
Connected to Zerodha Kite for market data
```

---

## 3. Groww API (Placeholder)

**Note**: Groww doesn't currently have a public API. This provider is a placeholder for future integration.

When Groww releases an API:
1. Follow their documentation
2. Add credentials to `.env`
3. The system will automatically detect and use it

---

## 4. How It Works

### Provider Priority

The system tries providers in this order:

1. **Angel One** (if configured) - Best for Indian markets
2. **Zerodha Kite** (if configured) - Excellent order book depth
3. **Yahoo Finance** (fallback) - Always available
4. **Alpha Vantage** (fallback) - If API key configured
5. **Synthetic Data** (last resort) - For testing only

### Automatic Fallback

If a broker provider fails or isn't configured, the system automatically falls back to Yahoo Finance. Your trading system continues to work!

### Data Caching

- Market data is cached for **5 minutes** to reduce API calls
- Order book data is fetched fresh each time (real-time)

---

## 5. Enhanced Order Flow Analysis

Once broker APIs are configured, you get access to:

### Institutional Flow Detection

```python
from backend.institutional_order_flow import InstitutionalOrderFlowAnalyzer

analyzer = InstitutionalOrderFlowAnalyzer("^NSEI")
order_book = await async_market_data_service.get_order_book("^NSEI")
flow_analysis = analyzer.analyze_comprehensive_flow(order_book, price_data)
```

**Features**:
- ✅ **Bid/Ask Imbalance**: Detect buying vs selling pressure
- ✅ **Order Flow Delta**: Volume at bid - volume at ask
- ✅ **Large Order Detection**: Find institutional footprints (₹10L+ orders)
- ✅ **Absorption Detection**: Identify where large orders are being absorbed
- ✅ **Momentum Shifts**: Detect when order flow changes direction

### Using in Trading Decisions

The `OrderFlowAnalyzer` automatically uses broker data when available:

```python
from backend.order_flow import OrderFlowAnalyzer

analyzer = OrderFlowAnalyzer("^NSEI")
# Enhanced analysis with broker data (if configured)
entry_signal = await analyzer.get_enhanced_entry_recommendation(df)
```

**Output includes**:
- Traditional volume profile (VPOC, Value Area)
- Institutional flow signals
- Large order alerts
- Absorption zones
- Order flow delta trends

---

## 6. Troubleshooting

### "Angel One provider not configured"

**Solution**: Check that all 4 environment variables are set:
- `ANGEL_API_KEY`
- `ANGEL_CLIENT_ID`
- `ANGEL_PASSWORD`
- `ANGEL_TOTP_KEY`

### "Zerodha provider not configured"

**Solution**: Check that all 3 environment variables are set:
- `ZERODHA_API_KEY`
- `ZERODHA_API_SECRET`
- `ZERODHA_ACCESS_TOKEN`

**Note**: Access tokens expire. Regenerate if connection fails.

### "Order book fetch failed"

**Possible causes**:
1. Broker API not connected (check credentials)
2. Symbol not found in broker's instrument list
3. API rate limits exceeded

**Solution**: System falls back to basic volume profile analysis. Check broker API status.

### "SmartAPI not installed"

**Solution**: 
```bash
pip install smartapi-python pyotp
```

### "KiteConnect not installed"

**Solution**:
```bash
pip install kiteconnect
```

---

## 7. Best Practices

### Security

1. **Never commit `.env` file** to version control
2. **Use environment variables** for all credentials
3. **Rotate API keys** periodically
4. **Use read-only API keys** if available (for data-only access)

### Performance

1. **Data is cached** for 5 minutes - don't worry about excessive API calls
2. **Order book data** is fetched fresh (real-time) - use sparingly
3. **Use broker providers** for intraday trading (faster, more accurate)
4. **Use Yahoo Finance** for backtesting (free, historical data)

### Cost

- **Angel One**: Free for data access (trading fees apply for orders)
- **Zerodha**: Free for data access (trading fees apply for orders)
- **Yahoo Finance**: Free (rate limits may apply)

---

## 8. Integration Examples

### Example 1: Get Real-Time Order Book

```python
from backend.services.market_data_service import async_market_data_service
import asyncio

async def get_order_book():
    order_book = await async_market_data_service.get_order_book("^NSEI")
    print(f"Bid levels: {len(order_book['bid'])}")
    print(f"Ask levels: {len(order_book['ask'])}")
    print(f"LTP: ₹{order_book['ltp']}")

asyncio.run(get_order_book())
```

### Example 2: Enhanced Entry Signal

```python
from backend.order_flow import OrderFlowAnalyzer
import pandas as pd

analyzer = OrderFlowAnalyzer("^NSEI")
df = pd.DataFrame(...)  # Your price data

# Enhanced analysis with broker order book
signal = await analyzer.get_enhanced_entry_recommendation(df)

if signal['action'] == 'ENTRY':
    print(f"Entry Signal: {signal['confidence']:.1%} confidence")
    print(f"Reasons: {signal.get('signals', [])}")
    if 'institutional_flow' in signal:
        print(f"Institutional Flow: {signal['institutional_flow']['final_signal']}")
```

### Example 3: Detect Large Orders

```python
from backend.institutional_order_flow import InstitutionalOrderFlowAnalyzer

analyzer = InstitutionalOrderFlowAnalyzer("^NSEI")
order_book = await async_market_data_service.get_order_book("^NSEI")

large_orders = analyzer.detect_large_orders(order_book)
for order in large_orders:
    if 'INSTITUTIONAL' in order['type']:
        print(f"⚠️ Institutional {order['side']} order: ₹{order['value']:,.0f} at ₹{order['price']}")
```

---

## 9. References

- **Angel One SmartAPI**: [Documentation](https://smartapi.angelone.in/)
- **Zerodha Kite Connect**: [Documentation](https://kite.trade/docs/connect/v3/)
- **Zerodha Varsity**: [Market Profile & Order Flow](https://zerodha.com/varsity/)
- **Order Flow Trading Books**: Concepts from "Order Flow Trading" by Trader Dale

---

## 10. Support

If you encounter issues:
1. Check broker API status pages
2. Verify credentials in `.env`
3. Check system logs for detailed error messages
4. System automatically falls back to Yahoo Finance if broker APIs fail

**Remember**: Broker APIs are optional. Your system works perfectly fine with Yahoo Finance as the data source!
