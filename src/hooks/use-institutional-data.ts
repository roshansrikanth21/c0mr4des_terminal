
import { useState, useEffect } from 'react';
import axios from 'axios';

// API Base URL (adjust if needed)
const API_BASE = '/api/dashboard';

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
                // Fetch in parallel, but tolerate partial failures.
                const [riskRes, strategyRes, timingRes, greeksRes] = await Promise.allSettled([
                    axios.get(`${API_BASE}/market_analysis?ticker=${ticker}`),
                    axios.get(`${API_BASE}/strategy_performance`),
                    axios.get(`${API_BASE}/summary?ticker=${ticker}`),
                    axios.get(`${API_BASE}/options_chain?ticker=${ticker}`)
                ]);

                if (riskRes.status === 'fulfilled') {
                    setRiskData(riskRes.value.data.risk_forecast || null);
                }

                if (strategyRes.status === 'fulfilled') {
                    setStrategyData(strategyRes.value.data || null);
                }

                if (timingRes.status === 'fulfilled') {
                    setTimingData(timingRes.value.data.market_status || null);
                }

                if (greeksRes.status === 'fulfilled') {
                    setGreeksData(greeksRes.value.data || null);
                }

                const hasFailure = [riskRes, strategyRes, timingRes, greeksRes].some(r => r.status === 'rejected');
                if (hasFailure) {
                    setError("Some institutional metrics are temporarily unavailable");
                }

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
            // Refresh every 45 seconds to avoid overlapping heavy recomputations.
            const interval = setInterval(fetchData, 45000);
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
