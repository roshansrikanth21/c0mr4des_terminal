# AI Market Analyser - Institutional Trading System

Professional-grade market analysis platform for Indian Equities and Options, featuring institutional quant models, ICT Smart Money concepts, and AI-driven visual analysis.

## 🚀 Quick Start (Windows)

1. **Setup Core**:
   ```bash
   # Create virtual environment if needed
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r backend/requirements.txt
   npm install
   ```

2. **Configure**:
   Add your `GEMINI_API_KEY` to `backend/.env`.

3. **Launch**:
   Double-click `run_system.bat` to start the Backend, Frontend, and Live Assistant.

## 📊 System Components

- **Backend API (Port 8000)**: FastAPI server with OU Process, MST, and ICT logic.
- **Frontend Dashboard (Port 3000)**: React interface with real-time charts and signals.
- **Live Trading Assistant**: Background market monitor and signal generator.
- **Institutional Quant Engine**: Wasserstein Drift, Monte Carlo, and Bayesian Inference.

## 📱 Access Points

- **Dashboard**: [http://localhost:3000](http://localhost:3000)
- **API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

## 🔧 Features Verified

- [x] **ICT/SMC Engine**: FVG, Order Blocks, BOS detection.
- [x] **Quant Core**: Wasserstein Regime Shifts, Entropy, A-Vol.
- [x] **Robust Data**: yfinance MultiIndex handling and 7-day retry logic.
- [x] **Dark Mode**: Persistent theme toggle in the UI.
- [x] **Broker Ready**: Angel One integration layer implemented.

---
*For detailed backtesting or docker deployment, see the source code scripts or docker-compose.yml.*