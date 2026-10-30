import {
  ArrowDownRight, ArrowUpRight, Clock, Layers, ShieldAlert, Target, Wallet, Waves,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { inr, num, type Analysis, type FlowTrade, type OptionSide } from '@/lib/api';

/**
 * The decision strip: one glance answer to "what do I do right now".
 *
 * Three things are deliberately separate here, because mixing them is how people lose money:
 *   1. DIRECTION  - what the ladder says the market is doing (call / put / no edge)
 *   2. TIMING     - whether there is a reason to act in this minute (act now / wait)
 *   3. AFFORDABILITY - whether your account can actually buy that side today
 *
 * A bullish read you cannot fund is not a trade. The ticket says so in plain words.
 */

function Bar({ value, tone }: { value: number; tone: 'green' | 'red' | 'muted' }) {
  const pct = Math.min(100, Math.abs(value) * 100);
  return (
    <div className="relative h-1.5 flex-1 rounded-full bg-secondary overflow-hidden">
      <div className="absolute top-0 bottom-0 left-1/2 w-px bg-foreground/30 z-10" />
      <div
        className={cn('absolute top-0 bottom-0',
          tone === 'green' ? 'left-1/2 bg-green-500' : tone === 'red' ? 'right-1/2 bg-red-500' : 'bg-muted-foreground/40')}
        style={{ width: `${pct / 2}%` }}
      />
    </div>
  );
}

function Chip({ children, tone }: { children: React.ReactNode; tone: 'green' | 'red' | 'amber' | 'muted' }) {
  return (
    <span className={cn('px-2 py-0.5 rounded-sm border text-[9px] font-mono font-black uppercase tracking-widest whitespace-nowrap',
      tone === 'green' && 'border-green-500/50 bg-green-500/10 text-green-500',
      tone === 'red' && 'border-red-500/50 bg-red-500/10 text-red-500',
      tone === 'amber' && 'border-amber-500/50 bg-amber-500/10 text-amber-500',
      tone === 'muted' && 'border-border bg-muted/30 text-muted-foreground')}>
      {children}
    </span>
  );
}

const PHASE: Record<string, { label: string; tone: 'green' | 'red' | 'amber' | 'muted'; note: string }> = {
  aligned: { label: 'All timeframes aligned', tone: 'green', note: 'cleanest kind of setup' },
  pullback: { label: 'Pullback inside trend', tone: 'amber', note: 'wait for the fast charts to turn back' },
  conflict: { label: 'Timeframes disagree', tone: 'red', note: 'no side has control' },
  unclear: { label: 'No direction', tone: 'muted', note: 'flat market, options bleed' },
};

export function DecisionPanel({ a }: { a: Analysis | null }) {
  if (!a || !a.mtf || !a.sides) return null;
  const m = a.mtf;
  const s = a.sides;
  const phase = PHASE[m.phase] ?? PHASE.unclear;

  const dir = m.primary?.direction ?? (m.bias > 0.12 ? 1 : m.bias < -0.12 ? -1 : 0);
  const headline = dir > 0 ? 'CALL' : dir < 0 ? 'PUT' : 'NO EDGE';
  const tone = dir > 0 ? 'green' : dir < 0 ? 'red' : 'muted';
  const acting = a.verdict === 'BUY' || a.verdict === 'SELL';
  const ticket = dir > 0 ? s.call : dir < 0 ? s.put : null;

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      {/* ---- headline row ---- */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3 px-4 py-3 border-b border-border bg-muted/20">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-primary" />
          <span className="text-[10px] font-mono font-black tracking-[0.25em] uppercase">Now</span>
        </div>

        <div className="flex items-baseline gap-2">
          <span className={cn('text-3xl font-black tracking-tighter leading-none',
            tone === 'green' ? 'text-green-500' : tone === 'red' ? 'text-red-500' : 'text-muted-foreground')}>
            {headline}
          </span>
          {dir !== 0 && (
            <span className="text-xs font-mono text-muted-foreground">
              buy the {dir > 0 ? 'call (CE)' : 'put (PE)'}
            </span>
          )}
        </div>

        <Chip tone={phase.tone}>{phase.label}</Chip>
        <Chip tone={acting ? 'green' : 'amber'}>
          {acting ? 'Act now' : 'Wait for trigger'}
        </Chip>

        <div className="flex items-center gap-3 ml-auto min-w-[220px]">
          <div className="flex-1">
            <div className="flex justify-between text-[9px] font-mono text-muted-foreground uppercase tracking-widest">
              <span>Strength</span><span>{Math.abs(m.bias).toFixed(2)}</span>
            </div>
            <Bar value={m.bias} tone={tone} />
          </div>
          <div className="flex-1">
            <div className="flex justify-between text-[9px] font-mono text-muted-foreground uppercase tracking-widest">
              <span>Agreement</span><span>{Math.round(m.agreement * 100)}%</span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-secondary overflow-hidden">
              <div className="h-full bg-primary" style={{ width: `${m.agreement * 100}%` }} />
            </div>
          </div>
        </div>
      </div>

      <FlowStrip a={a} />

      <div className="grid gap-0 lg:grid-cols-[1.1fr_1fr_1.1fr] divide-y lg:divide-y-0 lg:divide-x divide-border">
        {/* ---- the ladder ---- */}
        <div className="p-4 space-y-2">
          <div className="text-[9px] font-mono font-black uppercase tracking-[0.25em] text-muted-foreground">
            Timeframe ladder · slow to fast
          </div>
          {m.rows.map((r) => (
            <div key={r.tf} className="flex items-center gap-2">
              <span className="w-[68px] shrink-0 text-[10px] font-mono uppercase text-muted-foreground">{r.label}</span>
              <Bar value={r.score} tone={r.direction > 0 ? 'green' : r.direction < 0 ? 'red' : 'muted'} />
              <span className={cn('w-9 shrink-0 text-right text-[10px] font-mono font-bold',
                r.direction > 0 ? 'text-green-500' : r.direction < 0 ? 'text-red-500' : 'text-muted-foreground')}>
                {r.available ? (r.score > 0 ? '+' : '') + r.score.toFixed(2) : '--'}
              </span>
              {r.direction > 0 ? <ArrowUpRight className="w-3 h-3 text-green-500 shrink-0" />
                : r.direction < 0 ? <ArrowDownRight className="w-3 h-3 text-red-500 shrink-0" />
                  : <span className="w-3 shrink-0" />}
            </div>
          ))}
          <p className="text-[11px] leading-relaxed text-muted-foreground pt-1">{m.story}</p>
        </div>

        {/* ---- yesterday ---- */}
        <div className="p-4 space-y-2">
          <div className="text-[9px] font-mono font-black uppercase tracking-[0.25em] text-muted-foreground">
            Where yesterday ended
          </div>
          {a.yesterday ? (
            <>
              <div className="grid grid-cols-3 gap-2">
                <Field label="High" value={num(a.yesterday.high, 0)} className="text-red-500" />
                <Field label="Low" value={num(a.yesterday.low, 0)} className="text-green-500" />
                <Field label="Close" value={num(a.yesterday.close, 0)} />
              </div>
              <div>
                <div className="flex justify-between text-[9px] font-mono text-muted-foreground uppercase tracking-widest mb-1">
                  <span>Closed at {a.yesterday.close_position_pct}% of the range</span>
                  <span>{num(a.yesterday.range, 0)} pts</span>
                </div>
                <div className="relative h-1.5 w-full rounded-full bg-gradient-to-r from-red-500/40 via-muted to-green-500/40">
                  <div className="absolute -top-1 w-0.5 h-3.5 bg-foreground"
                    style={{ left: `${Math.max(0, Math.min(100, a.yesterday.close_position_pct))}%` }} />
                </div>
              </div>
              {a.yesterday.gap_points !== null && (
                <div className="flex items-center gap-2 text-[11px] font-mono">
                  <span className="text-muted-foreground uppercase tracking-widest text-[9px]">Gap</span>
                  <span className={cn('font-bold', (a.yesterday.gap_points ?? 0) >= 0 ? 'text-green-500' : 'text-red-500')}>
                    {(a.yesterday.gap_points ?? 0) >= 0 ? '+' : ''}{num(a.yesterday.gap_points, 0)} pts
                    ({a.yesterday.gap_pct !== null ? `${a.yesterday.gap_pct >= 0 ? '+' : ''}${a.yesterday.gap_pct}%` : ''})
                  </span>
                </div>
              )}
              <p className="text-[11px] leading-relaxed text-muted-foreground">{a.yesterday.text}</p>
            </>
          ) : <p className="text-xs text-muted-foreground">No previous session yet.</p>}

          {m.warning && (
            <div className="flex gap-2 pt-1 border-t border-border/60 mt-2">
              <ShieldAlert className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" />
              <p className="text-[11px] leading-snug text-amber-500/90">{m.warning}</p>
            </div>
          )}
        </div>

        {/* ---- the two tickets ---- */}
        <div className="p-4 space-y-2">
          <div className="text-[9px] font-mono font-black uppercase tracking-[0.25em] text-muted-foreground">
            One lot, both sides · expiry {new Date(s.expiry).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Ticket side={s.call} highlight={dir > 0} />
            <Ticket side={s.put} highlight={dir < 0} />
          </div>
          <div className={cn('flex gap-2 rounded-md border p-2',
            s.affordable.length === 0 ? 'border-red-500/40 bg-red-500/5' : 'border-border bg-muted/20')}>
            <Wallet className="w-3.5 h-3.5 text-muted-foreground shrink-0 mt-0.5" />
            <p className="text-[11px] leading-snug">{s.text}</p>
          </div>
          {ticket && (
            <div className="flex items-start gap-2 text-[11px]">
              <Target className="w-3.5 h-3.5 text-primary shrink-0 mt-0.5" />
              <div className="min-w-0">
                <span className="font-mono font-bold">{ticket.symbol_hint}</span>
                <span className="text-muted-foreground"> · breakeven {num(ticket.breakeven, 0)} · worst case {inr(ticket.worst_case)}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ---- the why ---- */}
      <details className="border-t border-border group">
        <summary className="px-4 py-2 cursor-pointer text-[9px] font-mono font-black uppercase tracking-[0.25em] text-muted-foreground hover:text-foreground">
          Why the two sides cost different · what moves these numbers
        </summary>
        <div className="px-4 pb-3 space-y-1.5">
          {s.explain.map((t, i) => (
            <p key={i} className="text-[11px] leading-relaxed text-muted-foreground">· {t}</p>
          ))}
          <div className="flex items-center gap-2 pt-1 text-[10px] font-mono text-muted-foreground">
            <Clock className="w-3 h-3" />
            Premiums are estimates unless the broker feed is live. Exit everything by {a.session.square_off_by}.
          </div>
        </div>
      </details>
    </div>
  );
}

function FlowStrip({ a }: { a: Analysis }) {
  const f = a.flow;
  if (!f) return null;
  const c = f.chain;
  const tone = f.verdict === 'bullish' ? 'green' : f.verdict === 'bearish' ? 'red' : 'muted';
  const reads: ({ name: string } & FlowTrade)[] = [];
  if (a.orb?.flow) reads.push({ name: a.orb.name, ...a.orb.flow });
  if (a.first30?.flow) reads.push({ name: a.first30.name, ...a.first30.flow });
  const tr = reads.sort((x, y) => Math.abs(y.support) - Math.abs(x.support))[0] ?? null;
  const trTone = tr?.verdict === 'supports' ? 'green' : tr?.verdict === 'against' ? 'red' : 'amber';
  const volTotal = c ? c.ce_vol + c.pe_vol : 0;
  const callShare = c && volTotal > 0 ? (c.ce_vol / volTotal) * 100 : null;
  const signed = (v: number, d = 2) => `${v >= 0 ? '+' : ''}${v.toFixed(d)}`;
  const compact = (v: number) =>
    `${v >= 0 ? '+' : ''}${new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 }).format(v)}`;
  const comp = (v: number) => (
    <b className={cn('font-mono', v > 0.05 ? 'text-green-500' : v < -0.05 ? 'text-red-500' : 'text-muted-foreground')}>
      {signed(v)}
    </b>
  );

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2 border-b border-border bg-black/40">
      <div className="flex items-center gap-2">
        <Waves className="w-3.5 h-3.5 text-primary" />
        <span className="text-[9px] font-mono font-black tracking-[0.25em] uppercase">Flow</span>
        <Chip tone={tone}>{f.verdict}</Chip>
        <span className="text-[10px] font-mono text-muted-foreground">
          net {signed(f.bias)} · conf {Math.round(f.confidence * 100)}%
        </span>
      </div>
      <div className="flex items-center gap-3 text-[10px] font-mono text-muted-foreground">
        <span>MTF {comp(f.components.mtf)}</span>
        <span>Chain {comp(f.components.chain)}</span>
        {tr?.book && (
          <span>
            Book {comp(tr.book.imbalance)} · spread {tr.book.spread_pct !== null ? `${tr.book.spread_pct}%` : '--'}
          </span>
        )}
      </div>
      {c && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] font-mono text-muted-foreground">
          <span>CE vol {callShare !== null ? `${callShare.toFixed(0)}%` : '--'}</span>
          <span>PCR {c.pcr_oi ?? '--'} · vol {c.pcr_vol ?? '--'}</span>
          <span>
            {c.n
              ? `ΔOI CE ${compact(c.ce_doi)} / PE ${compact(c.pe_doi)} · spot ${signed(c.dprice, 0)}`
              : 'ΔOI: no earlier snapshot yet'}
          </span>
        </div>
      )}
      {tr && <Chip tone={trTone}>{tr.name} {tr.verdict} {signed(tr.support)}</Chip>}
      <span
        className="ml-auto text-[8px] font-mono uppercase tracking-widest text-muted-foreground/60 cursor-help"
        title={f.caveats.join(' ')}
      >
        shadow · never blocks · not backtestable
      </span>
    </div>
  );
}

