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
    direction?: string;
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
    direction?: string;
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
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000); // 10s timeout

        try {
            const encodedTicker = encodeURIComponent(ticker);
            const res = await fetch(`/api/intraday?ticker=${encodedTicker}&interval=${interval}`, {
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            if (!res.ok) throw new Error("API Response not OK");

            const json = await res.json();
            setData(json);
        } catch (error) {
            if (error.name === 'AbortError') {
                console.error('Fetch aborted due to timeout');
            } else {
                console.error('Error fetching intraday data:', error);
            }
            // Keep previous data if available, or set error state?
            // For now, just stop loading so user sees "No signals" or stale data
        } finally {
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
            <Card className="h-full border-border/40 bg-card/20 backdrop-blur-sm animate-pulse flex flex-col items-center justify-center p-8 gap-4">
                <div className="relative">
                    <div className="w-12 h-12 border-2 border-primary/20 rounded-full" />
                    <div className="w-12 h-12 border-t-2 border-primary rounded-full absolute inset-0 animate-spin" />
                </div>
                <div className="text-center space-y-1">
                    <p className="text-[10px] font-mono font-bold uppercase tracking-[0.3em] text-primary/60">C0MR4DE_TERMINAL_Link_Establishment</p>
                    <p className="text-xs font-mono text-muted-foreground italic">Synchronizing neural feed...</p>
                </div>
            </Card>
        );
    }

    if (!data || !data.latest_signal) {
        return (
            <Card className="h-full border border-primary/20 bg-primary/5 flex flex-col items-center justify-center p-10 text-center space-y-5">
                <div className="p-4 rounded-full bg-primary/10 border border-primary/20">
                    <Clock className="w-8 h-8 text-primary/60" />
                </div>
                <div className="space-y-2">
                    <h3 className="text-sm font-mono font-black uppercase tracking-widest text-primary">Awaiting Intelligence</h3>
                    <p className="text-[10px] font-mono leading-relaxed text-muted-foreground/80 max-w-[200px] mx-auto">
                        Neural core is active and scanning global liquidity pools. Signals will materialize upon high-conviction pattern detection.
                    </p>
                </div>
                <Badge variant="outline" className="text-[9px] font-mono border-primary/20 text-primary/40 uppercase tracking-tighter">
                    Engine: C0MR4DE TERMINAL v2.0
                </Badge>
            </Card>
        );
    }

    const { latest_signal, options, market_open } = data;
    const action = latest_signal.action || 'WAIT';

    // Determine direction from API data or fall back to Option Type
    const direction = latest_signal.direction || options?.direction || (options?.type === 'CE' ? 'LONG' : 'SHORT');
    const isBullish = direction === 'LONG';

    const getCardStyle = () => {
        switch (action) {
            case 'ENTER NOW':
                return isBullish
                    ? 'border-l-8 border-l-green-500 bg-green-500/5 shadow-xl'
                    : 'border-l-8 border-l-red-500 bg-red-500/5 shadow-xl';
            case 'EXIT NOW': return 'border-l-8 border-l-orange-500 bg-orange-500/5 shadow-xl';
            case 'HOLD': return 'border-l-8 border-l-blue-500 bg-blue-500/5 shadow-lg';
            default: return 'border-l-4 border-l-gray-300 bg-gray-100/50 dark:bg-gray-800/20';
        }
    };

    const getActionBadge = () => {
        const styles = {
            'ENTER NOW': isBullish ? 'bg-green-600 text-white animate-pulse' : 'bg-red-600 text-white animate-pulse',
            'EXIT NOW': 'bg-orange-600 text-white animate-pulse',
            'HOLD': 'bg-blue-600 text-white',
            'WAIT': 'bg-gray-400 text-white'
        };
        return <Badge className={cn('text-lg px-4 py-1', styles[action as keyof typeof styles])}>{action}</Badge>;
    };

    return (
        <Card className={cn('border border-border transition-all duration-500 overflow-hidden shadow-sm',
            action === 'ENTER NOW' ? 'border-primary/50' : '',
            getCardStyle()
        )}>
            <CardHeader className="pb-3">
                <div className="flex justify-between items-start">
                    <div className="flex-1">
                        {options && action === 'ENTER NOW' ? (
                            <>
                                <CardTitle className="text-4xl font-black flex items-center gap-8">
                                    <div className={cn("p-4 rounded-xl", isBullish ? "bg-primary/10" : "bg-destructive/10")}>
                                        {isBullish ? <TrendingUp className="w-12 h-12 text-primary" /> : <TrendingDown className="w-12 h-12 text-destructive" />}
                                    </div>
                                    <div className="flex flex-col">
                                        <span className={cn("text-[10px] font-mono font-bold uppercase tracking-[0.4em] opacity-60 mb-2", isBullish ? "text-primary" : "text-destructive")}>
                                            {isBullish ? "ALLOCATE: LONG" : "ALLOCATE: SHORT"}
                                        </span>
                                        <span className="terminal-text break-all leading-tight tracking-tighter">
                                            {ticker.replace('^', '')} {options.recommended_strike} {options.type}
                                        </span>
                                    </div>
                                </CardTitle>
                                <p className="text-[10px] text-muted-foreground font-mono mt-3 opacity-50">EXPIRY: {options.expiry}</p>
                            </>
                        ) : (
                            <CardTitle className="text-xl font-mono font-bold terminal-text">
                                {ticker.replace('^', '')} » {action}
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
