import { useEffect, useState } from 'react';
import { ArrowDownRight, ArrowUpRight, Hourglass, ShieldAlert, Wallet } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getJSON, inr, num, type Analysis, type PaperSummary, type Symbol } from '@/lib/api';
import { CandleChart } from '@/components/CandleChart';

type Call = 'BUY' | 'SELL' | 'WAIT';

/** One answer in plain words, driven by the main (2-year validated) strategy: the first-hour breakout. */
function decide(a: Analysis): { call: Call; title: string; detail: string; why: string[] } {
  const o = a.orb;
  const s = a.session;
  const hi = o?.range_high, lo = o?.range_low;
  if (o && o.verdict !== 'NO TRADE' && o.option) {
    const buy = o.verdict === 'BUY';
    return {
      call: buy ? 'BUY' : 'SELL',
      title: `Buy ${o.option.symbol_hint}`,
      detail: `${a.instrument.key} broke ${buy ? 'above' : 'below'} its first-hour range. Get out if ${a.instrument.key} ${buy ? 'falls below' : 'rises above'} ${num(o.stop, 0)}; take profit near ${num(o.target, 0)}. Close everything by ${s.square_off_by}.`,
      why: [o.text],
    };
  }
  const why: string[] = [];
  let detail = '';
  if (!s.is_trading_day || !s.is_open) {
    detail = `Market is closed. Next session ${new Date(s.next_open).toLocaleString('en-IN', { weekday: 'long', hour: '2-digit', minute: '2-digit' })}.`;
  } else if (o?.status === 'forming') {
    detail = `The first hour (09:15-10:15) is still building its range${hi && lo ? ` (${num(lo, 0)} - ${num(hi, 0)} so far)` : ''}. Don't trade yet.`;
  } else if (o?.status === 'waiting' && hi && lo) {
    detail = `Waiting for a breakout. A 5-minute close above ${num(hi, 0)} means BUY, below ${num(lo, 0)} means SELL.`;
  } else if (o?.status === 'taken') {
    detail = "Today's one breakout trade already happened. Nothing new to do - manage any open trade and rest.";
  } else if (o?.status === 'done') {
    detail = 'No breakout today. A day without a trade is a good day.';
  } else {
    detail = 'Nothing clean to act on right now.';
  }
  if (a.gates[0]) why.push(a.gates[0]);
  return { call: 'WAIT', title: 'Wait', detail, why };
}

