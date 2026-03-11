
import React from 'react';
import {
    Activity,
    ArrowUp,
    ArrowDown,
    Layers,
    Gauge,
    Info
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { formatCurrency, MarketRegion } from '@/lib/market-config';

interface OrderFlowHeatmapProps {
    data: any;
    region: MarketRegion;
    isLoading: boolean;
}

export function OrderFlowHeatmap({ data, region, isLoading }: OrderFlowHeatmapProps) {
    if (isLoading || !data) {
        return (
            <Card className="h-full animate-pulse border-border/40 bg-card/40 backdrop-blur-sm">
                <CardHeader><div className="h-4 w-32 bg-secondary rounded-sm"></div></CardHeader>
                <CardContent className="space-y-4">
                    <div className="h-32 w-full bg-secondary/20 rounded-sm opacity-50"></div>
                </CardContent>
            </Card>
        );
    }

    const { order_book_imbalance, delta, large_orders, absorption } = data;
    const imbalance = order_book_imbalance?.imbalance || 0;
    const bidVol = order_book_imbalance?.bid_volume || 0;
    const askVol = order_book_imbalance?.ask_volume || 0;
    const totalVol = bidVol + askVol;

    // Normalize volumes for bars (1-100)
    const bidPercent = totalVol > 0 ? (bidVol / totalVol) * 100 : 50;
    const askPercent = 100 - bidPercent;

    return (
        <TooltipProvider>
            <Card className="h-full border border-border/40 bg-card/40 backdrop-blur-sm overflow-hidden flex flex-col transition-all duration-500 hover:border-primary/20">
                <CardHeader className="pb-3 border-b border-border/30 bg-primary/5 pl-4 py-3">
                    <CardTitle className="text-[10px] font-mono font-bold uppercase tracking-[0.2em] flex items-center gap-2 text-primary/80">
                        <Layers className="w-3 h-3" />
                        Order Flow Heatmap
                    </CardTitle>
                </CardHeader>

                <CardContent className="p-4 space-y-5">
                    {/* 1. DEPTH HEATMAP (Visual Bars) */}
                    <div className="space-y-1.5">
                        <div className="flex justify-between text-[9px] font-mono opacity-60 uppercase tracking-wider">
                            <span className="text-green-500 font-bold flex items-center gap-1">Bids (Demand)</span>
                            <span className="text-destructive font-bold flex items-center gap-1">Asks (Supply)</span>
                        </div>
                        <div className="flex h-6 w-full rounded-[2px] overflow-hidden border border-border/30 relative">
                            {/* Center Line */}
                            <div className="absolute left-1/2 top-0 bottom-0 w-[1px] bg-background/50 z-10" />

                            <div
                                className="bg-green-500/70 transition-all duration-700 flex items-center px-2 relative"
                                style={{ width: `${bidPercent}%` }}
                            >
                                <span className="text-[9px] font-bold text-white drop-shadow-sm font-mono absolute left-2">{bidPercent.toFixed(0)}%</span>
                            </div>
                            <div
                                className="bg-destructive/70 transition-all duration-700 flex items-center justify-end px-2 relative"
                                style={{ width: `${askPercent}%` }}
                            >
                                <span className="text-[9px] font-bold text-white drop-shadow-sm font-mono absolute right-2">{askPercent.toFixed(0)}%</span>
                            </div>
                        </div>
                        <div className="flex justify-between text-[9px] font-mono opacity-40">
                            <span>{formatCurrency(bidVol / 100000, region)}L Vol</span>
                            <span>{formatCurrency(askVol / 100000, region)}L Vol</span>
                        </div>
                    </div>

                    {/* 2. DELTA METER (Cumulative Pressure) */}
                    <div className="p-3 bg-secondary/10 rounded border border-border/30 space-y-2 relative overflow-hidden">
                        <div className={cn("absolute top-0 right-0 w-16 h-16 bg-gradient-to-br from-transparent to-primary/5 rounded-bl-full pointer-events-none")} />

                        <div className="flex items-center justify-between">
                            <span className="text-[9px] font-mono font-bold uppercase flex items-center gap-1.5 text-muted-foreground">
                                <Gauge className="w-3 h-3 opacity-70" /> Session Delta
                            </span>
                            <Tooltip>
                                <TooltipTrigger><Info className="w-3 h-3 opacity-20 hover:opacity-100 transition-opacity cursor-help" /></TooltipTrigger>
                                <TooltipContent className="text-[10px] max-w-[200px] font-mono">
                                    Net buying vs selling pressure.
                                </TooltipContent>
                            </Tooltip>
                        </div>

                        <div className="flex items-baseline gap-2">
                            <span className={cn(
                                "text-xl font-mono font-bold tracking-tight",
                                delta?.delta > 0 ? "text-green-500" : "text-destructive"
                            )}>
                                {delta?.delta > 0 ? '+' : ''}{delta?.delta_percent?.toFixed(1)}%
                            </span>
                            <span className="text-[9px] font-mono opacity-50 uppercase tracking-widest">{delta?.trend || 'NEUTRAL'}</span>
                        </div>

                        <Progress
                            value={50 + (delta?.delta_percent || 0) * 5}
                            className="h-1 bg-border/30"
                            indicatorClassName={delta?.delta > 0 ? "bg-green-500" : "bg-destructive"}
                        />
                    </div>

                    {/* 3. INSTITUTIONAL WALLS (Large Orders) */}
                    <div className="space-y-2">
                        <span className="text-[9px] font-mono text-muted-foreground uppercase flex items-center gap-1.5 tracking-wider">
                            <Activity className="w-3 h-3 opacity-70" /> Institutional Walls
                        </span>
                        <div className="space-y-1.5 max-h-[100px] overflow-y-auto pr-1 custom-scrollbar">
                            {large_orders?.length > 0 ? large_orders.map((order: any, i: number) => (
                                <div key={i} className={cn(
                                    "px-2 py-1.5 rounded-[2px] border flex items-center justify-between text-[9px] font-mono transition-colors hover:bg-accent/5",
                                    order.side === 'BID' ? "bg-green-500/5 border-green-500/20" : "bg-destructive/5 border-destructive/20"
                                )}>
                                    <div className="flex items-center gap-2">
                                        {order.side === 'BID' ? <ArrowUp className="w-2.5 h-2.5 text-green-500" /> : <ArrowDown className="w-2.5 h-2.5 text-destructive" />}
                                        <span className={cn("font-bold", order.side === 'BID' ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400")}>
                                            {formatCurrency(order.price, region)}
                                        </span>
                                    </div>
                                    <span className="opacity-60">{formatCurrency(order.value / 100000, region)}L</span>
                                </div>
                            )) : (
                                <div className="text-[9px] italic text-muted-foreground opacity-30 text-center py-3 font-mono border border-dashed border-border/30 rounded">
                                    Scanning depth...
                                </div>
                            )}
                        </div>
                    </div>
                </CardContent>
            </Card>
        </TooltipProvider>
    );
}
