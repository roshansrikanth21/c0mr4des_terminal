
import { useState, useEffect } from 'react';
import axios from 'axios';

// API Base URL (adjust if needed)
const API_BASE = 'http://localhost:8000/api/dashboard';

export function useInstitutionalData(ticker: string) {
    const [riskData, setRiskData] = useState<any>(null);
    const [strategyData, setStrategyData] = useState<any>(null);
    const [timingData, setTimingData] = useState<any>(null);
    const [greeksData, setGreeksData] = useState<any>(null);

    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchData = async () => {
            setIsLoading(true);
            setError(null);
            try {
                // Fetch in parallel for speed
                const [riskRes, strategyRes, timingRes, greeksRes] = await Promise.all([
                    axios.get(`${API_BASE}/market_analysis?ticker=${ticker}`),
                    axios.get(`${API_BASE}/strategy_performance`),
                    axios.get(`${API_BASE}/summary`),
                    axios.get(`${API_BASE}/options_chain?ticker=${ticker}`)
                ]);

                setRiskData(riskRes.data.risk_forecast);
                setStrategyData(strategyRes.data);
                setTimingData(timingRes.data.market_status);
                setGreeksData(greeksRes.data);

            } catch (err) {
                console.error("Failed to fetch institutional data:", err);
                setError("Failed to load institutional metrics");
                // Don't block UI, just leave data null
            } finally {
                setIsLoading(false);
            }
        };

        if (ticker) {
            fetchData();
            // Refresh every 30 seconds
            const interval = setInterval(fetchData, 30000);
            return () => clearInterval(interval);
        }
    }, [ticker]);

    return {
        riskData,
        strategyData,
        timingData,
        greeksData,
        isLoading,
        error
    };
}