function Field({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="rounded-md border border-border bg-muted/20 px-2 py-1.5">
      <div className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest">{label}</div>
      <div className={cn('text-sm font-mono font-bold', className)}>{value}</div>
    </div>
  );
}

function Ticket({ side, highlight }: { side: OptionSide; highlight: boolean }) {
  const isCall = side.option_type === 'CE';
  return (
    <div className={cn('rounded-md border p-2 space-y-1',
      highlight ? (isCall ? 'border-green-500/50 bg-green-500/5' : 'border-red-500/50 bg-red-500/5')
        : 'border-border bg-muted/10',
      !side.affordable && 'opacity-50')}>
      <div className="flex items-center justify-between">
        <span className={cn('text-[10px] font-mono font-black uppercase tracking-wider',
          isCall ? 'text-green-500' : 'text-red-500')}>{side.side}</span>
        <span className="text-[8px] font-mono uppercase text-muted-foreground">{side.moneyness}</span>
      </div>
      <div className="text-lg font-black tracking-tight leading-none">{num(side.strike, 0)}</div>
      <div className="text-[11px] font-mono">prem {inr(side.premium, 1)}</div>
      <div className="text-[11px] font-mono font-bold">lot {inr(side.lot_cost)}</div>
      <div className={cn('text-[9px] font-mono uppercase',
        side.affordable ? 'text-green-500' : 'text-red-500')}>
        {side.affordable ? 'you can afford' : 'too expensive'}
      </div>
      <div className="text-[9px] font-mono text-muted-foreground">
        Δ {side.delta.toFixed(2)} · θ {inr(side.theta_per_lot_per_day, 0)}/day
      </div>
    </div>
  );
}
