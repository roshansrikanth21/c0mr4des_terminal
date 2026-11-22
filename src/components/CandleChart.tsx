import { useEffect, useRef, useState } from 'react';
import {
  CandlestickSeries, ColorType, createChart, createSeriesMarkers, CrosshairMode, LineStyle, LineSeries,
  type IChartApi, type ISeriesApi, type SeriesMarker, type Time, type IPriceLine, type ISeriesMarkersPluginApi,
} from 'lightweight-charts';
import { Activity } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getJSON, usePredict, type Analysis, type Candle, type FanStep, type Symbol } from '@/lib/api';
import { cssColor, useAppearance } from '@/lib/appearance';

const IST_OFFSET = 19800; // chart renders UTC; shift so the axis reads Indian time
const INTERVALS = ['1m', '5m', '15m', '1d'] as const;
type Interval = (typeof INTERVALS)[number];

type ForecastSeries = { median: ISeriesApi<'Line'>; hi: ISeriesApi<'Line'>; lo: ISeriesApi<'Line'> };

const LEVEL_COLORS: Record<string, string> = {
  'Prev Day High': '#f59e0b', 'Prev Day Low': '#f59e0b', 'Prev Close': '#a1a1aa',
  'Opening Range High': '#3b82f6', 'Opening Range Low': '#3b82f6', 'CPR Pivot': '#a855f7',
};

function themeColors() {
  const dark = document.documentElement.classList.contains('dark');
  return {
    bg: 'transparent', text: cssColor('--muted-foreground'), grid: cssColor('--border', dark ? 0.6 : 0.7),
    border: cssColor('--border'), up: dark ? '#22c55e' : '#16a34a', down: dark ? '#ef4444' : '#dc2626',
  };
}

export function CandleChart({ symbol, analysis }: { symbol: Symbol; analysis: Analysis | null }) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const forecastRef = useRef<ForecastSeries | null>(null);
  const fittedFanRef = useRef(0);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const linesRef = useRef<IPriceLine[]>([]);
  const [interval, setInterval] = useState<Interval>('5m');
  const [candles, setCandles] = useState<Candle[]>([]);
  const [source, setSource] = useState('');
  const [showLevels, setShowLevels] = useState(true);
  const { theme, preset } = useAppearance();

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
    // Forecast overlay (owner, 9 Nov: the predicted range ON the chart, dotted): the
    // Monte Carlo median path in amber and the 10-90% band edges in dotted violet.
    forecastRef.current = {
      median: chart.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 2, lineStyle: LineStyle.Dotted,
                                            priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }),
      hi: chart.addSeries(LineSeries, { color: 'rgba(139, 92, 246, 0.8)', lineWidth: 1, lineStyle: LineStyle.Dotted,
                                        priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }),
      lo: chart.addSeries(LineSeries, { color: 'rgba(139, 92, 246, 0.8)', lineWidth: 1, lineStyle: LineStyle.Dotted,
                                        priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }),
    };
    markersRef.current = createSeriesMarkers(series, []);
    return () => {
      chart.remove();
      chartRef.current = null; seriesRef.current = null; forecastRef.current = null;
    };
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

  // forecast overlay (owner, 9 Nov): fan.today continues the candles from where they end
  const { data: pred } = usePredict(symbol);
  useEffect(() => {
    const f = forecastRef.current;
    if (!f) return;
    const fan = interval === '5m' ? pred?.fan?.today : undefined;
    if (!fan?.length) {
      f.median.setData([]); f.hi.setData([]); f.lo.setData([]);
      return;
    }
    const rows = (get: (s: FanStep) => number) =>
      fan.map((s) => ({ time: (Math.floor(new Date(s.t).getTime() / 1000) + IST_OFFSET) as Time, value: get(s) }));
    f.median.setData(rows(s => s.median));
    f.hi.setData(rows(s => s.q90));
    f.lo.setData(rows(s => s.q10));
    // refit only as the fan actually changes length, so polls don't jiggle the viewport
    if (fittedFanRef.current !== fan.length) {
      fittedFanRef.current = fan.length;
      chartRef.current?.timeScale().fitContent();
    }
  }, [pred?.fan?.today, interval]);

  useEffect(() => {
    const c = themeColors();
    chartRef.current?.applyOptions({
      layout: { background: { type: ColorType.Solid, color: c.bg }, textColor: c.text },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      rightPriceScale: { borderColor: c.border }, timeScale: { borderColor: c.border },
    });
    seriesRef.current?.applyOptions({ upColor: c.up, downColor: c.down, borderUpColor: c.up, borderDownColor: c.down, wickUpColor: c.up, wickDownColor: c.down });
  }, [theme, preset]);

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
          {pred?.fan?.today?.length ? (
            <span className="text-[9px] font-mono uppercase tracking-widest px-2 py-0.5 rounded-sm border border-violet-500/40 text-violet-400">
              MC+Bayes forecast · dotted
            </span>
          ) : null}
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
