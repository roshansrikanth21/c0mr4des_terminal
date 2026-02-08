import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { TrendingUp, TrendingDown, Clock, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

interface OptionsSignal {
    type: 'CE' | 'PE';
    atm_strike: number;
    otm_strike: number;
    itm_strike: number;
    recommended_strike: number;
    expiry: string;
    entry_range: string;
    stop_loss: string | null;
    target: string | null;
}

interface LatestSignal {
    time: string;
    price: number;
    action: string;
    signal: string | null;
    reason: string | null;
    confidence: number | null;
    stop_loss: number | null;
    take_profit: number | null;
}

interface OptionsSignalCardProps {
    ticker: string;
    interval?: string;
}

export function OptionsSignalCard({ ticker, interval = '5m' }: OptionsSignalCardProps) {
    const [data, setData] = useState<{
        latest_signal: LatestSignal | null;
        options: OptionsSignal | null;
        market_open: boolean;
    } | null>(null);
    const [loading, setLoading] = useState(true);

    const fetchData = async () => {
        try {
            const res = await fetch(`http://localhost:8000/api/intraday?ticker=${ticker}&interval=${interval}`);
            const json = await res.json();
            setData(json);
            setLoading(false);
        } catch (error) {
            console.error('Error fetching intraday data:', error);
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();

        // Auto-refresh every 60 seconds during market hours
        const intervalId = setInterval(fetchData, 60000);
        return () => clearInterval(intervalId);
    }, [ticker, interval]);

    if (loading) {
        return (
            <Card className="shadow-lg">
                <CardContent className="p-8 text-center">
                    <div className="animate-pulse">Loading live signals...</div>
                </CardContent>
            </Card>
        );
    }

    if (!data || !data.latest_signal) {
        return (
            <Card className="shadow-lg border-yellow-500/50">
                <CardContent className="p-8 text-center">
                    <AlertCircle className="w-12 h-12 mx-auto mb-4 text-yellow-500" />
                    <p className="text-lg font-semibold">No signals available</p>
                    <p className="text-sm text-muted-foreground mt-2">
                        {data?.market_open ? 'Waiting for entry setup...' : 'Market is closed'}
                    </p>
                </CardContent>
            </Card>
        );
    }

    const { latest_signal, options, market_open } = data;
    const action = latest_signal.action || 'WAIT';
    const isBullish = action === 'ENTER NOW' || action === 'HOLD';

    const getCardStyle = () => {
        switch (action) {
            case 'ENTER NOW': return 'border-l-8 border-l-green-500 bg-green-500/5 shadow-xl';
            case 'EXIT NOW': return 'border-l-8 border-l-red-500 bg-red-500/5 shadow-xl';
            case 'HOLD': return 'border-l-8 border-l-blue-500 bg-blue-500/5 shadow-lg';
            default: return 'border-l-4 border-l-gray-300 bg-gray-100/50 dark:bg-gray-800/20';
        }
    };

    const getActionBadge = () => {
        const styles = {
            'ENTER NOW': 'bg-green-600 text-white animate-pulse',
            'EXIT NOW': 'bg-red-600 text-white animate-pulse',
            'HOLD': 'bg-blue-600 text-white',
            'WAIT': 'bg-gray-400 text-white'
        };
        return <Badge className={cn('text-lg px-4 py-1', styles[action as keyof typeof styles])}>{action}</Badge>;
    };

    return (
        <Card className={cn('shadow-lg transition-all duration-300', getCardStyle())}>
            <CardHeader className="pb-3">
                <div className="flex justify-between items-start">
                    <div className="flex-1">
                        {options && action === 'ENTER NOW' ? (
                            <>
                                <CardTitle className="text-3xl font-bold flex items-center gap-2">
                                    {isBullish ? <TrendingUp className="w-8 h-8 text-green-600" /> : <TrendingDown className="w-8 h-8 text-red-600" />}
                                    BUY {ticker.replace('^', '')} {options.recommended_strike} {options.type}
                                </CardTitle>
                                <p className="text-sm text-muted-foreground mt-1">Expiry: {options.expiry}</p>
                            </>
                        ) : (
                            <CardTitle className="text-2xl font-bold">
                                {ticker.replace('^', '')} - {action}
                            </CardTitle>
                        )}
                    </div>
                    {getActionBadge()}
                </div>

                {/* Market Status */}
                <div className="flex items-center gap-2 mt-2">
                    <Clock className="w-4 h-4" />
                    <span className="text-xs font-mono">
                        {market_open ? (
                            <span className="text-green-600 font-semibold">● MARKET OPEN</span>
                        ) : (
                            <span className="text-red-600 font-semibold">● MARKET CLOSED</span>
                        )}
                    </span>
                    <span className="text-xs text-muted-foreground ml-2">Last Update: {latest_signal.time}</span>
                </div>
            </CardHeader>

            <CardContent className="space-y-4">
                {/* Entry Details */}
                {action === 'ENTER NOW' && options && (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div className="p-3 rounded-lg bg-blue-500/10 border border-blue-500/30">
                            <span className="text-xs uppercase text-blue-600 dark:text-blue-400 font-semibold block mb-1">
                                Spot Price
                            </span>
                            <span className="text-xl font-bold">{options.entry_range}</span>
                        </div>

                        <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30">
                            <span className="text-xs uppercase text-red-600 dark:text-red-400 font-semibold block mb-1">
                                Stop Loss
                            </span>
                            <span className="text-xl font-bold text-red-700 dark:text-red-300">
                                {options.stop_loss || 'N/A'}
                            </span>
                        </div>

                        <div className="p-3 rounded-lg bg-green-500/10 border border-green-500/30">
                            <span className="text-xs uppercase text-green-600 dark:text-green-400 font-semibold block mb-1">
                                Target
                            </span>
                            <span className="text-xl font-bold text-green-700 dark:text-green-300">
                                {options.target || 'N/A'}
                            </span>
                        </div>

                        <div className="p-3 rounded-lg bg-purple-500/10 border border-purple-500/30">
                            <span className="text-xs uppercase text-purple-600 dark:text-purple-400 font-semibold block mb-1">
                                Confidence
                            </span>
                            <span className="text-xl font-bold text-purple-700 dark:text-purple-300">
                                {latest_signal.confidence ? `${(latest_signal.confidence * 100).toFixed(0)}%` : 'N/A'}
                            </span>
                        </div>
                    </div>
                )}

                {/* Strike Options */}
                {options && action === 'ENTER NOW' && (
                    <div className="mt-4 p-4 bg-secondary/30 rounded-lg border border-border">
                        <p className="text-xs font-semibold text-muted-foreground uppercase mb-2">Strike Options:</p>
                        <div className="grid grid-cols-3 gap-2">
                            <div className="text-center p-2 rounded bg-background/50">
                                <span className="text-xs text-muted-foreground block">ITM</span>
                                <span className="font-bold">{options.itm_strike}</span>
                            </div>
                            <div className="text-center p-2 rounded bg-green-500/20 border-2 border-green-500">
                                <span className="text-xs text-green-600 dark:text-green-400 block font-semibold">ATM (Recommended)</span>
                                <span className="font-bold text-lg">{options.atm_strike}</span>
                            </div>
                            <div className="text-center p-2 rounded bg-background/50">
                                <span className="text-xs text-muted-foreground block">OTM</span>
                                <span className="font-bold">{options.otm_strike}</span>
                            </div>
                        </div>
                    </div>
                )}

                {/* Reason */}
                {latest_signal.reason && (
                    <div className="mt-4 p-3 bg-secondary/20 rounded-lg border-l-4 border-l-primary">
                        <p className="text-sm">
                            <span className="font-semibold">Reason:</span> {latest_signal.reason}
                        </p>
                    </div>
                )}

                {/* Current Position Info */}
                {action === 'HOLD' && latest_signal.stop_loss && (
                    <div className="mt-4 grid grid-cols-2 gap-3">
                        <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30">
                            <span className="text-xs uppercase text-red-600 dark:text-red-400 font-semibold block mb-1">
                                Trailing Stop
                            </span>
                            <span className="text-lg font-bold text-red-700 dark:text-red-300">
                                ₹{latest_signal.stop_loss.toFixed(2)}
                            </span>
                        </div>
                        <div className="p-3 rounded-lg bg-green-500/10 border border-green-500/30">
                            <span className="text-xs uppercase text-green-600 dark:text-green-400 font-semibold block mb-1">
                                Target
                            </span>
                            <span className="text-lg font-bold text-green-700 dark:text-green-300">
                                ₹{latest_signal.take_profit?.toFixed(2) || 'N/A'}
                            </span>
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
