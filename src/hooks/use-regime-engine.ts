import { useState, useEffect } from 'react';
import { MarketRegime, RegimeStatus } from '@/types/trading';

// This URL points to your Python Backend
const API_URL = 'http://localhost:8000/api/regime';

interface UseRegimeEngineReturn extends RegimeStatus {
  isLoading: boolean;
  vitals: {
    vix: number;
    rsi: number;
    adx: number;
  };
}

export function useRegimeEngine(ticker: string = '^NSEI'): UseRegimeEngineReturn {
  const [data, setData] = useState<UseRegimeEngineReturn>({
    regime: 'Range-bound', // Default safe starting state or use a specific 'Initializing' if types allow
    confidence: 0,
    isTradeAllowed: false,
    reason: 'Initializing System...',
    isLoading: true,
    vitals: { vix: 0, rsi: 0, adx: 0 }
  });

  useEffect(() => {
    // Reset state when ticker changes to show loading
    setData(prev => ({ ...prev, isLoading: true, reason: `Connecting to ${ticker}...` }));

    const fetchData = async () => {
      try {
        // Encode ticker to handle symbols like ^NSEI safely in URL
        const encodedTicker = encodeURIComponent(ticker);
        const response = await fetch(`${API_URL}?ticker=${encodedTicker}`);
        if (!response.ok) throw new Error('Network response was not ok');

        const json = await response.json();

        // Validate that the returned regime is a valid MarketRegime
        const regime = json.regime as MarketRegime;

        setData({
          regime,
          confidence: json.confidence,
          isTradeAllowed: json.is_trade_allowed,
          reason: json.reason,
          isLoading: false,
          vitals: json.vitals || { vix: 0, rsi: 0, adx: 0 }
        });
      } catch (error) {
        console.error("Failed to connect to Edge-Ops Brain:", error);
        // Could implement a specific error state here
      }
    };

    // Fetch immediately, then every 5 seconds
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [ticker]); // Re-run when ticker changes

  return data;
}