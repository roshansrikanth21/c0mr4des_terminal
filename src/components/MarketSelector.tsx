
import React from 'react';
import {
    Globe,
    Cpu,
    Coins,
    HardHat,
    Check,
    ChevronDown,
    Activity
} from 'lucide-react';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuGroup,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { MARKETS, MARKET_CATEGORIES, MarketConfig } from '@/lib/market-config';
import { cn } from '@/lib/utils';

interface MarketSelectorProps {
    selectedMarket: MarketConfig;
    onSelect: (marketId: string) => void;
}

export function MarketSelector({ selectedMarket, onSelect }: MarketSelectorProps) {
    const getIcon = (category: string) => {
        switch (category) {
            case 'indices': return <Activity className="w-3 h-3" />;
            case 'crypto': return <Cpu className="w-3 h-3" />;
            case 'forex': return <Coins className="w-3 h-3" />;
            case 'commodities': return <HardHat className="w-3 h-3" />;
            default: return <Globe className="w-3 h-3" />;
        }
    };

    const getRegionIcon = (region: string) => {
        switch (region) {
            case 'IN': return <span className="text-[10px] grayscale brightness-150">🇮🇳</span>;
            case 'US': return <span className="text-[10px] grayscale brightness-150">🇺🇸</span>;
            case 'FX': return <Coins className="w-3 h-3 text-yellow-500/80" />;
            case 'CRYPTO': return <Cpu className="w-3 h-3 text-purple-500/80" />;
            case 'COMMODITY': return <HardHat className="w-3 h-3 text-orange-500/80" />;
            default: return <Globe className="w-3 h-3" />;
        }
    };

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button variant="outline" className="min-w-[220px] justify-between border-border/40 hover:border-primary/50 bg-card/40 backdrop-blur-sm transition-all duration-300 font-mono text-xs h-9">
                    <div className="flex items-center gap-2.5">
                        <div className="flex items-center justify-center w-5 h-5 rounded bg-secondary/50">
                            {getRegionIcon(selectedMarket.region)}
                        </div>
                        <span className="font-bold tracking-tight">{selectedMarket.name}</span>
                    </div>
                    <ChevronDown className="w-3 h-3 opacity-50" />
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-[260px] p-1.5 bg-background/90 backdrop-blur-xl border-border/40 z-[100] shadow-xl" align="end">
                {MARKET_CATEGORIES.map((category, idx) => {
                    const categoryMarkets = MARKETS.filter(m => {
                        if (category.id === 'indices') return m.region === 'IN' || m.region === 'US';
                        if (category.id === 'crypto') return m.region === 'CRYPTO';
                        if (category.id === 'forex') return m.region === 'FX';
                        if (category.id === 'commodities') return m.region === 'COMMODITY';
                        return false;
                    });

                    if (categoryMarkets.length === 0) return null;

                    return (
                        <DropdownMenuGroup key={category.id}>
                            {idx > 0 && <DropdownMenuSeparator className="my-1 opacity-20" />}
                            <DropdownMenuLabel className="flex items-center gap-2 text-[9px] uppercase tracking-[0.2em] text-muted-foreground/60 px-2 py-1.5 font-mono">
                                {getIcon(category.id)}
                                {category.name}
                            </DropdownMenuLabel>
                            {categoryMarkets.map((market) => (
                                <DropdownMenuItem
                                    key={market.id}
                                    onClick={() => onSelect(market.id)}
                                    className={cn(
                                        "flex items-center justify-between px-2 py-1.5 cursor-pointer transition-all duration-200 rounded-sm mb-0.5",
                                        selectedMarket.id === market.id ? "bg-primary/10 text-primary font-bold" : "hover:bg-primary/5 text-muted-foreground hover:text-foreground"
                                    )}
                                >
                                    <div className="flex items-center gap-3">
                                        <span className={cn("text-xs font-mono transition-all", selectedMarket.id === market.id && "translate-x-1")}>
                                            {market.name}
                                        </span>
                                    </div>
                                    {selectedMarket.id === market.id && (
                                        <div className="w-1.5 h-1.5 rounded-full bg-primary shadow-[0_0_8px_rgba(var(--primary),0.5)]" />
                                    )}
                                </DropdownMenuItem>
                            ))}
                        </DropdownMenuGroup>
                    );
                })}
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
