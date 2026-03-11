import { useState, useEffect, useCallback } from 'react';

const API_BASE = '/api/broker';

export interface Position {
    symbol: string;
    quantity: number;
    avg_price: number;
    ltp: number;
    pnl: number;
    pnl_percent: number;
    value: number;
}

export interface Portfolio {
    balance: number;
    used_margin: number;
    total_value: number;
    pnl: number;
    positions: Position[];
    orders: any[]; // Define specific order type if needed
}

export interface BrokerStatus {
    connected: boolean;
    mode: 'PAPER' | 'ANGEL_ONE' | 'NONE';
    last_updated: string;
    balance: number;
    pnl?: number;
}

export function useBroker() {
    const [status, setStatus] = useState<BrokerStatus>({
        connected: false,
        mode: 'NONE',
        last_updated: '',
        balance: 0
    });

    const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Fetch Status
    const fetchStatus = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/status`);
            const json = await res.json();
            // Support both new and legacy backend payloads.
            const modeFromBroker: BrokerStatus['mode'] = (() => {
                if (json.mode === 'PAPER' || json.mode === 'ANGEL_ONE' || json.mode === 'NONE') return json.mode;
                if (json.broker === 'PaperBroker') return 'PAPER';
                if (json.broker === 'AngelOneBroker') return 'ANGEL_ONE';
                return 'NONE';
            })();

            setStatus({
                connected: Boolean(json.connected ?? (json.status === 'CONNECTED')),
                mode: modeFromBroker,
                last_updated: json.last_updated || new Date().toISOString(),
                balance: Number(json.balance || 0),
                pnl: Number(json.pnl || 0),
            });
        } catch (err) {
            console.error("Broker Status Error:", err);
            // Don't set global error for background polls
        }
    }, []);

    // Fetch Portfolio
    const fetchPortfolio = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/portfolio`);
            const json = await res.json();
            if (json?.positions && json?.orders !== undefined) {
                setPortfolio({
                    balance: Number(json.balance || 0),
                    used_margin: Number(json.used_margin || 0),
                    total_value: Number(json.total_value || 0),
                    pnl: Number(json.pnl || 0),
                    positions: json.positions || [],
                    orders: json.orders || []
                });
            }
        } catch (err) {
            console.error("Portfolio Error:", err);
        }
    }, []);

    // Connect
    const connect = async (mode: 'PAPER' | 'ANGEL_ONE') => {
        setLoading(true);
        setError(null);
        try {
            const res = await fetch(`${API_BASE}/connect`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode })
            });
            const json = await res.json();

            if (json.status === 'success') {
                await fetchStatus();
                await fetchPortfolio();
                return true;
            } else {
                setError(json.message || 'Connection failed');
                return false;
            }
        } catch (err: any) {
            setError(err.message || 'Network error');
            return false;
        } finally {
            setLoading(false);
        }
    };

    // Place Order
    const placeOrder = async (order: {
        symbol: string;
        action: 'BUY' | 'SELL';
        quantity: number;
        type?: 'MARKET' | 'LIMIT';
        price?: number;
    }) => {
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/order`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(order)
            });
            const json = await res.json();

            if (json.status === 'success' || json.status === 'SUCCESS') {
                await fetchPortfolio(); // Refresh portfolio immediately
                await fetchStatus();    // Refresh balance
                return { success: true, data: json };
            } else {
                return { success: false, message: json.message || 'Order rejected' };
            }
        } catch (err: any) {
            return { success: false, message: err.message };
        } finally {
            setLoading(false);
        }
    };

    // Initial Load & Polling
    useEffect(() => {
        fetchStatus();
        fetchPortfolio();

        const interval = setInterval(() => {
            fetchStatus();
            fetchPortfolio();
        }, 8000); // Poll every 8 seconds for lighter load

        return () => clearInterval(interval);
    }, [fetchStatus, fetchPortfolio]);

    return {
        status,
        portfolio,
        loading,
        error,
        connect,
        placeOrder,
        refresh: () => { fetchStatus(); fetchPortfolio(); }
    };
}
