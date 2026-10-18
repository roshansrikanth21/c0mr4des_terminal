import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Minus, Move, Plus, RotateCcw, SlidersHorizontal, Zap, Cpu, Wifi, WifiOff } from 'lucide-react';
import { toast } from 'sonner';
// @ts-ignore - react-grid-layout v2 ships these without matching types
import { Responsive, useContainerWidth } from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';
import { useAnalysis, type Analysis, type Symbol } from '@/lib/api';
import { useDashboardStore, type DashboardTab } from '@/hooks/use-dashboard-store';
import { CandleChart } from '@/components/CandleChart';
import {
  GlobalPanel, NewsPanel, OptionPanel, ReasonsPanel, StructurePanel, TimelinePanel, VerdictPanel,
} from '@/components/terminal/Panels';

const ResponsiveGrid: any = Responsive;
const MOBILE_ORDER = ['verdict', 'chart', 'option', 'reasons', 'timeline', 'structure', 'global', 'news'];

/** Narrow screens: one column, conclusion first. */
function stacked(layout: readonly { i: string; h: number }[], cols: number) {
  let y = 0;
  return [...layout]
    .sort((a, b) => MOBILE_ORDER.indexOf(a.i) - MOBILE_ORDER.indexOf(b.i))
    .map((it) => { const out = { i: it.i, x: 0, y, w: cols, h: it.i === 'chart' ? 5 : Math.max(it.h, 4) }; y += out.h; return out; });
}
const SYMBOLS: Symbol[] = ['NIFTY', 'SENSEX'];

