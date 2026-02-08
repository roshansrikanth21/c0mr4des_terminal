import React, { useState } from 'react';
import { useRegimeEngine } from '@/hooks/use-regime-engine';
import { useRiskEngine } from '@/hooks/use-risk-engine';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  ShieldCheck,
  ShieldAlert,
  Zap,
  TrendingUp,
  TrendingDown,
  Activity,
  Lock,
  ArrowRight,
  Info,
  Camera,
  Globe
} from 'lucide-react';
import { REGIME_STRATEGY_MAP } from '@/types/trading';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { MARKETS, formatCurrency, getMarketByRegion } from '@/lib/market-config';
import { PriceChart } from '@/components/PriceChart';
import { ScanDialog } from '@/components/ScanDialog';
import { TradeSetupCard } from '@/components/TradeSetupCard';
import { OptionsSignalCard } from '@/components/OptionsSignalCard';
import { RiskAnalysisCard } from '@/components/institutional/RiskAnalysisCard';
import { BayesianStrategyCard } from '@/components/institutional/BayesianStrategyCard';
import { MarketTimingCard } from '@/components/institutional/MarketTimingCard';
import { OptionGreeksTable } from '@/components/institutional/OptionGreeksTable';
import { useInstitutionalData } from '@/hooks/use-institutional-data';

