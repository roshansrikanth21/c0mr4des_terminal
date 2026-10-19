import { useEffect, useRef, useState } from 'react';
import {
  CandlestickSeries, ColorType, createChart, createSeriesMarkers, CrosshairMode, LineStyle,
  type IChartApi, type ISeriesApi, type SeriesMarker, type Time, type IPriceLine, type ISeriesMarkersPluginApi,
} from 'lightweight-charts';
import { Activity } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getJSON, type Analysis, type Candle, type Symbol } from '@/lib/api';
import { useAppearance } from '@/lib/appearance';

const IST_OFFSET = 19800; // chart renders UTC; shift so the axis reads Indian time
const INTERVALS = ['1m', '5m', '15m', '1d'] as const;
type Interval = (typeof INTERVALS)[number];

const LEVEL_COLORS: Record<string, string> = {
  'Prev Day High': '#f59e0b', 'Prev Day Low': '#f59e0b', 'Prev Close': '#a1a1aa',
  'Opening Range High': '#3b82f6', 'Opening Range Low': '#3b82f6', 'CPR Pivot': '#a855f7',
};

function themeColors() {
  const dark = document.documentElement.classList.contains('dark');
  return dark
    ? { bg: 'transparent', text: '#a1a1aa', grid: 'rgba(39,39,42,0.6)', border: '#27272a', up: '#22c55e', down: '#ef4444' }
    : { bg: 'transparent', text: '#71717a', grid: 'rgba(228,228,231,0.6)', border: '#e4e4e7', up: '#16a34a', down: '#dc2626' };
}

