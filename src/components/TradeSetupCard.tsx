import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ArrowRight, TrendingUp, TrendingDown, AlertCircle, CheckCircle2, Target, Shield, DollarSign, Activity } from 'lucide-react';
import { formatCurrency, MARKETS } from '@/lib/market-config';
import { cn } from '@/lib/utils';

interface TradeSetupProps {
    ticker: string;
}

export function TradeSetupCard({ ticker }: TradeSetupProps) {
    const [data, setData] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    // We fetch Daily data for the "Official" Trade Setup
    useEffect(() => {
        const fetchSetup = async () => {
            setLoading(true);
            try {
                const res = await fetch(`http://localhost:8000/api/history?ticker=${ticker}&period=1y&interval=1d`);
                const json = await res.json();
                if (json && json.length > 0) {
                    // Get the LAST data point
                    setData(json[json.length - 1]);
                }
            } catch (e) {
                console.error("Failed to fetch setup", e);
            } finally {
                setLoading(false);
            }
        };
        fetchSetup();
    }, [ticker]);

    if (loading || !data) return (
        <Card className="border-border/50 shadow-sm animate-pulse h-[180px]">
            <CardHeader><div className="h-6 w-32 bg-secondary rounded"></div></CardHeader>
            <CardContent><div className="h-24 bg-secondary/30 rounded"></div></CardContent>
        </Card>
    );

    const action = data.action || 'WAIT';
    const confidence = data.confidence || 0;
    const isBullish = action === 'ENTER NOW' || action === 'HOLD';
    const region = MARKETS.find(m => m.ticker === ticker)?.region || 'IN';

    // Helper to determine card style based on action
    const getCardStyle = () => {
        switch (action) {
            case 'ENTER NOW': return 'border-l-4 border-l-green-500 bg-green-500/5';
            case 'EXIT NOW': return 'border-l-4 border-l-red-500 bg-red-500/5';
            case 'HOLD': return 'border-l-4 border-l-blue-500 bg-blue-500/5';
            default: return 'border-l-4 border-l-gray-300 bg-gray-100/50 dark:bg-gray-800/20';
        }
    };

    const getActionColor = () => {
        switch (action) {
            case 'ENTER NOW': return 'text-green-600 dark:text-green-400';
            case 'EXIT NOW': return 'text-red-600 dark:text-red-400';
            case 'HOLD': return 'text-blue-600 dark:text-blue-400';
            default: return 'text-muted-foreground';
        }
    };

    return (
        <Card className={cn("shadow-md relative overflow-hidden transition-all duration-300", getCardStyle())}>
            <CardHeader className="pb-2 pt-4 flex flex-row items-center justify-between space-y-0">
                <div className="flex items-center gap-2">
                    <Activity className={cn("w-5 h-5", getActionColor())} />
                    <span className={cn("text-lg font-bold font-mono tracking-tight", getActionColor())}>
                        ACTION: {action}
                    </span>
                </div>
                {action === 'ENTER NOW' && (
                    <Badge className="bg-green-600 hover:bg-green-700 animate-pulse">HIGH CONVICTION</Badge>
                )}
            </CardHeader>

            <CardContent className="grid grid-cols-2 md:grid-cols-4 gap-4 py-4">

                {/* PRICE / ENTRY */}
                <div className="flex flex-col space-y-1 p-2 rounded-lg bg-background/50 border border-border/50">
                    <span className="text-[10px] uppercase text-muted-foreground font-semibold flex items-center gap-1">
                        <DollarSign className="w-3 h-3" /> Current Price
                    </span>
                    <span className="text-xl font-bold tracking-tight">
                        {formatCurrency(data.price, region)}
                    </span>
                    {action === 'ENTER NOW' && (
                        <span className="text-xs text-green-600 font-medium">Entry Zone</span>
                    )}
                </div>

                {/* STOP LOSS */}
                <div className="flex flex-col space-y-1 p-2 rounded-lg bg-red-500/10 border border-red-500/20 opacity-90">
                    <span className="text-[10px] uppercase text-red-600 dark:text-red-400 font-semibold flex items-center gap-1">
                        <Shield className="w-3 h-3" /> Stop Loss
                    </span>
                    <span className="text-lg font-bold text-red-700 dark:text-red-300">
                        {formatCurrency(data.stop_loss || data.price * 0.95, region)}
                    </span>
                    <span className="text-[10px] text-red-600/80">
                        Risk: {data.stop_loss ? ((1 - data.stop_loss / data.price) * 100).toFixed(1) : '5.0'}%
                    </span>
                </div>

                {/* TAKE PROFIT */}
                <div className="flex flex-col space-y-1 p-2 rounded-lg bg-green-500/10 border border-green-500/20 opacity-90">
                    <span className="text-[10px] uppercase text-green-600 dark:text-green-400 font-semibold flex items-center gap-1">
                        <Target className="w-3 h-3" /> Target (2:1)
                    </span>
                    <span className="text-lg font-bold text-green-700 dark:text-green-300">
                        {formatCurrency(data.take_profit || data.price * 1.05, region)}
                    </span>
                    <span className="text-[10px] text-green-600/80">
                        Gain: {data.take_profit ? ((data.take_profit / data.price - 1) * 100).toFixed(1) : '5.0'}%
                    </span>
                </div>

                {/* REASON / CONFIDENCE */}
                <div className="flex flex-col space-y-1 p-2 rounded-lg bg-secondary/50 border border-border/50">
                    <span className="text-[10px] uppercase text-muted-foreground font-semibold">
                        Intelligence
                    </span>
                    {action === 'WAIT' ? (
                        <span className="text-sm font-medium text-muted-foreground mt-1">
                            No clear setup. Market is ranging or consolidating.
                        </span>
                    ) : (
                        <>
                            <div className="flex items-center gap-2">
                                <div className="h-2 flex-1 bg-gray-200 rounded-full overflow-hidden">
                                    <div
                                        className={cn("h-full rounded-full", isBullish ? "bg-green-500" : "bg-red-500")}
                                        style={{ width: `${(data.confidence || 0.7) * 100}%` }}
                                    />
                                </div>
                                <span className="text-xs font-bold">{(data.confidence * 100)?.toFixed(0) || 75}%</span>
                            </div>
                            <span className="text-xs text-muted-foreground truncate" title={data.reason || "Algo Signal"}>
                                {data.reason || "Algorithm Signal"}
                            </span>
                        </>
                    )}
                </div>

            </CardContent>
        </Card>
    );
}
