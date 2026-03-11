
import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { TrendingUp, TrendingDown, AlertCircle, Target, Shield, DollarSign } from 'lucide-react';
import { formatCurrency, MARKETS } from '@/lib/market-config';
import { cn } from '@/lib/utils';

interface TradeSetupProps {
    ticker: string;
}

export function TradeSetupCard({ ticker }: TradeSetupProps) {
    const [data, setData] = useState<any>(null);
    const [quant, setQuant] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchSetup = async () => {
            setLoading(true);
            try {
                const encodedTicker = encodeURIComponent(ticker);
                const res = await fetch(`/api/history?ticker=${encodedTicker}&period=1y&interval=1d`);
                const json = await res.json();
                if (json && json.length > 0) {
                    setData(json[json.length - 1]);
                }

                try {
                    const qRes = await fetch(`/api/quant/institutional?ticker=${ticker}`);
                    const qJson = await qRes.json();
                    if (qJson.status === 'success') {
                        setQuant(qJson.data);
                    }
                } catch (e) { console.error("Quant fetch failed", e); }

            } catch (e) {
                console.error("Failed to fetch setup", e);
            } finally {
                setLoading(false);
            }
        };
        fetchSetup();
    }, [ticker]);

    if (loading) return (
        <Card className="h-full border-border/40 bg-card/20 backdrop-blur-sm animate-pulse flex flex-col items-center justify-center p-6 gap-3">
            <div className="w-10 h-10 border-2 border-primary/10 rounded-full border-t-primary animate-spin" />
            <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-primary/40">Synchronizing_Setup</span>
        </Card>
    );

    if (!data) return (
        <Card className="h-full border border-primary/20 bg-primary/5 flex flex-col items-center justify-center p-8 text-center space-y-4">
            <div className="p-3 rounded-full bg-primary/10 border border-primary/20">
                <AlertCircle className="w-6 h-6 text-primary/40" />
            </div>
            <div className="space-y-1">
                <h3 className="text-xs font-mono font-black uppercase tracking-widest text-primary/60">No Intelligence Feed</h3>
                <p className="text-[9px] font-mono text-muted-foreground italic">Waiting for market confirmed signals...</p>
            </div>
        </Card>
    );

    const action = data.action || 'WAIT';
    const region = MARKETS.find(m => m.ticker === ticker)?.region || 'IN';
    const direction = data.direction || (action === 'ENTER NOW' ? 'LONG' : null);
    const isBullish = direction === 'LONG';
    const isBearish = direction === 'SHORT';

    const risk = Math.abs(data.price - (data.stop_loss || data.price * 0.95));
    const reward = Math.abs((data.take_profit || data.price * 1.05) - data.price);
    const rrRatio = risk > 0 ? (reward / risk).toFixed(1) : '2.0';

    const getActionColor = () => {
        switch (action) {
            case 'ENTER NOW': return isBearish ? 'text-red-500' : 'text-green-500';
            case 'EXIT NOW': return 'text-orange-500';
            case 'HOLD': return 'text-blue-400';
            default: return 'text-muted-foreground';
        }
    };

    const getGlowEffect = () => {
        if (action === 'ENTER NOW') return isBearish ? 'shadow-[0_0_15px_-3px_rgba(239,68,68,0.2)]' : 'shadow-[0_0_15px_-3px_rgba(34,197,94,0.2)]';
        return '';
    };

    return (
        <Card className={cn(
            "border border-border/40 relative overflow-hidden transition-all duration-500 bg-card/40 backdrop-blur-sm",
            getGlowEffect()
        )}>
            {/* Side Accent Line */}
            <div className={cn("absolute left-0 top-0 bottom-0 w-1",
                action === 'ENTER NOW' ? (isBearish ? 'bg-red-500' : 'bg-green-500') :
                    action === 'EXIT NOW' ? 'bg-orange-500' :
                        action === 'HOLD' ? 'bg-blue-500' : 'bg-border/50'
            )} />

            <CardHeader className="pb-2 pt-4 pl-5 flex flex-row items-center justify-between space-y-0">
                <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-2">
                        {action !== 'WAIT' && (
                            <Badge variant="outline" className={cn("text-[9px] px-1.5 py-0 h-4 border-current rounded-sm font-mono tracking-wider", getActionColor())}>
                                {isBearish ? "SHORT" : "LONG"}
                            </Badge>
                        )}
                        <span className={cn("text-lg font-mono font-black tracking-tight", getActionColor())}>
                            {action}
                        </span>
                    </div>
                </div>

                {action === 'ENTER NOW' && (
                    <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-background/60 border border-border/30">
                        <div className={cn("w-1.5 h-1.5 rounded-full animate-pulse", isBearish ? "bg-red-500" : "bg-green-500")} />
                        <span className="text-[10px] font-mono text-muted-foreground/80 uppercase">Confirmed</span>
                    </div>
                )}
            </CardHeader>

            <CardContent className="grid grid-cols-2 md:grid-cols-4 gap-4 py-4 pl-5">

                {/* 1. CURRENT PRICE */}
                <div className="flex flex-col space-y-0.5">
                    <span className="text-[9px] uppercase text-muted-foreground font-mono flex items-center gap-1">
                        <DollarSign className="w-3 h-3 opacity-70" /> Price
                    </span>
                    <span className="text-xl font-mono font-medium tracking-tight">
                        {formatCurrency(data.price, region)}
                    </span>
                </div>

                {/* 2. STOP LOSS */}
                <div className="flex flex-col space-y-0.5">
                    <span className="text-[9px] uppercase text-muted-foreground font-mono flex items-center gap-1">
                        <Shield className="w-3 h-3 opacity-70" /> SL
                    </span>
                    <span className={cn("text-lg font-mono font-medium tracking-tight", isBearish ? "text-red-400" : "text-red-400")}>
                        {formatCurrency(data.stop_loss || data.price * 0.95, region)}
                    </span>
                    <span className="text-[9px] text-muted-foreground/60 font-mono">
                        -{data.stop_loss ? ((1 - data.stop_loss / data.price) * 100).toFixed(1) : '5.0'}%
                    </span>
                </div>

                {/* 3. TARGET */}
                <div className="flex flex-col space-y-0.5">
                    <span className="text-[9px] uppercase text-muted-foreground font-mono flex items-center gap-1">
                        <Target className="w-3 h-3 opacity-70" /> TP
                    </span>
                    <span className={cn("text-lg font-mono font-medium tracking-tight", isBearish ? "text-green-400" : "text-green-400")}>
                        {formatCurrency(data.take_profit || data.price * 1.05, region)}
                    </span>
                    <div className="flex items-center gap-2">
                        <span className="text-[9px] text-muted-foreground/60 font-mono">
                            +{data.take_profit ? ((data.take_profit / data.price - 1) * 100).toFixed(1) : '5.0'}%
                        </span>
                        <Badge variant="secondary" className="text-[9px] px-1 py-0 h-3.5 rounded-[2px] font-mono text-muted-foreground">
                            1:{rrRatio}
                        </Badge>
                    </div>
                </div>

                {/* 4. ALGO INTELLIGENCE */}
                <div className="flex flex-col space-y-2 pl-2 border-l border-border/30">
                    <div className="flex justify-between items-center">
                        <span className="text-[9px] uppercase text-muted-foreground font-mono">Conf.</span>
                        <span className="text-[9px] font-bold font-mono">{(data.confidence * 100)?.toFixed(0) || 75}%</span>
                    </div>

                    {/* Progress Bar */}
                    <div className="h-1 w-full bg-secondary/50 rounded-full overflow-hidden">
                        <div
                            className={cn("h-full transition-all duration-500",
                                isBullish ? "bg-green-500" : isBearish ? "bg-red-500" : "bg-blue-500"
                            )}
                            style={{ width: `${(data.confidence || 0.5) * 100}%` }}
                        />
                    </div>

                    <span className="text-[9px] text-muted-foreground truncate w-full" title={data.reason}>
                        {quant?.regime?.primary_regime?.replace('_', ' ') || "Analyzing..."}
                    </span>
                </div>

            </CardContent>
        </Card>
    );
}
