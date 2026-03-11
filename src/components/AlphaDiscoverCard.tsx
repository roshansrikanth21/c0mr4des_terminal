import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
    Zap,
    ArrowUpRight,
    ArrowDownRight,
    TrendingUp,
    TrendingDown,
    Search,
    RefreshCw,
    Activity,
    Target
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatCurrency, MarketRegion } from '@/lib/market-config';

interface AlphaPick {
    ticker: string;
    name: string;
    region: MarketRegion;
    price: number;
    signal: string;
    score: number;
    rsi: number;
    trend: string;
}

interface AlphaDiscoverCardProps {
    onSelectTicker?: (ticker: string) => void;
}

export function AlphaDiscoverCard({ onSelectTicker }: AlphaDiscoverCardProps) {
    const [picks, setPicks] = useState<AlphaPick[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [lastRefresh, setLastRefresh] = useState(new Date());

    const fetchAlpha = async () => {
        setIsLoading(true);
        try {
            const res = await fetch('/api/alpha/discover');
            const json = await res.json();
            if (json.status === 'success') {
                setPicks(json.data);
                setLastRefresh(new Date());
            }
        } catch (err) {
            console.error("Alpha discovery failed", err);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchAlpha();
        const interval = setInterval(fetchAlpha, 300000); // Check every 5 mins
        return () => clearInterval(interval);
    }, []);

    return (
        <Card className="border border-border bg-card/50 backdrop-blur-xl shadow-2xl relative overflow-hidden group">
            {/* Animated Background Glow */}
            <div className="absolute -top-24 -right-24 w-48 h-48 bg-primary/10 rounded-full blur-[80px] group-hover:bg-primary/20 transition-all duration-700" />

            <CardHeader className="pb-4 border-b border-white/5 bg-white/5">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-mono font-bold uppercase tracking-[0.2em] flex items-center gap-3">
                        <Zap className="w-4 h-4 text-primary animate-pulse" />
                        Market Alpha Discovery
                    </CardTitle>
                    <button
                        onClick={fetchAlpha}
                        disabled={isLoading}
                        className="p-1.5 rounded-md hover:bg-secondary transition-colors disabled:opacity-50"
                    >
                        <RefreshCw className={cn("w-3 h-3 text-muted-foreground", isLoading && "animate-spin")} />
                    </button>
                </div>
            </CardHeader>

            <CardContent className="p-0">
                <div className="divide-y divide-white/5">
                    {isLoading && picks.length === 0 ? (
                        <div className="p-12 flex flex-col items-center justify-center text-center space-y-4">
                            <Activity className="w-8 h-8 text-primary animate-bounce" />
                            <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest">Scanning Global Liquidity Pools...</p>
                        </div>
                    ) : (
                        picks.map((pick, i) => (
                            <div
                                key={pick.ticker}
                                onClick={() => onSelectTicker?.(pick.ticker)}
                                className="group/item flex items-center justify-between p-4 hover:bg-primary/5 transition-all cursor-pointer border-l-2 border-transparent hover:border-primary"
                            >
                                <div className="flex items-center gap-4">
                                    <div className={cn(
                                        "w-10 h-10 rounded-lg flex items-center justify-center border transition-all",
                                        pick.signal === 'BUY' || pick.signal === 'RECOVERY'
                                            ? "bg-green-500/10 border-green-500/20 text-green-500 group-hover/item:scale-110"
                                            : "bg-red-500/10 border-red-500/20 text-red-500 group-hover/item:scale-110"
                                    )}>
                                        {pick.trend === 'BULLISH' ? <TrendingUp className="w-5 h-5" /> : <TrendingDown className="w-5 h-5" />}
                                    </div>
                                    <div>
                                        <div className="flex items-center gap-2">
                                            <span className="font-black text-sm tracking-tight">{pick.name}</span>
                                            <Badge variant="outline" className="text-[8px] font-mono px-1.5 py-0 border-white/10 uppercase opacity-60">
                                                {pick.region}
                                            </Badge>
                                        </div>
                                        <p className="text-[10px] font-mono font-bold text-muted-foreground leading-none mt-1 uppercase">
                                            {formatCurrency(pick.price, pick.region)}
                                        </p>
                                    </div>
                                </div>

                                <div className="text-right flex flex-col items-end gap-1.5">
                                    <div className="flex items-center gap-2">
                                        <span className="text-[9px] font-mono text-muted-foreground uppercase font-bold tracking-tighter">Confidence</span>
                                        <span className="text-xs font-black font-mono">{pick.score}%</span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <Badge className={cn(
                                            "font-black text-[9px] px-2 py-0.5 border-none shadow-sm",
                                            pick.signal === 'BUY' ? "bg-green-500 text-white" :
                                                pick.signal === 'RECOVERY' ? "bg-cyan-500 text-white" :
                                                    pick.signal === 'SELL' ? "bg-red-500 text-white" : "bg-yellow-600 text-white"
                                        )}>
                                            {pick.signal}
                                        </Badge>
                                        <div className="w-1.5 h-1.5 rounded-full bg-primary/20 flex items-center justify-center">
                                            <ArrowUpRight className="w-1.5 h-1.5 text-primary opacity-0 group-hover/item:opacity-100 transition-opacity" />
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ))
                    )}
                </div>

                <div className="p-3 bg-white/5 flex items-center justify-between border-t border-white/5">
                    <div className="flex items-center gap-2 text-[9px] font-mono text-muted-foreground uppercase italic opacity-40">
                        <Target className="w-3 h-3" />
                        Engine: C0MR4DE TERMINAL Discovery v1.2
                    </div>
                    <span className="text-[9px] font-mono text-muted-foreground">
                        Last Refresh: {lastRefresh.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                </div>
            </CardContent>
        </Card>
    );
}
