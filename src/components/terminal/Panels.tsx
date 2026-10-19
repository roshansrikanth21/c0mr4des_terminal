import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import {
  ArrowDownRight, Bot, ArrowUpRight, Ban, CalendarClock, CircleDot, Clock, ExternalLink, Globe2, Layers, Newspaper,
  ShieldAlert, Target, TrendingDown, TrendingUp,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { ago, getJSON, inr, num, signalColor, type Analysis, type NewsItem, type PaperSummary } from '@/lib/api';

export function PanelTitle({ icon: Icon, children, right }: { icon: any; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <div className="flex items-center gap-2">
        <Icon className="w-3.5 h-3.5 text-primary" />
        <span className="text-[10px] font-mono font-black tracking-[0.25em] uppercase">{children}</span>
      </div>
      {right}
    </div>
  );
}

export function Empty({ text = 'Waiting for data...' }: { text?: string }) {
  return <div className="h-full flex items-center justify-center text-[10px] font-mono uppercase tracking-widest text-muted-foreground animate-pulse">{text}</div>;
}

/* ---------------- VERDICT ---------------- */
export function VerdictPanel({ a }: { a: Analysis | null }) {
  if (!a) return <Empty text="Reading the market..." />;
  const tone = a.verdict === 'BUY' ? 'green' : a.verdict === 'SELL' ? 'red' : 'zinc';
  const leanColor = a.lean === 'BUY' ? 'text-green-500' : a.lean === 'SELL' ? 'text-red-500' : 'text-muted-foreground';
  return (
    <div className="h-full p-4 flex flex-col gap-3 overflow-y-auto custom-scrollbar">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-mono font-black tracking-[0.25em] uppercase">Conclusion</span>
        <span className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest">
          {a.instrument.key} · {new Date(a.generated_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>
      <div className={cn('rounded-md border p-4 flex items-center gap-4',
        tone === 'green' && 'border-green-500/40 bg-green-500/10',
        tone === 'red' && 'border-red-500/40 bg-red-500/10',
        tone === 'zinc' && 'border-border bg-muted/30')}>
        {a.verdict === 'BUY' ? <TrendingUp className="w-10 h-10 text-green-500 shrink-0" />
          : a.verdict === 'SELL' ? <TrendingDown className="w-10 h-10 text-red-500 shrink-0" />
            : <Ban className="w-10 h-10 text-muted-foreground shrink-0" />}
        <div className="min-w-0">
          <div className={cn('text-4xl font-black tracking-tighter leading-none',
            tone === 'green' ? 'text-green-500' : tone === 'red' ? 'text-red-500' : 'text-foreground')}>{a.verdict}</div>
          <div className="text-xs mt-1.5 text-muted-foreground">{a.headline}</div>
        </div>
      </div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(96px,1fr))] gap-2">
        <Stat label="Lean" value={a.lean} className={leanColor} />
        <Stat label="Score" value={(a.score > 0 ? '+' : '') + a.score.toFixed(2)} className={signalColor(a.score)} />
        <Stat label="Strength" value={`${Math.round(a.confidence * 100)}%`} />
      </div>
      <div className="h-1.5 w-full rounded-full bg-secondary relative overflow-hidden">
        <div className="absolute top-0 bottom-0 left-1/2 w-px bg-foreground/40" />
        <div className={cn('absolute top-0 bottom-0', a.score >= 0 ? 'left-1/2 bg-green-500' : 'right-1/2 bg-red-500')}
          style={{ width: `${Math.min(50, Math.abs(a.score) * 50)}%` }} />
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">{a.summary}</p>
      {a.gates.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[9px] font-mono uppercase tracking-widest text-amber-500">Why not trading</div>
          {a.gates.map((g, i) => (
            <div key={i} className="flex gap-2 text-xs leading-snug"><ShieldAlert className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" />{g}</div>
          ))}
        </div>
      )}
      {a.triggers?.length > 0 && (
        <div className="text-[10px] font-mono text-muted-foreground">TRIGGER: {a.triggers.join(' · ')}</div>
      )}
    </div>
  );
}

function Stat({ label, value, className }: { label: string; value: React.ReactNode; className?: string }) {
  return (
    <div className="min-w-0 border border-border rounded-md px-2.5 py-2 bg-muted/20">
      <div className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest truncate">{label}</div>
      <div className={cn('text-sm font-mono font-bold mt-0.5', className)}>{value}</div>
    </div>
  );
}

