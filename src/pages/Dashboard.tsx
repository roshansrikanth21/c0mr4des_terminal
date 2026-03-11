import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useRegimeEngine } from '@/hooks/use-regime-engine';
import { useRiskEngine } from '@/hooks/use-risk-engine';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  RotateCcw,
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
  Globe,
  Cpu,
  Wifi,
  ChevronRight,
  SlidersHorizontal,
  Move,
  Plus,
  Minus
} from 'lucide-react';
import { REGIME_STRATEGY_MAP } from '@/types/trading';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { MARKETS, formatCurrency, MarketRegion } from '@/lib/market-config';
import { PriceChart } from '@/components/PriceChart';
import { ScanDialog } from '@/components/ScanDialog';
import { TradeSetupCard } from '@/components/TradeSetupCard';
import { OptionsSignalCard } from '@/components/OptionsSignalCard';
import { RiskAnalysisCard } from '@/components/institutional/RiskAnalysisCard';
import { BayesianStrategyCard } from '@/components/institutional/BayesianStrategyCard';
import { MarketTimingCard } from '@/components/institutional/MarketTimingCard';
import { OptionGreeksTable } from '@/components/institutional/OptionGreeksTable';
import { useInstitutionalData } from '@/hooks/use-institutional-data';
import { useBroker } from '@/hooks/use-broker';
import { BrokerStatus } from '@/components/broker/BrokerStatus';
import { OrderEntry } from '@/components/broker/OrderEntry';
import { PortfolioTable } from '@/components/broker/PortfolioTable';
import { MarketSelector } from '@/components/MarketSelector';
import { TechnicalIntelSidebar } from '@/components/institutional/TechnicalIntelSidebar';
import { OrderFlowHeatmap } from '@/components/institutional/OrderFlowHeatmap';
import { AlphaDiscoverCard } from '@/components/AlphaDiscoverCard';
import { NewsImpactFeed } from '@/components/analytics/NewsImpactFeed';
import { SystemMonitor } from '@/components/analytics/SystemMonitor';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { LoadingScreen } from '@/components/ui/LoadingScreen';
import { useDashboardStore } from '@/hooks/use-dashboard-store';

// @ts-ignore
import { Responsive, useContainerWidth } from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

const ResponsiveGrid: any = Responsive;