export function Dashboard() {
  const [selectedMarketId, setSelectedMarketId] = useState(MARKETS[0].id);
  const selectedMarket = MARKETS.find(m => m.id === selectedMarketId) || MARKETS[0];

  const regimeStatus = useRegimeEngine(selectedMarket.ticker);
  const riskStatus = useRiskEngine();

  // Safety check: Ensure the regime exists in the map
  const strategy = REGIME_STRATEGY_MAP[regimeStatus.regime] || {
    name: 'System Initializing...',
    description: 'Waiting for market data connection...',
    type: 'vol_play'
  };

  const handleApproveTrade = () => {
    if (riskStatus.isLocked) {
      toast.error('Trading is locked due to risk rules.');
      return;
    }
    toast.success(`Trade recommendation for ${selectedMarket.name} sent to execution.`);
  };

  const toggleMarket = () => {
    const nextMarket = MARKETS.find(m => m.id !== selectedMarketId) || MARKETS[0];
    setSelectedMarketId(nextMarket.id);
    toast.info(`Switched to ${nextMarket.name} (${nextMarket.region})`);
  };

  const getRegimeIcon = () => {
    switch (regimeStatus.regime) {
      case 'Strong Uptrend': return <TrendingUp className="w-10 h-10 text-primary" />;
      case 'Strong Downtrend': return <TrendingDown className="w-10 h-10 text-primary" />;
      case 'Range-bound': return <Activity className="w-10 h-10 text-primary" />;
      case 'Volatility Expansion': return <Zap className="w-10 h-10 text-destructive" />;
      default: return <Activity className="w-10 h-10 text-primary" />;
    }
  };

  return (
    <div className="space-y-8 pb-24">
      {/* Header Info */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter mb-2">OPERATIONS TERMINAL</h1>
          <div className="flex items-center gap-3">
            <p className="text-muted-foreground font-mono text-xs uppercase tracking-widest">
              SESSION: {new Date().toLocaleDateString()} // UTC: {new Date().toUTCString()}
            </p>
            <Badge variant="secondary" className="font-mono text-[9px] px-1.5 py-0 bg-primary/10 text-primary border-primary/20">
              SIMULATION MODE
            </Badge>
          </div>
        </div>
        <div className="flex gap-4 items-center">
          <ScanDialog />
          {/* Market Selector */}
          <Button
            variant="outline"
            className="flex items-center gap-2 border-primary/20 bg-background"
            onClick={toggleMarket}
          >
            <Globe className="w-4 h-4 text-primary" />
            <span className="font-mono text-xs font-bold">{selectedMarket.name} ({selectedMarket.currency})</span>
          </Button>

          <div className="bg-card border border-border px-6 py-4 rounded-sm flex flex-col items-center min-w-[140px]">
            <span className="text-[10px] font-mono text-muted-foreground uppercase mb-1">Status</span>
            {riskStatus.isLocked ? (
              <Badge variant="destructive" className="font-mono text-xs">TRADING LOCKED</Badge>
            ) : (
              <Badge variant="outline" className="font-mono text-xs border-primary text-primary">OPERATIONAL</Badge>
            )}
          </div>
        </div>
      </div>

      {/* INTRADAY OPTIONS SIGNAL CARD */}
      <OptionsSignalCard ticker={selectedMarket.ticker} interval="5m" />

      {/* ACTIONABLE SIGNAL CARD */}
      <TradeSetupCard ticker={selectedMarket.ticker} />

      {/* --- INSTITUTIONAL ANALYTICS SECTION --- */}
      <InstitutionalSection ticker={selectedMarket.ticker} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Market Regime Section */}
        <Card className="lg:col-span-3 border-2 border-primary/10 bg-card/50">
          <CardHeader className="border-b border-border/50 pb-6">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-xl font-mono uppercase tracking-tighter">Market Regime Engine</CardTitle>
                <CardDescription>Real-time classification for <span className="text-primary font-bold">{selectedMarket.ticker}</span></CardDescription>
              </div>
              <div className="bg-secondary p-3 rounded-full">
                {getRegimeIcon()}
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-8 pb-8">
            <div className="flex flex-col md:flex-row gap-10 items-center">
              <div className="flex-1 text-center md:text-left">
                <div className="text-xs font-mono text-muted-foreground uppercase mb-2">Current Classification</div>
                <div className="text-5xl font-bold tracking-tighter mb-4">{regimeStatus.regime}</div>
                <div className="flex items-center justify-center md:justify-start gap-4">
                  <div className="flex items-center">
                    <div className="w-2 h-2 rounded-full bg-primary mr-2" />
                    <span className="text-sm font-medium">Confidence: {Math.round(regimeStatus.confidence * 100)}%</span>
                  </div>
                </div>
              </div>
              <div className="w-px h-24 bg-border hidden md:block" />
              <div className="flex-1 text-center">
                <div className="text-xs font-mono text-muted-foreground uppercase mb-4">Trade Eligibility</div>
                {regimeStatus.isTradeAllowed && !riskStatus.isLocked ? (
                  <div className="flex flex-col items-center text-primary">
                    <ShieldCheck className="w-16 h-16 mb-2" />
                    <span className="text-2xl font-bold font-mono tracking-tighter">YES / ALLOWED</span>
                  </div>
                ) : (
                  <div className="flex flex-col items-center text-muted-foreground opacity-50">
                    <ShieldAlert className="w-16 h-16 mb-2" />
                    <span className="text-2xl font-bold font-mono tracking-tighter uppercase">NO / FILTERED</span>
                    {regimeStatus.reason && <p className="text-[10px] mt-2 font-mono">{regimeStatus.reason}</p>}
                  </div>
                )}
              </div>
            </div>

            {/* --- VITALS BAR --- */}
            <div className="grid grid-cols-3 gap-4 mt-8 pt-6 border-t border-border/50">
              {/* VIX Vital */}
              <div className="flex flex-col items-center p-3 bg-secondary/30 rounded-lg border border-border/50">
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-1">{selectedMarket.region === 'IN' ? 'India VIX' : 'VIX'}</span>
                <div className="flex items-center gap-2">
                  <div className={cn("h-1.5 w-1.5 rounded-full animate-pulse", regimeStatus.vitals.vix > 20 ? "bg-red-500" : "bg-green-500")}></div>
                  <span className="text-lg font-bold font-mono">{regimeStatus.vitals.vix} <span className="text-[10px] text-muted-foreground font-sans">pts</span></span>
                </div>
              </div>

              {/* RSI Vital */}
              <div className="flex flex-col items-center p-3 bg-secondary/30 rounded-lg border border-border/50">
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-1">RSI (14)</span>
                <span className="text-lg font-bold font-mono text-blue-500">{regimeStatus.vitals.rsi}</span>
              </div>

              {/* ADX Vital */}
              <div className="flex flex-col items-center p-3 bg-secondary/30 rounded-lg border border-border/50">
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-1">Trend Strength</span>
                <span className="text-lg font-bold font-mono text-purple-500">{regimeStatus.vitals.adx}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* --- PRICE CHART SECTION (Inserted Here) --- */}
        <div className="lg:col-span-3">
          <PriceChart ticker={selectedMarket.ticker} region={selectedMarket.region} />
        </div>

        {/* Risk Summary Section */}
        <Card className="lg:col-span-3 border border-border bg-card shadow-sm">
          <CardHeader className="border-b border-border/50">
            <CardTitle className="text-sm font-mono uppercase tracking-widest text-muted-foreground">Risk Engine Summary</CardTitle>
          </CardHeader>
          <CardContent className="pt-6 space-y-6">
            <div className="space-y-4">
              <div className="flex justify-between items-end">
                <span className="text-xs font-medium text-muted-foreground uppercase font-mono">Trades Today</span>
                <span className="text-xl font-bold">{riskStatus.tradesToday} / 3</span>
              </div>
              <div className="w-full bg-secondary h-2 rounded-full overflow-hidden">
                <div
                  className="bg-primary h-full transition-all duration-500"
                  style={{ width: `${(riskStatus.tradesToday / 3) * 100}%` }}
                />
              </div>
            </div>

            <div className="space-y-4">
              <div className="flex justify-between items-end">
                <span className="text-xs font-medium text-muted-foreground uppercase font-mono">Daily Drawdown</span>
                <span className="text-xl font-bold">{formatCurrency(riskStatus.dailyLoss, selectedMarket.region)}</span>
              </div>
              <div className="w-full bg-secondary h-2 rounded-full overflow-hidden">
                <div
                  className="bg-destructive h-full transition-all duration-500"
                  style={{ width: `${Math.min((riskStatus.dailyLoss / 500) * 100, 100)}%` }}
                />
              </div>
            </div>

            <div className="pt-4 border-t border-border">
              <div className="flex items-center justify-between text-xs font-mono uppercase text-muted-foreground mb-4">
                <span>Loss Streak</span>
                <span className={cn(riskStatus.consecutiveLosses >= 2 ? "text-destructive font-bold" : "")}>
                  {riskStatus.consecutiveLosses} / 2
                </span>
              </div>
              {riskStatus.isLocked && (
                <div className="bg-destructive/10 text-destructive p-4 rounded-sm flex items-start gap-3 border border-destructive/20 animate-fade-in">
                  <Lock className="w-5 h-5 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-xs font-bold font-mono uppercase">System Locked</p>
                    <p className="text-[10px] leading-relaxed mt-1">Risk limits exceeded. Further trading is prohibited for this session to preserve capital.</p>
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Connection Info */}
      <div className="bg-secondary/50 border border-border p-4 rounded-sm flex items-start gap-4">
        <div className="bg-primary/10 p-2 rounded-full">
          <Info className="w-4 h-4 text-primary" />
        </div>
        <div className="flex-1">
          <p className="text-xs font-bold uppercase font-mono tracking-tighter mb-1">Live Market Data Active</p>
          <p className="text-[10px] text-muted-foreground leading-relaxed">
            Connected to <strong>Edge-Ops Backend</strong> fetching live data for <strong>{selectedMarket.ticker}</strong>.
            Regime classification is processed in real-time based on 200 SMA, 50 SMA, RSI(14), and ADX(14) logic.
          </p>
        </div>
      </div>

      {/* Recommended Strategy */}
      <Card className={cn(
        "border transition-all duration-300",
        regimeStatus.isTradeAllowed && !riskStatus.isLocked
          ? "border-primary shadow-lg scale-[1.01]"
          : "border-border opacity-60"
      )}>
        <CardHeader className="bg-secondary/30">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="text-[10px] font-mono text-muted-foreground uppercase mb-1 tracking-widest">Recommended Strategy</div>
              <CardTitle className="text-2xl font-bold tracking-tight">{strategy.name}</CardTitle>
            </div>
            {regimeStatus.isTradeAllowed && !riskStatus.isLocked && (
              <Badge className="bg-primary text-primary-foreground font-mono text-[10px] py-1 px-3">OPTIMAL ENTRY WINDOW</Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="pt-8 pb-8 flex flex-col md:flex-row gap-10">
          <div className="flex-1 space-y-6">
            <div>
              <h4 className="text-xs font-mono text-muted-foreground uppercase mb-3">Strategy Mechanics</h4>
              <p className="text-sm leading-relaxed">{strategy.description}</p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-secondary/50 p-4 rounded-sm border border-border/50">
                <div className="text-[10px] font-mono text-muted-foreground uppercase mb-1">Max Risk</div>
                <div className="text-sm font-bold">{formatCurrency(150, selectedMarket.region)}</div>
              </div>
              <div className="bg-secondary/50 p-4 rounded-sm border border-border/50">
                <div className="text-[10px] font-mono text-muted-foreground uppercase mb-1">Max Reward</div>
                <div className="text-sm font-bold">{formatCurrency(300, selectedMarket.region)}</div>
              </div>
            </div>
          </div>
          <div className="flex flex-col justify-center items-center md:items-end md:w-[300px] border-t md:border-t-0 md:border-l border-border pt-8 md:pt-0 md:pl-10">
            <div className="text-center md:text-right mb-6">
              <p className="text-[10px] font-mono text-muted-foreground uppercase mb-2">Trade Execution</p>
              <p className="text-xs italic leading-relaxed">System requires manual approval to confirm discipline protocols.</p>
            </div>
            <Button
              size="lg"
              className="w-full h-16 group transition-all"
              disabled={!regimeStatus.isTradeAllowed || riskStatus.isLocked}
              onClick={handleApproveTrade}
            >
              Approve Strategy Recommendation
              <ArrowRight className="ml-2 w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* --- FLOATING CAMERA BUTTON --- */}
      <button
        className="fixed bottom-24 right-6 h-14 w-14 bg-primary text-primary-foreground rounded-full shadow-2xl flex items-center justify-center hover:scale-105 active:scale-95 transition-all z-50 border-2 border-primary/20"
        onClick={() => toast.info("Initializing Camera Scan Module...")}
      >
        <Camera className="h-7 w-7" />
      </button>

      {/* --- RISK GUARD STICKY FOOTER --- */}
      <div className="fixed bottom-0 left-0 w-full bg-background/95 backdrop-blur-sm border-t border-border p-3 shadow-lg z-40 flex justify-between items-center px-6">
        <div className="flex items-center gap-3">
          <div className={`h-2.5 w-2.5 rounded-full ${riskStatus.isLocked ? "bg-destructive animate-pulse" : "bg-green-500"}`}></div>
          <span className="text-xs font-bold font-mono tracking-wider uppercase text-foreground">
            RISK GUARD: {riskStatus.isLocked ? "LOCKED" : "ACTIVE"}
          </span>
        </div>
        <span className="text-xs font-mono text-muted-foreground">
          DAILY LOSS: <span className={riskStatus.dailyLoss > 0 ? "text-destructive font-bold" : "text-foreground font-bold"}>
            {((riskStatus.dailyLoss / 500) * 100).toFixed(2)}%
          </span> / 2.00%
        </span>
      </div>

    </div>
  );
}

function InstitutionalSection({ ticker }: { ticker: string }) {
  const { riskData, strategyData, timingData, greeksData, isLoading } = useInstitutionalData(ticker);

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-mono font-bold uppercase tracking-wider text-primary flex items-center gap-2">
        <span className="w-2 h-2 bg-primary rounded-full animate-pulse"></span>
        Institutional Analytics
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <RiskAnalysisCard metrics={riskData} isLoading={isLoading} />
        <BayesianStrategyCard metrics={strategyData} isLoading={isLoading} />
        <MarketTimingCard session={timingData?.session} nextEvent={timingData?.next_event} isLoading={isLoading} />
        <OptionGreeksTable
          data={greeksData?.chain || []}
          spotPrice={greeksData?.spot_price || 0}
          expiry={greeksData?.expiry || "-"}
          isLoading={isLoading}
        />
      </div>
    </div>
  );
}