export function Dashboard() {
  const [symbol, setSymbol] = useState<Symbol>(() => (localStorage.getItem('symbol') as Symbol) || 'NIFTY');
  const [activeTab, setActiveTab] = useState<DashboardTab>('terminal');
  const { isEditMode, toggleEditMode, resetPanelScales, resetLayout } = useDashboardStore();
  const { data, error, live, updatedAt } = useAnalysis(symbol);
  const lastVerdict = useRef<string | null>(null);

  useEffect(() => { localStorage.setItem('symbol', symbol); lastVerdict.current = null; }, [symbol]);

  // React to the live market: notify when the verdict flips during market hours.
  useEffect(() => {
    if (!data) return;
    const v = data.verdict;
    if (lastVerdict.current && lastVerdict.current !== v && data.session.is_open) {
      const fn = v === 'BUY' ? toast.success : v === 'SELL' ? toast.error : toast.message;
      fn(`${symbol}: ${v}`, { description: data.headline, duration: 12000 });
      if ('Notification' in window && Notification.permission === 'granted') {
        new Notification(`${symbol}: ${v}`, { body: data.headline });
      }
    }
    lastVerdict.current = v;
  }, [data, symbol]);

  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission().catch(() => undefined);
  }, []);

  return (
    <div className="space-y-6 pb-24 w-full px-4 lg:px-6">
      {/* --- PRO HEADER --- */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-8 pb-6 border-b border-border">
        <div className="flex flex-col">
          <h1 className="text-4xl font-black tracking-tighter text-foreground uppercase flex items-center gap-3">
            <Zap className="w-8 h-8 text-primary animate-pulse" />
            C0MR4DE TERMINAL
          </h1>
          <span className="text-[10px] font-mono font-bold tracking-[0.4em] opacity-40 uppercase ml-11">
            NIFTY · SENSEX options desk
          </span>
        </div>

        <div className="flex-1 hidden xl:flex items-center justify-center gap-14 px-10 border-x border-border/20 mx-10">
          <HeaderStat label="Spot" value={data ? data.price.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '---'} />
          <HeaderStat label="Session" value={data ? (data.session.is_open ? data.session.phase.replace('_', ' ') : 'closed') : '---'}
            dot={data?.session.is_open ? 'bg-green-500' : 'bg-muted-foreground'} />
          <HeaderStat label="Feed" value={data ? (data.data_delayed ? 'Yahoo · delayed' : 'Angel · live') : '---'}
            dot={data && !data.data_delayed ? 'bg-green-500' : 'bg-amber-500'} />
          <div className="flex flex-col gap-1">
            <span className="text-[9px] font-mono font-bold tracking-[0.3em] opacity-40 uppercase leading-none">Stream</span>
            <div className="flex items-center gap-2">
              {live ? <Wifi className="w-3 h-3 text-green-500" /> : <WifiOff className="w-3 h-3 text-muted-foreground" />}
              <span className="text-[11px] font-mono font-bold tracking-tight opacity-70 uppercase">{live ? 'push' : 'polling'}</span>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <div className="flex border border-border rounded-md p-1 bg-muted/20">
            {SYMBOLS.map((s) => (
              <button key={s} onClick={() => setSymbol(s)}
                className={cn('px-5 py-2 text-xs font-mono font-black tracking-widest uppercase rounded-sm transition-all',
                  symbol === s ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}>
                {s}
              </button>
            ))}
          </div>
          <div className={cn('border shadow-sm px-6 py-3 rounded-md min-w-[130px]',
            data?.verdict === 'BUY' ? 'border-green-500/50 bg-green-500/10' : data?.verdict === 'SELL' ? 'border-red-500/50 bg-red-500/10' : 'border-border bg-muted/20')}>
            <div className="text-right">
              <div className="text-[9px] font-mono text-muted-foreground uppercase leading-none mb-1">Verdict</div>
              <span className={cn('text-sm font-black font-mono',
                data?.verdict === 'BUY' ? 'text-green-500' : data?.verdict === 'SELL' ? 'text-red-500' : 'text-primary')}>
                {data?.verdict ?? '...'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {error && !data && (
        <div className="border border-destructive/40 bg-destructive/10 text-sm p-4 rounded-md font-mono">
          Backend unreachable or no data: {error}. Start it with <code>python -m uvicorn backend.app:app --port 8100</code>.
        </div>
      )}

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as DashboardTab)} className="w-full">
        <TabsList className="bg-muted/30 border border-border p-1 h-12 mb-8 flex flex-wrap max-w-fit">
          {([['terminal', 'Market Terminal'], ['context', 'Market Context'], ['news', 'Global News']] as const).map(([v, label]) => (
            <TabsTrigger key={v} value={v} className="px-8 font-mono font-bold tracking-widest uppercase text-[10px] data-[state=active]:bg-primary data-[state=active]:text-primary-foreground transition-all">
              {label}
            </TabsTrigger>
          ))}
        </TabsList>
        {(['terminal', 'context', 'news'] as DashboardTab[]).map((tab) => (
          <TabsContent key={tab} value={tab} className="mt-0">
            {activeTab === tab && <DashboardGrid tab={tab} symbol={symbol} data={data} />}
          </TabsContent>
        ))}
      </Tabs>

      {/* --- FOOTER STICKY --- */}
      <div className="fixed bottom-0 left-0 w-full bg-background/95 backdrop-blur-sm border-t border-border p-3 shadow-lg z-40">
        <div className="px-8 flex justify-between items-center w-full">
          <div className="flex items-center gap-3">
            <div className={cn('h-2.5 w-2.5 rounded-full', data?.session.is_open ? 'bg-green-500 animate-pulse' : 'bg-muted-foreground')} />
            <Button variant="outline" size="sm" className="h-8 border-primary/20 bg-primary/5 hover:bg-primary/10 transition-all"
              onClick={() => { resetLayout(activeTab); toast.success('Dashboard arrangement reset.'); }}>
              <RotateCcw className="w-4 h-4 mr-2" />Reset Arrangement
            </Button>
            <Button variant={isEditMode ? 'default' : 'outline'} size="sm" className="h-8 transition-all"
              onClick={() => { toggleEditMode(); toast.success(isEditMode ? 'Layout locked.' : 'Drag/resize panels now.'); }}>
              <Move className="w-4 h-4 mr-2" />{isEditMode ? 'Lock Layout' : 'Customize Layout'}
            </Button>
            <Button variant="ghost" size="sm" className="h-8 text-muted-foreground"
              onClick={() => { resetPanelScales(activeTab); toast.success('Panel text scaling reset.'); }}>
              <SlidersHorizontal className="w-4 h-4 mr-2" />Reset Text Scale
            </Button>
          </div>
          <span className="text-xs font-mono text-muted-foreground hidden md:block">
            {symbol} | {data ? `UPDATED ${new Date(updatedAt).toLocaleTimeString('en-IN')}` : 'SYNCING'} | NOT FINANCIAL ADVICE
          </span>
        </div>
      </div>
    </div>
  );
}