/* ---------------- REASONS ---------------- */
export function ReasonsPanel({ a }: { a: Analysis | null }) {
  if (!a) return <Empty />;
  return (
    <div className="h-full p-4 overflow-y-auto custom-scrollbar">
      <PanelTitle icon={CircleDot}>Why · in plain English</PanelTitle>
      <div className="space-y-2.5">
        {a.reasons.map((r) => (
          <div key={r.factor} className="flex gap-3">
            <span className={cn('mt-1 w-2 h-2 rounded-full shrink-0',
              r.signal === 'bullish' ? 'bg-green-500' : r.signal === 'bearish' ? 'bg-red-500' : 'bg-muted-foreground/40')} />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono font-bold uppercase tracking-wider">{r.factor}</span>
                <span className={cn('text-[9px] font-mono uppercase', signalColor(r.signal))}>{r.signal}</span>
              </div>
              <p className="text-xs leading-relaxed text-muted-foreground">{r.text}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------------- OPTION PLAN ---------------- */
export function OptionPanel({ a }: { a: Analysis | null }) {
  if (!a) return <Empty />;
  const o = a.option;
  const p = a.plan;
  if (!o) return <div className="p-4"><PanelTitle icon={Target}>Trade plan</PanelTitle><p className="text-xs text-muted-foreground">No direction - nothing to plan.</p></div>;
  const live = a.verdict !== 'NO TRADE';
  return (
    <div className="h-full p-4 overflow-y-auto custom-scrollbar">
      <PanelTitle icon={Target} right={<span className={cn('text-[9px] font-mono uppercase tracking-widest', live ? 'text-green-500' : 'text-muted-foreground')}>{live ? 'active setup' : 'if it triggers'}</span>}>
        Trade plan
      </PanelTitle>
      <div className={cn('text-2xl font-black tracking-tight', o.option_type === 'CE' ? 'text-green-500' : 'text-red-500')}>
        {o.side} <span className="text-foreground">{o.strike}</span>
      </div>
      <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-widest mt-0.5">{o.symbol_hint} · lot {o.lot_size}</div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(96px,1fr))] gap-2 mt-3">
        <Stat label="Premium" value={inr(o.premium, 1)} />
        <Stat label="Stop (prem)" value={inr(o.premium_stop, 1)} className="text-red-500" />
        <Stat label="Target (prem)" value={inr(o.premium_target, 1)} className="text-green-500" />
        <Stat label={`Index stop`} value={num(p.stop, 0)} className="text-red-500" />
        <Stat label={`Index target`} value={num(p.target, 0)} className="text-green-500" />
        <Stat label="Reward:Risk" value={`${p.reward_risk.toFixed(1)}x`} />
        <Stat label="Size" value={`${o.lots} lot${o.lots === 1 ? '' : 's'} (${o.quantity})`} />
        <Stat label="Capital" value={inr(o.capital_needed)} />
        <Stat label="Max loss" value={inr(o.max_loss)} className="text-red-500" />
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-[10px] font-mono text-muted-foreground">
        <span>Δ {o.greeks.delta}</span><span>Θ {o.greeks.theta_per_day}/day</span><span>Vega {o.greeks.vega}</span>
        <span>{o.greeks.iv ? `IV ${(o.greeks.iv * 100).toFixed(1)}%` : `VIX ${a.vix?.value ?? '--'}`}</span>
      </div>
      <p className="text-[10px] text-muted-foreground mt-2">Premium: {o.premium_source}. Charges round trip ≈ {inr(o.charges_round_trip)}. Exit everything by {a.session.square_off_by}.</p>
      {o.note && <p className="text-xs text-amber-500 mt-2">{o.note}</p>}
      <LiveOrderButton a={a} />
    </div>
  );
}

/* ---------------- STRUCTURE / LEVELS / PATTERNS ---------------- */
export function StructurePanel({ a }: { a: Analysis | null }) {
  if (!a) return <Empty />;
  const levels = [...a.levels].filter((l) => Math.abs(l.price - a.price) < a.atr * 15).sort((x, y) => y.price - x.price);
  const pats = [...a.patterns].reverse().slice(0, 8);
  return (
    <div className="h-full p-4 overflow-y-auto custom-scrollbar space-y-4">
      <div>
        <PanelTitle icon={Layers}>Candle & structure</PanelTitle>
        <p className="text-xs leading-relaxed">{a.anatomy.text}</p>
        <div className="flex gap-3 mt-2 text-[10px] font-mono text-muted-foreground">
          <span>BODY {a.anatomy.body_pct}%</span><span>UPPER WICK {a.anatomy.upper_wick_pct}%</span>
          <span>LOWER WICK {a.anatomy.lower_wick_pct}%</span><span>SIZE {a.anatomy.range_vs_atr}× ATR</span>
        </div>
        <p className={cn('text-xs mt-2', signalColor(a.structure.trend))}>{a.structure.text}</p>
        {a.structure.swings.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {a.structure.swings.slice(-8).map((s) => (
              <span key={s.time + s.type} className={cn('text-[9px] font-mono px-1.5 py-0.5 rounded-sm border',
                s.label === 'HH' || s.label === 'HL' ? 'border-green-500/40 text-green-500' : 'border-red-500/40 text-red-500')}>
                {s.label} {num(s.price, 0)}
              </span>
            ))}
          </div>
        )}
      </div>
      <div>
        <div className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground mb-1.5">Recent patterns (5m)</div>
        {pats.length === 0 ? <p className="text-xs text-muted-foreground">None in the last hour.</p> : (
          <div className="space-y-1.5">
            {pats.map((p) => (
              <div key={p.time + p.name} className="text-xs">
                <span className={cn('font-mono font-bold', signalColor(p.direction))}>{p.name}</span>
                <span className="text-[10px] font-mono text-muted-foreground ml-2">{new Date(p.time).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}</span>
                {!p.context_ok && <span className="text-[9px] font-mono text-amber-500 ml-2">WEAK CONTEXT</span>}
                <div className="text-muted-foreground leading-snug">{p.meaning}</div>
              </div>
            ))}
          </div>
        )}
      </div>
      <div>
        <div className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground mb-1.5">Key levels</div>
        <div className="space-y-0.5">
          {levels.map((l) => {
            const above = l.price > a.price;
            return (
              <div key={l.name + l.price} className="flex justify-between text-[11px] font-mono">
                <span className={above ? 'text-red-400' : 'text-green-400'}>{above ? '▲' : '▼'} {l.name}</span>
                <span>{num(l.price, 1)} <span className="text-muted-foreground">({num((l.price - a.price) / a.atr, 1)} ATR)</span></span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ---------------- TIMELINE ---------------- */
export function TimelinePanel({ a }: { a: Analysis | null }) {
  if (!a) return <Empty />;
  const s = a.session;
  const phases = [['09:15', 'Open'], ['09:30', 'Trend'], ['11:30', 'Chop'], ['13:30', 'Afternoon'], ['15:00', 'Close']];
  return (
    <div className="h-full p-4 overflow-y-auto custom-scrollbar">
      <PanelTitle icon={Clock} right={<span className={cn('text-[9px] font-mono uppercase tracking-widest', s.is_open ? 'text-green-500' : 'text-muted-foreground')}>{s.is_open ? `● open · ${s.minutes_to_close}m left` : '○ closed'}</span>}>
        Timeline
      </PanelTitle>
      <div className="flex gap-1 mb-3">
        {phases.map(([t, label]) => {
          const active = (s.phase === 'opening' && label === 'Open') || (s.phase === 'morning_trend' && label === 'Trend')
            || (s.phase === 'midday_chop' && label === 'Chop') || (s.phase === 'afternoon' && label === 'Afternoon') || (s.phase === 'closing' && label === 'Close');
          return (
            <div key={t} className={cn('flex-1 rounded-sm border px-1.5 py-1 text-center', active ? 'bg-primary text-primary-foreground border-primary' : 'border-border text-muted-foreground')}>
              <div className="text-[9px] font-mono">{t}</div><div className="text-[9px] font-mono font-bold uppercase">{label}</div>
            </div>
          );
        })}
      </div>
      <p className="text-xs leading-relaxed">{s.phase_note}</p>
      <div className="mt-3 border border-border rounded-md p-3 bg-muted/20">
        <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest">
          <CalendarClock className="w-3.5 h-3.5" /> Expiry {new Date(s.expiry).toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'short' })}
          <span className={cn('ml-auto', s.is_expiry_day ? 'text-amber-500' : 'text-muted-foreground')}>{s.is_expiry_day ? 'TODAY' : `${s.days_to_expiry} day(s)`}</span>
        </div>
        <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed">{s.expiry_note}</p>
      </div>
      {!s.is_open && <p className="text-[10px] font-mono text-muted-foreground mt-2">Next open: {new Date(s.next_open).toLocaleString('en-IN', { weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</p>}
      {a.expected_move_rest_of_day && <p className="text-[10px] font-mono text-muted-foreground mt-1">Expected move (1σ, rest of session): ±{num(a.expected_move_rest_of_day, 0)} pts</p>}
    </div>
  );
}

/* ---------------- GLOBAL ---------------- */
export function GlobalPanel({ a }: { a: Analysis | null }) {
  if (!a) return <Empty />;
  return (
    <div className="h-full p-4 overflow-y-auto custom-scrollbar">
      <PanelTitle icon={Globe2}>Global cues · indirect</PanelTitle>
      <p className={cn('text-xs mb-2', signalColor(a.global.bias))}>{a.global.text}</p>
      {a.vix && (
        <div className="flex justify-between text-[11px] font-mono border-b border-border pb-1.5 mb-1.5">
          <span>India VIX</span><span>{a.vix.value} <span className={signalColor(-a.vix.change_pct)}>({a.vix.change_pct > 0 ? '+' : ''}{a.vix.change_pct}%)</span></span>
        </div>
      )}
      <div className="space-y-1">
        {a.global.cues.filter((c) => c.available).map((c) => (
          <div key={c.symbol} className="flex justify-between text-[11px] font-mono" title={c.why}>
            <span className="text-muted-foreground">{c.label}</span>
            <span className="flex items-center gap-2">
              <span className={c.change_pct! >= 0 ? 'text-green-500' : 'text-red-500'}>{c.change_pct! > 0 ? '+' : ''}{c.change_pct}%</span>
              <span className={cn('w-12 text-right text-[9px]', signalColor(c.effect || 0))}>{c.effect! > 0 ? 'GOOD' : c.effect! < 0 ? 'BAD' : 'FLAT'}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------------- NEWS ---------------- */
export function NewsList({ items, compact = false }: { items: NewsItem[]; compact?: boolean }) {
  if (!items.length) return <p className="text-xs text-muted-foreground">No matching headlines.</p>;
  return (
    <div className="space-y-2">
      {items.map((n) => (
        <a key={n.id} href={n.url} target="_blank" rel="noreferrer"
          className="group flex gap-3 border border-border rounded-md p-2.5 hover:bg-accent/40 transition-colors">
          <div className={cn('w-9 shrink-0 rounded-sm flex flex-col items-center justify-center border',
            n.direction > 0 ? 'border-green-500/40 text-green-500' : n.direction < 0 ? 'border-red-500/40 text-red-500' : 'border-border text-muted-foreground')}>
            {n.direction > 0 ? <ArrowUpRight className="w-4 h-4" /> : n.direction < 0 ? <ArrowDownRight className="w-4 h-4" /> : <CircleDot className="w-3 h-3" />}
            <span className="text-[9px] font-mono">{'●'.repeat(n.impact) || '·'}</span>
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-xs font-semibold leading-snug group-hover:underline">{n.title}</div>
            {!compact && n.why && <div className="text-[11px] text-muted-foreground mt-0.5">{n.why}</div>}
            <div className="flex flex-wrap items-center gap-2 mt-1 text-[9px] font-mono uppercase tracking-widest text-muted-foreground">
              <span>{n.sources.join(' + ')}</span><span>{ago(n.age_minutes)}</span>
              {n.scope !== 'none' && <span className={n.scope === 'direct' ? 'text-primary' : ''}>{n.scope}</span>}
              {!compact && n.keywords.slice(0, 3).map((k) => <span key={k} className="px-1 border border-border rounded-sm normal-case tracking-normal">{k}</span>)}
              <ExternalLink className="w-3 h-3 ml-auto opacity-0 group-hover:opacity-100" />
            </div>
          </div>
        </a>
      ))}
    </div>
  );
}

export function NewsPanel() {
  const [items, setItems] = useState<NewsItem[]>([]);
  useEffect(() => {
    let alive = true;
    const load = () => getJSON<{ items: NewsItem[] }>('/api/news?relevant=true&limit=25').then((r) => alive && setItems(r.items)).catch(() => undefined);
    load();
    const id = window.setInterval(load, 90000);
    return () => { alive = false; window.clearInterval(id); };
  }, []);
  return (
    <div className="h-full p-4 overflow-y-auto custom-scrollbar">
      <PanelTitle icon={Newspaper}>Market-moving news</PanelTitle>
      <NewsList items={items} compact />
    </div>
  );
}

/* ---------------- PAPER AUTOPILOT ---------------- */
export function PaperPanel({ a }: { a: Analysis | null }) {
  const [sum, setSum] = useState<PaperSummary | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () => getJSON<PaperSummary>('/api/paper').then((r) => alive && setSum(r)).catch(() => undefined);
    load();
    const id = window.setInterval(load, 15000);
    return () => { alive = false; window.clearInterval(id); };
  }, [a?.generated_at]);
  if (!sum) return <Empty />;
  const opens = sum.open.filter((p) => !a || p.instrument === a.instrument.key);
  return (
    <div className="h-full p-4 overflow-y-auto custom-scrollbar">
      <PanelTitle icon={Bot} right={<span className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground">paper · auto</span>}>
        Autopilot
      </PanelTitle>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(96px,1fr))] gap-2">
        <Stat label="Today P&L" value={inr(sum.today.pnl)} className={sum.today.pnl >= 0 ? 'text-green-500' : 'text-red-500'} />
        <Stat label="Trades" value={`${sum.today.trades} (${sum.today.wins} won)`} />
        <Stat label="All-time" value={inr(sum.all_time.pnl)} className={sum.all_time.pnl >= 0 ? 'text-green-500' : 'text-red-500'} />
      </div>
      {Object.keys(sum.by_strategy || {}).length > 0 && (
        <div className="flex gap-3 mt-2 text-[10px] font-mono text-muted-foreground">
          {Object.entries(sum.by_strategy).map(([k, v]) => (
            <span key={k}>{k}: <span className={v.pnl >= 0 ? 'text-green-500' : 'text-red-500'}>{inr(v.pnl)}</span> ({v.wins}/{v.trades})</span>
          ))}
        </div>
      )}
      {opens.length ? opens.map((open) => (
        <div key={open.slot || open.opened_at} className={cn('mt-3 rounded-md border p-3', open.dir > 0 ? 'border-green-500/40 bg-green-500/5' : 'border-red-500/40 bg-red-500/5')}>
          <div className="flex justify-between items-center">
            <span className="text-sm font-black">{open.side} {open.strike} <span className="text-[9px] font-mono text-muted-foreground uppercase">{open.strategy}</span></span>
            <span className={cn('text-sm font-mono font-bold', (open.unrealized ?? 0) >= 0 ? 'text-green-500' : 'text-red-500')}>{inr(open.unrealized ?? 0)}</span>
          </div>
          <div className="text-[10px] font-mono text-muted-foreground mt-1">
            {open.symbol} · {open.quantity} qty · in {num(open.entry_premium)} → now {num(open.mark)}
          </div>
          <div className="text-[10px] font-mono text-muted-foreground">index stop {num(open.index_stop, 0)} · target {num(open.index_target, 0)} · since {new Date(open.opened_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}</div>
        </div>
      )) : (
        <p className="text-xs text-muted-foreground mt-3">No open paper position. The autopilot paper-trades three strategies separately (Engine, Opening Range breakout, First-30 rule) and exits on stop, target or 15:15.</p>
      )}
      {sum.closed.slice(0, 4).map((t) => (
        <div key={t.opened_at + t.instrument} className="flex justify-between text-[11px] font-mono mt-1.5">
          <span className="text-muted-foreground">{new Date(t.opened_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })} {t.instrument} {t.side} · {t.strategy} · {t.reason}</span>
          <span className={(t.pnl ?? 0) >= 0 ? 'text-green-500' : 'text-red-500'}>{inr(t.pnl ?? 0)}</span>
        </div>
      ))}
    </div>
  );
}

/* ---------------- LIVE ORDER (explicit click, server re-checks caps) ---------------- */
export function LiveOrderButton({ a }: { a: Analysis }) {
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { getJSON<{ live_trading: boolean; connected: boolean }>('/api/broker/status').then((r) => setEnabled(r.live_trading)).catch(() => undefined); }, []);
  const o = a.option;
  if (!enabled || !o || a.verdict === 'NO TRADE' || o.lots < 1) return null;
  const limit = Math.round(o.premium * 1.01 * 20) / 20;
  const place = async () => {
    const msg = `REAL ORDER via Angel One\n\nBUY ${o.lots} lot(s) = ${o.quantity} qty\n${o.symbol_hint}\nLIMIT ₹${limit}\nMax loss ≈ ${inr(o.max_loss)}\n\nYou must manage the exit yourself. Place it?`;
    if (!window.confirm(msg)) return;
    setBusy(true);
    try {
      const r = await getJSON<{ ok: boolean; error?: string }>('/api/orders/place', 20000, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: a.instrument.key, expiry: o.expiry, strike: o.strike, option_type: o.option_type, lots: o.lots, side: 'BUY', limit_price: limit, confirm: true }),
      });
      r.ok ? toast.success('Order sent to Angel One') : toast.error(r.error || 'Order rejected');
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <button onClick={place} disabled={busy}
      className={cn('w-full mt-3 py-2.5 rounded-md text-xs font-mono font-black uppercase tracking-widest border',
        o.option_type === 'CE' ? 'border-green-500 text-green-500 hover:bg-green-500/10' : 'border-red-500 text-red-500 hover:bg-red-500/10')}>
      {busy ? 'Sending...' : `Place real order · ${o.lots} lot @ ₹${limit}`}
    </button>
  );
}


/* ---------------- OPENING RANGE PLAYBOOK ---------------- */
export function OrbPanel({ a }: { a: Analysis | null }) {
  const o = a?.orb;
  if (!a || !o) return <Empty />;
  const tone = o.verdict === 'BUY' ? 'text-green-500' : o.verdict === 'SELL' ? 'text-red-500' : 'text-foreground';
  const pos = o.range_high && o.range_low ? Math.max(0, Math.min(100, ((a.price - o.range_low) / (o.range_high - o.range_low)) * 100)) : null;
  return (
    <div className="h-full p-4 overflow-y-auto custom-scrollbar">
      <PanelTitle icon={Target} right={<span className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground">{o.status}</span>}>
        Opening range playbook
      </PanelTitle>
      <div className={cn('text-3xl font-black tracking-tighter', tone)}>{o.verdict}</div>
      <p className="text-xs leading-relaxed mt-1">{o.text}</p>
      {o.range_high && o.range_low && (
        <div className="mt-3">
          <div className="flex justify-between text-[10px] font-mono text-muted-foreground"><span>Low {num(o.range_low, 0)}</span><span>{num(o.range_points, 0)} pts</span><span>High {num(o.range_high, 0)}</span></div>
          <div className="relative h-2 mt-1 rounded-full bg-secondary">
            {pos !== null && <div className="absolute -top-1 w-1 h-4 bg-primary rounded-sm" style={{ left: `calc(${pos}% - 2px)` }} />}
          </div>
          {o.prev_close && <div className="text-[10px] font-mono text-muted-foreground mt-1.5">Yesterday's close {num(o.prev_close, 0)} · price is {a.price > o.prev_close ? 'above (only BUY breaks count)' : 'below (only SELL breaks count)'}</div>}
        </div>
      )}
      {o.option && o.verdict !== 'NO TRADE' && (
        <div className="mt-3 text-xs font-mono">
          <span className={o.option.option_type === 'CE' ? 'text-green-500' : 'text-red-500'}>{o.option.side} {o.option.strike}</span>
          {' '}@ ~{inr(o.option.premium, 1)} · {o.option.lots} lot · stop {num(o.stop, 0)} · target {num(o.target, 0)}
        </div>
      )}
      {a.first30 && (
        <div className="mt-3 border-t border-border pt-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono font-black uppercase tracking-widest">First-30 rule</span>
            <span className={cn('text-xs font-black', a.first30.verdict === 'BUY' ? 'text-green-500' : a.first30.verdict === 'SELL' ? 'text-red-500' : 'text-muted-foreground')}>{a.first30.verdict}</span>
          </div>
          <p className="text-xs text-muted-foreground mt-1">{a.first30.text}</p>
        </div>
      )}
      <p className="text-[10px] text-muted-foreground mt-3">Lab (Jul-Oct 2026): breakout NIFTY 56% winners PF 2.6, SENSEX 46% PF 1.7; first-30 rule PF 2.6-2.9 at ~31% winners. Most profit came in the falling Sep-Oct market. On probation.</p>
    </div>
  );
}
