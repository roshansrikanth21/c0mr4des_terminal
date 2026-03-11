import React from 'react';
import {
    Fingerprint,
    Target,
    Waves,
    Zap,
    Info,
    ArrowUpRight,
    ArrowDownRight,
    Search
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { formatCurrency, MarketRegion } from '@/lib/market-config';

interface TechnicalIntelProps {
    ictData: any[];
    volumeData: any;
    timingData: any;
    region: MarketRegion;
    isLoading: boolean;
}

export function TechnicalIntelSidebar({ ictData, volumeData, timingData, region, isLoading }: TechnicalIntelProps) {
    if (isLoading) {
        return (
            <Card className="h-full animate-pulse border-border/50">
                <CardHeader><div className="h-4 w-32 bg-muted rounded"></div></CardHeader>
                <CardContent className="space-y-4">
                    {[1, 2, 3, 4].map(i => <div key={i} className="h-12 w-full bg-muted rounded opacity-50"></div>)}
                </CardContent>
            </Card>
        );
    }

    const sndZones = ictData.filter(d => d.type.includes('ZONE')).slice(-3);
    const sweeps = ictData.filter(d => d.type === 'LIQUIDITY_SWEEP').slice(-2);
    const poc = volumeData?.poc;
    const asianRange = timingData?.asian_range;

    return (
        <TooltipProvider>
            <Card className="h-full border-border bg-card/50 backdrop-blur-sm overflow-hidden flex flex-col">
                <CardHeader className="pb-3 border-b border-border/50 bg-secondary/20">
                    <CardTitle className="text-xs font-mono font-bold uppercase tracking-[0.2em] flex items-center gap-2">
                        <Fingerprint className="w-4 h-4 text-primary" />
                        Technical Intelligence
                    </CardTitle>
                </CardHeader>
                <CardContent className="p-0 flex-1">
                    <div className="space-y-1">
                        {/* 1. VOLUME PROFILE (POC) */}
                        <div className="p-4 space-y-3">
                            <div className="flex items-center justify-between">
                                <span className="text-[10px] font-mono text-muted-foreground uppercase flex items-center gap-2">
                                    <Target className="w-3 h-3" /> Volume POC
                                </span>
                                <Tooltip>
                                    <TooltipTrigger><Info className="w-3 h-3 opacity-30 cursor-help" /></TooltipTrigger>
                                    <TooltipContent side="right" className="max-w-[200px] text-[10px]">
                                        Point of Control: The price level where the most volume was traded. Acts as a price "gravity well".
                                    </TooltipContent>
                                </Tooltip>
                            </div>
                            <div className="bg-primary/5 border border-primary/20 p-3 rounded-md">
                                <span className="text-xl font-black tracking-tighter block">{formatCurrency(poc || 0, region)}</span>
                                <span className="text-[9px] font-mono opacity-60 uppercase">Institutional Magnet</span>
                            </div>
                        </div>

                        {/* 2. SUPPLY & DEMAND */}
                        <div className="p-4 space-y-3">
                            <span className="text-[10px] font-mono text-muted-foreground uppercase flex items-center gap-2">
                                <Waves className="w-3 h-3" /> Supply & Demand
                            </span>
                            <div className="space-y-2">
                                {sndZones.length > 0 ? sndZones.map((zone, i) => (
                                    <div key={i} className={cn(
                                        "flex items-center justify-between p-2 rounded border text-[10px] font-mono font-bold",
                                        zone.type.includes('SUPPLY') ? "bg-destructive/5 border-destructive/20 text-destructive" : "bg-green-500/5 border-green-500/20 text-green-500"
                                    )}>
                                        <span>{zone.type.replace('_ZONE', '')}</span>
                                        <span>{formatCurrency(zone.bottom, region)}</span>
                                    </div>
                                )) : (
                                    <div className="text-[10px] italic text-muted-foreground opacity-50 px-2 py-1">No active zones detected</div>
                                )}
                            </div>
                        </div>

                        {/* 3. SESSION BREAKOUTS */}
                        <div className="p-4 space-y-3">
                            <div className="flex items-center justify-between">
                                <span className="text-[10px] font-mono text-muted-foreground uppercase flex items-center gap-2">
                                    <Zap className="w-3 h-3" /> Session Range
                                </span>
                                <Badge variant="outline" className="text-[8px] opacity-70">ASIAN</Badge>
                            </div>
                            {asianRange ? (
                                <div className="space-y-2">
                                    <div className="flex justify-between text-[10px] font-mono opacity-80">
                                        <span>High: {formatCurrency(asianRange.high, region)}</span>
                                        <span>Low: {formatCurrency(asianRange.low, region)}</span>
                                    </div>
                                    <div className={cn(
                                        "px-2 py-1 rounded text-[9px] font-bold text-center uppercase tracking-wider",
                                        asianRange.status === 'INSIDE' ? "bg-muted text-muted-foreground" : "bg-primary text-primary-foreground animate-pulse"
                                    )}>
                                        {asianRange.status.replace('_', ' ')}
                                    </div>
                                </div>
                            ) : (
                                <div className="text-[10px] italic text-muted-foreground opacity-50 px-2 py-1">Calculating session...</div>
                            )}
                        </div>

                        {/* 4. LIQUIDITY SWEEPS */}
                        <div className="p-4 space-y-3">
                            <span className="text-[10px] font-mono text-muted-foreground uppercase flex items-center gap-2">
                                <Search className="w-3 h-3" /> Stop Hunts
                            </span>
                            <div className="space-y-2">
                                {sweeps.map((sweep, i) => (
                                    <div key={i} className="flex gap-2 items-start bg-secondary/30 p-2 rounded border border-border/50">
                                        {sweep.direction === 'BULLISH' ? <ArrowUpRight className="w-3 h-3 text-green-500" /> : <ArrowDownRight className="w-3 h-3 text-destructive" />}
                                        <div className="flex flex-col">
                                            <span className="text-[10px] font-bold uppercase">{sweep.description}</span>
                                            <span className="text-[9px] opacity-50 font-mono">{formatCurrency(sweep.level, region)}</span>
                                        </div>
                                    </div>
                                ))}
                                {sweeps.length === 0 && <div className="text-[10px] italic text-muted-foreground opacity-50 px-2 py-1">Clean price action</div>}
                            </div>
                        </div>
                    </div>
                </CardContent>
                <div className="p-4 bg-muted/20 border-t border-border/50">
                    <button className="w-full text-[9px] font-mono uppercase font-bold text-primary hover:underline flex items-center justify-center gap-2">
                        View Technical Docs <ArrowUpRight className="w-2.5 h-2.5" />
                    </button>
                </div>
            </Card>
        </TooltipProvider>
    );
}