function HeaderStat({ label, value, dot }: { label: string; value: string; dot?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[9px] font-mono font-bold tracking-[0.3em] opacity-40 uppercase leading-none">{label}</span>
      <div className="flex items-center gap-2">
        {dot ? <span className={cn('w-2 h-2 rounded-full', dot)} /> : <Cpu className="w-3 h-3 text-primary/40" />}
        <span className="text-[11px] font-mono font-bold tracking-tight opacity-80 uppercase whitespace-nowrap">{value}</span>
      </div>
    </div>
  );
}

function AdaptivePanel({ tab, panelId, isEditMode, children }: { tab: DashboardTab; panelId: string; isEditMode: boolean; children: React.ReactNode }) {
  const panelScale = useDashboardStore((s) => s.panelScales[tab]?.[panelId] ?? 1);
  const setPanelScale = useDashboardStore((s) => s.setPanelScale);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [autoScale, setAutoScale] = useState(1);

  useEffect(() => {
    if (!hostRef.current || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0]?.contentRect ?? { width: 0, height: 0 };
      if (!width || !height) return;
      setAutoScale(Math.max(0.85, Math.min(1.1, Math.min(width / 520, height / 300))));
    });
    observer.observe(hostRef.current);
    return () => observer.disconnect();
  }, []);

  const finalScale = useMemo(() => Math.max(0.75, Math.min(1.3, autoScale * panelScale)), [autoScale, panelScale]);

  return (
    <div ref={hostRef} className="relative h-full w-full overflow-hidden">
      {isEditMode && (
        <div className="absolute top-2 right-2 z-20 flex items-center gap-1 rounded-md border border-border/60 bg-background/90 px-1.5 py-1 backdrop-blur">
          <Button size="icon" variant="ghost" className="h-5 w-5" onClick={() => setPanelScale(tab, panelId, panelScale - 0.05)}><Minus className="w-3 h-3" /></Button>
          <button className="text-[9px] min-w-[46px] text-center font-mono text-muted-foreground" onClick={() => setPanelScale(tab, panelId, 1)}>
            {Math.round(finalScale * 100)}%
          </button>
          <Button size="icon" variant="ghost" className="h-5 w-5" onClick={() => setPanelScale(tab, panelId, panelScale + 0.05)}><Plus className="w-3 h-3" /></Button>
        </div>
      )}
      <div className="h-full w-full overflow-hidden transition-[font-size] duration-200" style={{ fontSize: `${finalScale}em` }}>
        {children}
      </div>
    </div>
  );
}

function DashboardGrid({ tab, symbol, data }: { tab: DashboardTab; symbol: Symbol; data: Analysis | null }) {
  const { layouts, isEditMode, updateLayout } = useDashboardStore();
  const layout = layouts[tab];
  const { width, containerRef, mounted } = useContainerWidth();

  const panels: Record<string, React.ReactNode> = {
    chart: <CandleChart symbol={symbol} analysis={data} />,
    verdict: <VerdictPanel a={data} />,
    reasons: <ReasonsPanel a={data} />,
    option: <OptionPanel a={data} />,
    timeline: <TimelinePanel a={data} />,
    structure: <StructurePanel a={data} />,
    global: <GlobalPanel a={data} />,
    news: <NewsPanel />,
  };

  const gridItemClass = cn(
    'h-full w-full overflow-hidden rounded-lg bg-card/40 backdrop-blur-sm border border-border shadow-sm transition-all',
    isEditMode && 'ring-2 ring-primary ring-offset-2 cursor-move border-dashed border-primary/50 bg-primary/5',
  );

  return (
    <div ref={containerRef} className="h-full relative z-10 w-full min-h-[800px]">
      {mounted && (
        <ResponsiveGrid
          className="layout"
          layouts={{ lg: layout, md: layout, sm: stacked(layout, 6), xs: stacked(layout, 4), xxs: stacked(layout, 2) }}
          breakpoints={{ lg: 1000, md: 820, sm: 620, xs: 420, xxs: 0 }}
          cols={{ lg: 12, md: 12, sm: 6, xs: 4, xxs: 2 }}
          rowHeight={100}
          isDraggable={isEditMode}
          isResizable={isEditMode}
          onLayoutChange={(l: any, all: any) => { if (isEditMode) updateLayout(tab, all?.lg ?? l); }}
          margin={[24, 24]}
          width={width}
        >
          {layout.map((item) => (
            <div key={item.i} className={gridItemClass}>
              <AdaptivePanel tab={tab} panelId={item.i} isEditMode={isEditMode}>{panels[item.i]}</AdaptivePanel>
            </div>
          ))}
        </ResponsiveGrid>
      )}
    </div>
  );
}