export function Dashboard() {
  const [availableMarkets, setAvailableMarkets] = useState(MARKETS);
  const [selectedMarketId, setSelectedMarketId] = useState(MARKETS[0].id);
  const selectedMarket = availableMarkets.find(m => m.id === selectedMarketId) || availableMarkets[0];
  const { isEditMode, toggleEditMode, resetPanelScales } = useDashboardStore();

  const regimeStatus = useRegimeEngine(selectedMarket.ticker);
  const broker = useBroker();
  const riskStatus = useRiskEngine({ status: broker.status, portfolio: broker.portfolio });

  const [activeTab, setActiveTab] = useState<'terminal' | 'analytics' | 'news'>('terminal');
  const [volumeData, setVolumeData] = useState<any>(null);
  const [timingData, setTimingData] = useState<any>(null);
  const [ictData, setIctData] = useState<any[]>([]);
  const [orderFlowData, setOrderFlowData] = useState<any>(null);
  const [isIntelLoading, setIsIntelLoading] = useState(true);
  const [intelError, setIntelError] = useState<string | null>(null);
  const hasIntelDataRef = useRef(false);

  useEffect(() => {
    hasIntelDataRef.current = Boolean(
      volumeData ||
      timingData ||
      orderFlowData ||
      (Array.isArray(ictData) && ictData.length > 0)
    );
  }, [volumeData, timingData, orderFlowData, ictData]);


  useEffect(() => {
    let isMounted = true;

    fetch(`/api/system/prewarm?ticker=${encodeURIComponent(selectedMarket.ticker)}&period=30d&interval=15m`, {
      method: 'POST',
    }).catch(() => undefined);

    const fetchJsonWithTimeout = async (url: string, timeout = 9000) => {
      const controller = new AbortController();
      const id = setTimeout(() => controller.abort(), timeout);
      try {
        const response = await fetch(url, { signal: controller.signal });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
      } finally {
        clearTimeout(id);
      }
    };

    const fetchIntel = async () => {
      const hasExistingIntel = hasIntelDataRef.current;
      if (!hasExistingIntel) setIsIntelLoading(true);
      setIntelError(null);

      const safetyTimeout = setTimeout(() => {
        if (isMounted) setIsIntelLoading(false);
      }, 9000);

      try {
        const encodedTicker = encodeURIComponent(selectedMarket.ticker);
        const bundle = await fetchJsonWithTimeout(
          `/api/intel/bundle?ticker=${encodedTicker}&period=30d&interval=15m`
        );

        if (bundle?.status === 'success' && bundle.data) {
          const { volume, ict, timing, order_flow } = bundle.data;
          if (volume) setVolumeData(volume);
          if (timing) setTimingData(timing);
          if (ict) setIctData(ict);
          if (order_flow) setOrderFlowData(order_flow);
          setIntelError(null);
        } else {
          throw new Error(bundle?.message || "Failed to parse intel bundle");
        }
      } catch (err: any) {
        console.warn("Intel bundle fetch failed, trying fallback feeds:", err);
        try {
          const encodedTicker = encodeURIComponent(selectedMarket.ticker);
          const [vpRes, ictRes, timingRes, flowRes] = await Promise.allSettled([
            fetchJsonWithTimeout(`/api/volume_profile?ticker=${encodedTicker}&period=30d&interval=15m`, 7000),
            fetchJsonWithTimeout(`/api/ict_analysis?ticker=${encodedTicker}&period=30d&interval=15m`, 7000),
            fetchJsonWithTimeout(`/api/market_timing?ticker=${encodedTicker}`, 7000),
            fetchJsonWithTimeout(`/api/order_flow?ticker=${encodedTicker}`, 7000),
          ]);

          let hydrated = false;
          if (vpRes.status === 'fulfilled' && vpRes.value?.status === 'success' && vpRes.value.data) {
            setVolumeData(vpRes.value.data);
            hydrated = true;
          }
          if (ictRes.status === 'fulfilled' && ictRes.value?.status === 'success' && ictRes.value.data) {
            setIctData(ictRes.value.data);
            hydrated = true;
          }
          if (timingRes.status === 'fulfilled' && timingRes.value?.status === 'success') {
            setTimingData({ session: timingRes.value.session, signals: timingRes.value.signals });
            hydrated = true;
          }
          if (flowRes.status === 'fulfilled' && flowRes.value?.status === 'success' && flowRes.value.data) {
            setOrderFlowData(flowRes.value.data);
            hydrated = true;
          }

          if (hydrated) {
            setIntelError("Bundle delayed. Running fallback sync.");
          } else {
            setIntelError("Market intelligence synchronization delayed.");
            if (!hasExistingIntel) toast.error("Intelligence synchronization offline.");
          }
        } catch (fallbackErr) {
          console.error("Fallback intelligence fetch failed:", fallbackErr);
          setIntelError("Market intelligence synchronization delayed.");
          if (!hasExistingIntel) toast.error("Intelligence synchronization offline.");
        }
      } finally {
        if (isMounted) setIsIntelLoading(false);
        clearTimeout(safetyTimeout);
      }
    };

    fetchIntel();
    const interval = setInterval(fetchIntel, 60000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [selectedMarket.ticker]);

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

  const handleSelectAlpha = (ticker: string) => {
    const existing = availableMarkets.find(m => m.ticker === ticker);
    if (existing) {
      setSelectedMarketId(existing.id);
    } else {
      const name = ticker.split('.')[0].replace('^', '');
      const region: MarketRegion = ticker.includes('.NS') ? 'IN' : (ticker.includes('-USD') ? 'CRYPTO' : 'US');
      const newMarket = {
        id: name.toLowerCase(),
        name: name,
        region: region,
        ticker: ticker,
        currency: region === 'IN' ? 'INR' : 'USD',
        locale: region === 'IN' ? 'en-IN' : 'en-US',
      };
      setAvailableMarkets(prev => [...prev, newMarket]);
      setSelectedMarketId(newMarket.id);
    }
    toast.success(`Switching focus to ${ticker}`);
  };

  if (isIntelLoading && !volumeData && !intelError) {
    return <LoadingScreen progress={66} status={`Establishing secure feed to ${selectedMarket.ticker}...`} />;
  }

  return (
    <div className="space-y-6 pb-24 w-full px-4 lg:px-6">
      {/* --- PRO HEADER --- */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-8 pb-6 border-b border-border">
        <div className="flex flex-col">
          <h1 className="text-4xl font-black tracking-tighter text-foreground uppercase flex items-center gap-3">
            <Zap className="w-8 h-8 text-primary animate-pulse shadow-[0_0_15px_rgba(var(--primary),0.5)]" />
            C0MR4DE TERMINAL
          </h1>
          <span className="text-[10px] font-mono font-bold tracking-[0.4em] opacity-40 uppercase ml-11">
            Neural Intelligence Platform v3.2
          </span>
        </div>

        <div className="flex-1 hidden xl:flex items-center justify-center gap-16 px-12 border-x border-border/20 mx-12">
          <div className="flex items-center gap-4">
            <div className="flex gap-1 items-end h-4">
              {[1, 2, 3, 4, 5].map((i) => (
                <div
                  key={i}
                  className={cn(
                    "w-1.5 rounded-t-[1px] transition-all duration-700",
                    i <= (regimeStatus.isLoading ? 2 : 5) ? "bg-primary shadow-[0_0_12px_rgba(var(--primary),0.5)]" : "bg-muted-foreground/10",
                    i === 1 ? "h-1.5" : i === 2 ? "h-2.5" : i === 3 ? "h-3.5" : i === 4 ? "h-4" : "h-4.5"
                  )}
                />
              ))}
            </div>
            <div className="flex flex-col">
              <span className="text-[9px] font-mono font-bold tracking-[0.3em] opacity-40 uppercase leading-none mb-1">Status</span>
              <span className="text-[10px] font-mono font-black tracking-widest text-primary uppercase whitespace-nowrap">
                {regimeStatus.isLoading ? "SYNCING_CORE" : "LINK_ESTABLISHED"}
              </span>
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <span className="text-[9px] font-mono font-bold tracking-[0.3em] opacity-40 uppercase leading-none">Latency</span>
            <div className="flex items-center gap-2">
              <Cpu className="w-3 h-3 text-primary/40" />
              <span className="text-[11px] font-mono font-bold tracking-tight text-primary/80">
                {regimeStatus.isLoading ? "---" : "42ms"}
              </span>
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <span className="text-[9px] font-mono font-bold tracking-[0.3em] opacity-40 uppercase leading-none">Process</span>
            <div className="flex items-center gap-2">
              <span className={cn(
                "w-2 h-2 rounded-full",
                regimeStatus.isLoading ? "bg-muted-foreground animate-pulse" : "bg-primary shadow-[0_0_10px_rgba(var(--primary),0.8)]"
              )} />
              <span className="text-[11px] font-mono font-bold tracking-tight opacity-70 uppercase">
                Neural_Active
              </span>
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <span className="text-[9px] font-mono font-bold tracking-[0.3em] opacity-40 uppercase leading-none">Engine</span>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse shadow-[0_0_8px_rgba(34,197,94,0.6)]" />
              <span className="text-[11px] font-mono font-bold tracking-tight opacity-70 uppercase text-green-500/80">
                Gemini_2.0_Flash
              </span>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <ScanDialog />
          <MarketSelector
            selectedMarket={selectedMarket}
            onSelect={(id) => setSelectedMarketId(id)}
          />
          <div className="border border-border shadow-sm px-6 py-3 bg-muted/20 rounded-md">
            <div className="text-right">
              <div className="text-[9px] font-mono text-muted-foreground uppercase leading-none mb-1">Risk Status</div>
              <span className={cn("text-xs font-bold font-mono", riskStatus.isLocked ? "text-destructive" : "text-primary")}>
                {riskStatus.isLocked ? "LOCKED" : "NOMINAL"}
              </span>
            </div>
          </div>
        </div>
      </div>

      <Tabs defaultValue="terminal" onValueChange={(v) => setActiveTab(v as any)} className="w-full">
        <TabsList className="bg-muted/30 border border-border p-1 h-12 mb-8 flex flex-wrap max-w-fit">
          <TabsTrigger value="terminal" className="px-8 font-mono font-bold tracking-widest uppercase text-[10px] data-[state=active]:bg-primary data-[state=active]:text-primary-foreground transition-all">
            Market Terminal
          </TabsTrigger>
          <TabsTrigger value="analytics" className="px-8 font-mono font-bold tracking-widest uppercase text-[10px] data-[state=active]:bg-primary data-[state=active]:text-primary-foreground transition-all">
            Model Analytics
          </TabsTrigger>
          <TabsTrigger value="news" className="px-8 font-mono font-bold tracking-widest uppercase text-[10px] data-[state=active]:flex data-[state=active]:items-center data-[state=active]:gap-2 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground transition-all">
            <Globe className="w-3 h-3 hidden data-[state=active]:block" />
            Global News
          </TabsTrigger>
        </TabsList>

        <TabsContent value="terminal" className="mt-0">
          <DashboardGrid
            tab="terminal"
            selectedMarket={selectedMarket}
            orderFlowData={orderFlowData}
            isIntelLoading={isIntelLoading}
            riskStatus={riskStatus}
            ictData={ictData}
            volumeData={volumeData}
            timingData={timingData}
            broker={broker}
            handleSelectAlpha={handleSelectAlpha}
            handleApproveTrade={handleApproveTrade}
            regimeStatus={regimeStatus}
            strategy={strategy}
          />
        </TabsContent>

        <TabsContent value="analytics" className="mt-0">
          <DashboardGrid
            tab="analytics"
            selectedMarket={selectedMarket}
            isIntelLoading={isIntelLoading}
            regimeStatus={regimeStatus}
          />
        </TabsContent>

        <TabsContent value="news" className="mt-0">
          <DashboardGrid tab="news" />
        </TabsContent>
      </Tabs>

      {/* --- FOOTER STICKY --- */}
      <div className="fixed bottom-0 left-0 w-full bg-background/95 backdrop-blur-sm border-t border-border p-3 shadow-lg z-40">
        <div className="px-8 flex justify-between items-center w-full">
          <div className="flex items-center gap-3">
            <div className={`h-2.5 w-2.5 rounded-full ${riskStatus.isLocked ? "bg-destructive animate-pulse" : "bg-green-500"}`}></div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                const { resetLayout } = useDashboardStore.getState();
                resetLayout(activeTab);
                toast.success("Dashboard arrangement reset to optimal default.");
              }}
              className="h-8 border-primary/20 bg-primary/5 hover:bg-primary/10 transition-all"
            >
              <RotateCcw className="w-4 h-4 mr-2" />
              Reset Arrangement
            </Button>
            <Button
              variant={isEditMode ? "default" : "outline"}
              size="sm"
              onClick={() => {
                toggleEditMode();
                toast.success(isEditMode ? "Layout edit mode disabled." : "Layout edit mode enabled. Drag/resize panels now.");
              }}
              className="h-8 transition-all"
            >
              <Move className="w-4 h-4 mr-2" />
              {isEditMode ? "Lock Layout" : "Customize Layout"}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                resetPanelScales(activeTab);
                toast.success("Panel text scaling reset for this tab.");
              }}
              className="h-8 text-muted-foreground"
            >
              <SlidersHorizontal className="w-4 h-4 mr-2" />
              Reset Text Scale
            </Button>
            <span className="text-xs font-bold font-mono tracking-wider uppercase">
              RISK GUARD: {riskStatus.isLocked ? "LOCKED" : "ACTIVE"}
            </span>
          </div>
          <span className="text-xs font-mono text-muted-foreground">
            STREAMS SYNCED | {selectedMarket.ticker} | SESSION: {selectedMarket.region}
          </span>
        </div>
      </div>
    </div>
  );
}