export function CandleChart({ symbol, analysis }: { symbol: Symbol; analysis: Analysis | null }) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const linesRef = useRef<IPriceLine[]>([]);
  const [interval, setInterval] = useState<Interval>('5m');
  const [candles, setCandles] = useState<Candle[]>([]);
  const [source, setSource] = useState('');
  const [showLevels, setShowLevels] = useState(true);
  const { theme } = useAppearance();

  // create chart once
  useEffect(() => {
    if (!hostRef.current) return;
    const c = themeColors();
    const chart = createChart(hostRef.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: c.bg }, textColor: c.text, fontFamily: 'Geist Mono, monospace', fontSize: 10 },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      rightPriceScale: { borderColor: c.border },
      timeScale: { borderColor: c.border, timeVisible: true, secondsVisible: false, rightOffset: 6 },
      crosshair: { mode: CrosshairMode.Normal },
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#22c55e', downColor: '#ef4444', borderUpColor: '#22c55e', borderDownColor: '#ef4444',
      wickUpColor: '#22c55e', wickDownColor: '#ef4444',
    });
    chartRef.current = chart;
    seriesRef.current = series;
    markersRef.current = createSeriesMarkers(series, []);
    return () => { chart.remove(); chartRef.current = null; seriesRef.current = null; };
  }, []);

  // 5m candles come with every live analysis; other intervals are fetched on demand
  useEffect(() => {
    if (interval === '5m' && analysis?.candles?.length) {
      setCandles(analysis.candles);
      setSource(analysis.data_source);
    }
  }, [interval, analysis]);

  useEffect(() => {
    if (interval === '5m') return;
    let alive = true;
    const load = () => getJSON<{ candles: Candle[]; source: string }>(`/api/candles?symbol=${symbol}&interval=${interval}`)
      .then((r) => { if (alive) { setCandles(r.candles); setSource(r.source); } })
      .catch(() => undefined);
    load();
    const id = window.setInterval(load, interval === '1d' ? 300000 : 30000);
    return () => { alive = false; window.clearInterval(id); };
  }, [symbol, interval]);

  // push candles
  useEffect(() => {
    const s = seriesRef.current;
    if (!s) return;
    const shift = interval === '1d' ? 0 : IST_OFFSET;
    s.setData(candles.map((k) => ({ ...k, time: (k.time + shift) as Time })));
  }, [candles, interval]);

  useEffect(() => { chartRef.current?.timeScale().fitContent(); }, [symbol, interval]);

  useEffect(() => {
    const c = themeColors();
    chartRef.current?.applyOptions({
      layout: { background: { type: ColorType.Solid, color: c.bg }, textColor: c.text },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      rightPriceScale: { borderColor: c.border }, timeScale: { borderColor: c.border },
    });
    seriesRef.current?.applyOptions({ upColor: c.up, downColor: c.down, borderUpColor: c.up, borderDownColor: c.down, wickUpColor: c.up, wickDownColor: c.down });
  }, [theme]);

  // overlays: pattern markers, key levels, trade plan
  useEffect(() => {
    const s = seriesRef.current;
    if (!s || !analysis) return;
    linesRef.current.forEach((l) => s.removePriceLine(l));
    linesRef.current = [];
    if (interval !== '1d' && showLevels) {
      for (const lv of analysis.levels) {
        if (lv.name === 'Round Number' || lv.name.startsWith('CPR T') || lv.name.startsWith('CPR B')) continue;
        if (Math.abs(lv.price - analysis.price) > analysis.atr * 12) continue;
        linesRef.current.push(s.createPriceLine({
          price: lv.price, color: LEVEL_COLORS[lv.name] || '#71717a', lineWidth: 1, lineStyle: LineStyle.Dotted,
          axisLabelVisible: false, title: lv.name.replace('Swing zone', 'Zone'),
        }));
      }
      if (analysis.verdict !== 'NO TRADE') {
        const p = analysis.plan;
        linesRef.current.push(s.createPriceLine({ price: p.stop, color: '#ef4444', lineWidth: 2, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: 'STOP' }));
        linesRef.current.push(s.createPriceLine({ price: p.target, color: '#22c55e', lineWidth: 2, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: 'TARGET' }));
      }
    }
    const markers: SeriesMarker<Time>[] = [];
    if (interval === '5m') {
      const lastBar = analysis.candles.length ? analysis.candles[analysis.candles.length - 1].time : 0;
      for (const p of analysis.patterns) {
        const t = Math.floor(new Date(p.time).getTime() / 1000);
        // only meaningful patterns (right context) from the last ~2 hours, to keep the chart readable
        if (p.direction === 0 || !p.context_ok || t < lastBar - 2 * 3600) continue;
        markers.push({
          time: (Math.floor(new Date(p.time).getTime() / 1000) + IST_OFFSET) as Time,
          position: p.direction > 0 ? 'belowBar' : 'aboveBar',
          color: p.direction > 0 ? '#22c55e' : '#ef4444',
          shape: p.direction > 0 ? 'arrowUp' : 'arrowDown',
          text: p.name.replace('Bullish ', '').replace('Bearish ', '').replace('Three ', '3 '),
        });
      }
      for (const sw of analysis.structure.swings.slice(-8)) {
        markers.push({
          time: (Math.floor(new Date(sw.time).getTime() / 1000) + IST_OFFSET) as Time,
          position: sw.type === 'H' ? 'aboveBar' : 'belowBar', color: '#a1a1aa', shape: 'circle', size: 0.4, text: sw.label,
        });
      }
    }
    markers.sort((a, b) => (a.time as number) - (b.time as number));
    markersRef.current?.setMarkers(markers);
  }, [analysis, interval, showLevels, candles]);

  const last = candles[candles.length - 1];
  const delayed = source && source !== 'angel_one';

  return (
    <div className="h-full flex flex-col">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 pt-4 pb-2">
        <div className="flex items-center gap-3">
          <Activity className="w-4 h-4 text-primary" />
          <span className="text-xs font-mono font-black tracking-[0.2em] uppercase">{symbol} · Candles</span>
          {last && <span className="text-sm font-mono font-bold">{last.close.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</span>}
          {source && (
            <span className={cn('text-[9px] font-mono uppercase tracking-widest px-2 py-0.5 rounded-sm border',
              delayed ? 'border-amber-500/40 text-amber-500' : 'border-green-500/40 text-green-500')}>
              {delayed ? 'Yahoo · delayed' : 'Angel One · live'}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => setShowLevels((v) => !v)}
            className={cn('px-2 py-1 text-[9px] font-mono uppercase tracking-widest rounded-sm border border-border mr-2',
              showLevels ? 'bg-primary text-primary-foreground' : 'text-muted-foreground')}>Levels</button>
          {INTERVALS.map((iv) => (
            <button key={iv} onClick={() => setInterval(iv)}
              className={cn('px-3 py-1 text-[10px] font-mono font-bold uppercase rounded-sm transition-colors',
                interval === iv ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}>
              {iv}
            </button>
          ))}
        </div>
      </div>
      <div ref={hostRef} className="flex-1 min-h-[240px] px-2 pb-2" />
    </div>
  );
}