export function SimpleView({ a, symbol }: { a: Analysis | null; symbol: Symbol }) {
  const [paper, setPaper] = useState<PaperSummary | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () => getJSON<PaperSummary>('/api/paper').then((r) => alive && setPaper(r)).catch(() => undefined);
    load();
    const id = window.setInterval(load, 15000);
    return () => { alive = false; window.clearInterval(id); };
  }, [a?.generated_at]);

  if (!a) {
    return <div className="h-[50vh] flex items-center justify-center text-sm text-muted-foreground animate-pulse">Reading the market...</div>;
  }
  const d = decide(a);
  const tone = d.call === 'BUY' ? 'green' : d.call === 'SELL' ? 'red' : 'neutral';
  const mood = a.lean === 'BUY' ? 'leaning up' : a.lean === 'SELL' ? 'leaning down' : 'undecided';
  const s = a.session;
  const o = a.orb;
  const now = new Date(a.generated_at);
  const hm = now.getHours() * 60 + now.getMinutes();
  const steps = [
    { t: '09:15 - 10:15', label: 'Watch the first hour build its range', done: hm >= 615, active: hm >= 555 && hm < 615 },
    { t: '10:15 - 15:00', label: o?.range_high ? `Breakout: above ${num(o.range_high, 0)} = BUY, below ${num(o.range_low, 0)} = SELL` : 'Wait for a 5-minute close outside the range', done: o?.status === 'taken' || hm >= 900, active: hm >= 615 && hm < 900 && o?.status !== 'taken' },
    { t: 'By 15:15', label: 'Close any open trade, win or lose', done: hm >= 915, active: hm >= 900 && hm < 915 },
  ];
  const openPos = paper?.open.filter((p) => p.instrument === symbol) ?? [];

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {a.shock?.active && (
        <div className="rounded-lg border border-amber-500/50 bg-amber-500/10 p-4 flex gap-3">
          <ShieldAlert className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
          <div>
            <div className="text-sm font-bold">Unusual day: {a.shock.reasons.join(', ')}</div>
            <p className="text-sm text-muted-foreground mt-1">{a.shock.playbook[0]}</p>
          </div>
        </div>
      )}

      {/* THE ANSWER */}
      <div className={cn('rounded-2xl border p-8 md:p-10',
        tone === 'green' && 'border-green-500/50 bg-green-500/10',
        tone === 'red' && 'border-red-500/50 bg-red-500/10',
        tone === 'neutral' && 'border-border bg-card')}>
        <div className="flex items-start gap-5">
          <div className={cn('rounded-xl p-3 shrink-0', tone === 'green' ? 'bg-green-500/15 text-green-500' : tone === 'red' ? 'bg-red-500/15 text-red-500' : 'bg-muted text-muted-foreground')}>
            {d.call === 'BUY' ? <ArrowUpRight className="w-10 h-10" /> : d.call === 'SELL' ? <ArrowDownRight className="w-10 h-10" /> : <Hourglass className="w-10 h-10" />}
          </div>
          <div className="min-w-0">
            <div className={cn('text-6xl md:text-7xl font-black tracking-tight leading-none',
              tone === 'green' ? 'text-green-500' : tone === 'red' ? 'text-red-500' : 'text-foreground')}>{d.call}</div>
            {d.call !== 'WAIT' && <div className="text-xl font-bold mt-3">{d.title}</div>}
            <p className="text-lg leading-relaxed mt-3">{d.detail}</p>
            {d.call !== 'WAIT' && o?.option && (
              <div className="flex flex-wrap gap-x-6 gap-y-1 mt-4 text-sm text-muted-foreground">
                <span>Price now ~{inr(o.option.premium, 1)}</span>
                <span>1 lot = {o.option.lot_size} qty ≈ {inr(o.option.premium * o.option.lot_size)}</span>
                <span>Max loss ≈ {inr(o.option.max_loss)}</span>
              </div>
            )}
            <p className="text-sm text-muted-foreground mt-4">
              Market mood: <span className="font-semibold text-foreground">{mood}</span> · {s.expiry_note}
            </p>
          </div>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {/* TODAY'S PLAN */}
        <div className="rounded-xl border border-border bg-card p-6">
          <div className="text-sm font-bold mb-4">Today's plan</div>
          <ol className="space-y-4">
            {steps.map((st) => (
              <li key={st.t} className="flex gap-3">
                <span className={cn('mt-1.5 w-2.5 h-2.5 rounded-full shrink-0',
                  st.active ? 'bg-primary ring-4 ring-primary/20' : st.done ? 'bg-muted-foreground/50' : 'bg-border')} />
                <div>
                  <div className={cn('text-xs', st.active ? 'text-primary font-bold' : 'text-muted-foreground')}>{st.t}</div>
                  <div className={cn('text-sm', st.done && !st.active && 'text-muted-foreground line-through decoration-muted-foreground/40')}>{st.label}</div>
                </div>
              </li>
            ))}
          </ol>
          <p className="text-xs text-muted-foreground mt-5">One trade a day, 1 lot. If it hits the stop, you're done for the day.</p>
        </div>

        {/* AUTOPILOT */}
        <div className="rounded-xl border border-border bg-card p-6">
          <div className="flex items-center gap-2 text-sm font-bold mb-4"><Wallet className="w-4 h-4" />Practice account (paper)</div>
          {paper ? (
            <>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs text-muted-foreground">Today</div>
                  <div className={cn('text-3xl font-black', paper.today.pnl >= 0 ? 'text-green-500' : 'text-red-500')}>{inr(paper.today.pnl)}</div>
                  <div className="text-xs text-muted-foreground">{paper.today.trades} trade(s), {paper.today.wins} won</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Since you started</div>
                  <div className={cn('text-3xl font-black', paper.all_time.pnl >= 0 ? 'text-green-500' : 'text-red-500')}>{inr(paper.all_time.pnl)}</div>
                  <div className="text-xs text-muted-foreground">{paper.all_time.trades} trades{paper.all_time.win_rate !== null ? `, ${paper.all_time.win_rate}% won` : ''}</div>
                </div>
              </div>
              {openPos.length > 0 ? openPos.map((p) => (
                <div key={p.slot} className="mt-4 rounded-lg bg-muted/50 p-3 text-sm flex justify-between">
                  <span>Open: {p.side} {p.strike} ({p.strategy})</span>
                  <span className={cn('font-bold', (p.unrealized ?? 0) >= 0 ? 'text-green-500' : 'text-red-500')}>{inr(p.unrealized ?? 0)}</span>
                </div>
              )) : <p className="text-sm text-muted-foreground mt-4">No open practice trade right now.</p>}
            </>
          ) : <p className="text-sm text-muted-foreground">Loading...</p>}
        </div>
      </div>

      {/* SMALL CHART */}
      <div className="rounded-xl border border-border bg-card h-[340px] overflow-hidden">
        <CandleChart symbol={symbol} analysis={a} />
      </div>
    </div>
  );
}