type DashboardTab = 'terminal' | 'analytics' | 'news';

function AdaptivePanel({
  tab,
  panelId,
  isEditMode,
  children,
}: {
  tab: DashboardTab;
  panelId: string;
  isEditMode: boolean;
  children: React.ReactNode;
}) {
  const panelScale = useDashboardStore((state) => state.panelScales[tab]?.[panelId] ?? 1);
  const setPanelScale = useDashboardStore((state) => state.setPanelScale);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [autoScale, setAutoScale] = useState(1);

  useEffect(() => {
    if (!hostRef.current || typeof ResizeObserver === 'undefined') return;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height } = entry.contentRect;
      if (!width || !height) return;

      // Auto-fit baseline: compact cards scale down, larger cards scale up mildly.
      const widthScale = width / 520;
      const heightScale = height / 300;
      const next = Math.max(0.78, Math.min(1.15, Math.min(widthScale, heightScale)));
      setAutoScale(next);
    });

    observer.observe(hostRef.current);
    return () => observer.disconnect();
  }, []);

  const finalScale = useMemo(() => {
    const merged = autoScale * panelScale;
    return Math.max(0.72, Math.min(1.3, merged));
  }, [autoScale, panelScale]);

  return (
    <div ref={hostRef} className="relative h-full w-full overflow-hidden">
      {isEditMode && (
        <div className="absolute top-2 right-2 z-20 flex items-center gap-1 rounded-md border border-border/60 bg-background/90 px-1.5 py-1 backdrop-blur">
          <Button
            size="icon"
            variant="ghost"
            className="h-5 w-5"
            onClick={() => setPanelScale(tab, panelId, panelScale - 0.05)}
            title="Reduce text scale"
          >
            <Minus className="w-3 h-3" />
          </Button>
          <button
            className="text-[9px] min-w-[46px] text-center font-mono text-muted-foreground hover:text-foreground transition-colors"
            onClick={() => setPanelScale(tab, panelId, 1)}
            title="Reset text scale"
          >
            {Math.round(finalScale * 100)}%
          </button>
          <Button
            size="icon"
            variant="ghost"
            className="h-5 w-5"
            onClick={() => setPanelScale(tab, panelId, panelScale + 0.05)}
            title="Increase text scale"
          >
            <Plus className="w-3 h-3" />
          </Button>
        </div>
      )}

      <div className="h-full w-full overflow-hidden">
        <div
          className="h-full w-full transition-[font-size] duration-200 ease-out"
          style={{ fontSize: `${finalScale}em` }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}

function DashboardGrid({
  tab, selectedMarket, orderFlowData, isIntelLoading, riskStatus,
  ictData, volumeData, timingData, broker, handleSelectAlpha,
  handleApproveTrade, regimeStatus, strategy
}: any) {
  const { terminalLayout, analyticsLayout, newsLayout, isEditMode, updateLayout } = useDashboardStore();
  const currentLayout = tab === 'terminal' ? terminalLayout : tab === 'analytics' ? analyticsLayout : newsLayout;

  const onLayoutChange = (newLayout: any) => {
    updateLayout(tab, newLayout);
  };

  const gridItemClass = cn(
    "h-full w-full overflow-hidden rounded-lg bg-card/40 backdrop-blur-sm border border-border shadow-sm transition-all",
    isEditMode && "ring-2 ring-primary ring-offset-2 cursor-move border-dashed border-primary/50 bg-primary/5"
  );

  const { width, containerRef, mounted } = useContainerWidth();

  return (
    <div ref={containerRef} className="h-full relative z-10 w-full min-h-[800px]">
      {mounted && (
        <>
          <ResponsiveGrid
            className="layout"
            layouts={{ lg: currentLayout, md: currentLayout }}
            breakpoints={{ lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 }}
            cols={{ lg: 12, md: 10, sm: 6, xs: 4, xxs: 2 }}
            rowHeight={100}
            isDraggable={isEditMode}
            isResizable={isEditMode}
            onLayoutChange={onLayoutChange}
            margin={[24, 24]}
            width={width}
          >
            {tab === 'terminal' ? [
              <div key="chart" className={gridItemClass}>
                <AdaptivePanel tab={tab} panelId="chart" isEditMode={isEditMode}>
                  <PriceChart ticker={selectedMarket.ticker} region={selectedMarket.region} />
                </AdaptivePanel>
              </div>,
              <div key="signals" className={gridItemClass}>
                <AdaptivePanel tab={tab} panelId="signals" isEditMode={isEditMode}>
                  <OptionsSignalCard ticker={selectedMarket.ticker} interval="5m" />
                </AdaptivePanel>
              </div>,
              <div key="heatmap" className={gridItemClass}>
                <AdaptivePanel tab={tab} panelId="heatmap" isEditMode={isEditMode}>
                  <div className="h-full overflow-y-auto">
                    <OrderFlowHeatmap data={orderFlowData} region={selectedMarket.region} isLoading={isIntelLoading} />
                  </div>
                </AdaptivePanel>
              </div>,
              <div key="setup" className={gridItemClass}>
                <AdaptivePanel tab={tab} panelId="setup" isEditMode={isEditMode}>
                  <div className="p-4">
                    <div className="text-[10px] font-mono text-muted-foreground uppercase mb-1">Recommended Strategy</div>
                    <CardTitle className="text-xl font-bold tracking-tight">{strategy?.name}</CardTitle>
                    <p className="text-xs mt-2 text-muted-foreground">{strategy?.description}</p>
                    <Button size="sm" className="w-full mt-4" disabled={!regimeStatus.isTradeAllowed || riskStatus.isLocked} onClick={handleApproveTrade}>
                      Execute Strategy
                    </Button>
                  </div>
                </AdaptivePanel>
              </div>,
              <div key="risk" className={gridItemClass}>
                <AdaptivePanel tab={tab} panelId="risk" isEditMode={isEditMode}>
                  <div className="p-4 h-full">
                    <div className="text-[10px] font-mono uppercase tracking-widest text-primary mb-4">Risk Protocols</div>
                    <RiskSummarySection risk={riskStatus} market={selectedMarket} />
                  </div>
                </AdaptivePanel>
              </div>,
              <div key="technical" className={gridItemClass}>
                <AdaptivePanel tab={tab} panelId="technical" isEditMode={isEditMode}>
                  <TechnicalIntelSidebar ictData={ictData} volumeData={volumeData} timingData={timingData} region={selectedMarket.region} isLoading={isIntelLoading} />
                </AdaptivePanel>
              </div>,
              <div key="broker" className={gridItemClass}>
                <AdaptivePanel tab={tab} panelId="broker" isEditMode={isEditMode}>
                  <div className="p-4">
                    <BrokerStatus broker={broker} />
                    <OrderEntry broker={broker} defaultSymbol={selectedMarket.ticker.replace('^', '')} />
                  </div>
                </AdaptivePanel>
              </div>,
              <div key="alpha" className={gridItemClass}>
                <AdaptivePanel tab={tab} panelId="alpha" isEditMode={isEditMode}>
                  <AlphaDiscoverCard onSelectTicker={handleSelectAlpha} />
                </AdaptivePanel>
              </div>,
            ] : tab === 'analytics' ? [
              <div key="institutional" className={gridItemClass}>
                <AdaptivePanel tab={tab} panelId="institutional" isEditMode={isEditMode}>
                  <div className="p-6 h-full overflow-y-auto custom-scrollbar">
                    <InstitutionalSection ticker={selectedMarket.ticker} />
                  </div>
                </AdaptivePanel>
              </div>,
              <div key="regime-detail" className={gridItemClass}>
                <AdaptivePanel tab={tab} panelId="regime-detail" isEditMode={isEditMode}>
                  <div className="p-6 h-full border-t border-border flex flex-col justify-between">
                    <div>
                      <h2 className="text-xl font-bold mb-4 uppercase font-mono tracking-tighter">Mathematical Regime Analysis</h2>
                      <div className="grid grid-cols-2 gap-8">
                        <div className="space-y-4">
                          <Label className="text-[10px] uppercase font-mono text-muted-foreground">Current State</Label>
                          <div className="text-4xl font-black text-primary uppercase">{regimeStatus.regime}</div>
                          <p className="text-sm opacity-70">Detecting underlying market structure via variance-weighted Bayesian filtering.</p>
                        </div>
                        <div className="bg-primary/5 p-4 rounded-sm border border-primary/20">
                          <Label className="text-[10px] uppercase font-mono text-muted-foreground">Regime Probability</Label>
                          <div className="text-2xl font-mono mt-2">{(regimeStatus.confidence * 100).toFixed(2)}% CONFIDENCE</div>
                        </div>
                      </div>
                    </div>

                    <div className="mt-8 pt-8 border-t border-border/50 grid grid-cols-4 gap-4">
                      <div className="space-y-1">
                        <div className="text-[9px] font-mono text-muted-foreground uppercase">Hurst Exponent</div>
                        <div className="text-lg font-mono font-bold">0.62</div>
                      </div>
                      <div className="space-y-1">
                        <div className="text-[9px] font-mono text-muted-foreground uppercase">Stability Index</div>
                        <div className="text-lg font-mono font-bold">88.2</div>
                      </div>
                      <div className="space-y-1">
                        <div className="text-[9px] font-mono text-muted-foreground uppercase">Model Sync</div>
                        <div className="text-lg font-mono font-bold">99.1%</div>
                      </div>
                    </div>
                  </div>
                </AdaptivePanel>
              </div>,
              <div key="system-monitor" className={gridItemClass}>
                <AdaptivePanel tab={tab} panelId="system-monitor" isEditMode={isEditMode}>
                  <SystemMonitor />
                </AdaptivePanel>
              </div>,
            ] : tab === 'news' ? [
              <div key="news-feed" className={gridItemClass}>
                <AdaptivePanel tab={tab} panelId="news-feed" isEditMode={isEditMode}>
                  <NewsImpactFeed />
                </AdaptivePanel>
              </div>,
            ] : []
            }
          </ResponsiveGrid>
        </>
      )}
    </div>
  );
}

function InstitutionalSection({ ticker }: { ticker: string }) {
  const { riskData, strategyData, timingData, greeksData, isLoading } = useInstitutionalData(ticker);

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-mono font-bold uppercase tracking-widest text-foreground flex items-center gap-3">
        <span className="w-2 h-2 bg-primary rounded-full"></span>
        Central Intelligence
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
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

function RiskSummarySection({ risk, market }: { risk: any, market: any }) {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="flex justify-between items-end">
          <span className="text-[10px] font-bold text-muted-foreground uppercase font-mono tracking-wider">Session Trades</span>
          <span className="text-lg font-mono font-bold text-primary">{risk.tradesToday} / 3</span>
        </div>
        <div className="w-full bg-secondary h-1.5 rounded-full overflow-hidden">
          <div
            className="bg-primary h-full transition-all duration-700"
            style={{ width: `${(risk.tradesToday / 3) * 100}%` }}
          />
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex justify-between items-end">
          <span className="text-[10px] font-bold text-muted-foreground uppercase font-mono tracking-wider">Daily Drawdown</span>
          <span className="text-lg font-mono font-bold">{formatCurrency(risk.dailyLoss, market.region)}</span>
        </div>
        <div className="w-full bg-secondary h-1.5 rounded-full overflow-hidden">
          <div
            className="bg-destructive h-full transition-all duration-700"
            style={{ width: `${Math.min((risk.dailyLoss / 500) * 100, 100)}%` }}
          />
        </div>
      </div>

      {risk.isLocked && (
        <div className="bg-destructive/10 text-destructive p-4 rounded-lg flex items-start gap-3 border border-destructive/20 animate-fade-in">
          <Lock className="w-4 h-4 mt-0.5 shrink-0" />
          <div>
            <p className="text-[10px] font-bold font-mono uppercase tracking-widest">Protocol Lockdown</p>
            <p className="text-[9px] leading-relaxed mt-1 opacity-80">Risk limits breached.</p>
          </div>
        </div>
      )}
    </div>
  );
}
