import { useEffect, useState } from 'react';
import { FlaskConical, RotateCcw, TriangleAlert } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getJSON, inr, type CapitalTest } from '@/lib/api';

const fmtPct = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;

function Cell({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="border border-border rounded-md p-3 bg-card/40">
      <div className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground">{label}</div>
      <div className={cn('text-base font-mono font-bold mt-1', tone)}>{value}</div>
    </div>
  );
}

export function CapitalTest() {
  const [data, setData] = useState<CapitalTest | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => getJSON<CapitalTest>('/api/capital-test').then((r) => { setData(r); setErr(null); }).catch((e) => setErr(String(e)));
  useEffect(() => {
    load();
    const id = window.setInterval(load, 15000);
    return () => window.clearInterval(id);
  }, []);

  const restart = async () => {
    if (!window.confirm('Archive all four books and start a fresh week? Old files are moved, never deleted.')) return;
    setBusy(true);
    try {
      await getJSON<CapitalTest>('/api/capital-test/restart', 30000, { method: 'POST' });
      await load();
    } finally {
      setBusy(false);
    }
  };

  const cases = data?.cases ?? [];
  const ranked = [...cases].sort((a, b) => b.return_pct - a.return_pct);
  const leader = data?.leader ? cases.find((c) => c.id === data.leader) : null;

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="pb-6 border-b border-border flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black tracking-tighter uppercase flex items-center gap-3">
            <FlaskConical className="w-7 h-7" />Capital Test
          </h1>
          <p className="text-sm text-muted-foreground mt-2 max-w-3xl">
            Four isolated paper accounts on the same live signals. No money moves between them. A case that
            cannot fund one lot is archived and reset to its original stake - never topped up from another case.
          </p>
        </div>
        <button
          onClick={restart} disabled={busy}
          className="flex items-center gap-2 border border-border rounded-md px-3 py-2 text-[10px] font-mono uppercase tracking-widest text-muted-foreground hover:text-foreground hover:bg-accent disabled:opacity-50"
        >
          <RotateCcw className="w-3.5 h-3.5" />{busy ? 'Restarting' : 'Restart week'}
        </button>
      </div>

      {err && <div className="border border-red-500/30 bg-red-500/5 rounded-md p-3 text-xs font-mono text-red-400">{err}</div>}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Cell label="Week" value={data?.day_index ? `Day ${Math.min(data.day_index, data.week_days)}/${data.week_days}` : 'Not started'} />
        <Cell label="Started" value={data?.started_at ? data.started_at.slice(0, 10) : 'next session'} />
        <Cell label="Leader by yield" value={leader ? `${leader.id} · ${fmtPct(leader.return_pct)}` : '--'}
          tone={leader ? (leader.return_pct >= 0 ? 'text-green-500' : 'text-red-500') : undefined} />
        <Cell label="Cases" value={`${cases.length} isolated`} />
      </div>

      <div className="overflow-auto border border-border rounded-md">
        <table className="w-full text-xs font-mono">
          <thead className="bg-card">
            <tr className="text-muted-foreground uppercase text-[9px] tracking-widest">
              {['Case', 'Stake', 'Equity', 'Net', 'Yield', 'Trades', 'Win %', 'Payoff', 'Busts', 'CE / PE', 'Charges', 'Open'].map((h) => (
                <th key={h} className="text-left px-3 py-2 whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ranked.map((c) => (
              <tr key={c.id} className="border-t border-border/60 hover:bg-accent/40">
                <td className="px-3 py-2">
                  <div className="font-bold">{c.id} · {c.label}</div>
                  <div className="text-[10px] text-muted-foreground">{c.puts_only ? 'puts only' : `${c.max_lots} lot max`}</div>
                </td>
                <td className="px-3 py-2 whitespace-nowrap">{inr(c.stake)}{c.eras > 1 && <span className="text-muted-foreground"> / {c.eras} eras</span>}</td>
                <td className="px-3 py-2 whitespace-nowrap">{inr(c.equity)}</td>
                <td className={cn('px-3 py-2 whitespace-nowrap font-bold', c.net > 0 ? 'text-green-500' : c.net < 0 ? 'text-red-500' : '')}>{inr(c.net)}</td>
                <td className={cn('px-3 py-2 whitespace-nowrap font-bold', c.return_pct > 0 ? 'text-green-500' : c.return_pct < 0 ? 'text-red-500' : '')}>{fmtPct(c.return_pct)}</td>
                <td className="px-3 py-2">{c.trades}</td>
                <td className="px-3 py-2">{c.win_rate === null ? '--' : `${c.win_rate}%`}</td>
                <td className="px-3 py-2">{c.payoff === null ? '--' : `${c.payoff}x`}</td>
                <td className={cn('px-3 py-2', c.busts > 0 ? 'text-red-500 font-bold' : 'text-muted-foreground')}>{c.busts}</td>
                <td className="px-3 py-2">{c.ce} / {c.pe}</td>
                <td className="px-3 py-2 whitespace-nowrap">{inr(c.charges)}</td>
                <td className="px-3 py-2">{c.open.length}</td>
              </tr>
            ))}
            {!cases.length && (
              <tr><td colSpan={12} className="px-3 py-6 text-center text-muted-foreground">Waiting for the first analysis of the week.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {ranked.map((c) => (
          <div key={c.id} className="border border-border rounded-md p-3 bg-card/40 space-y-2">
            <div className="flex items-baseline justify-between">
              <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">{c.id} · {c.label}</div>
              <div className={cn('text-sm font-mono font-bold', c.era_net > 0 ? 'text-green-500' : c.era_net < 0 ? 'text-red-500' : '')}>{inr(c.era_net)} this era</div>
            </div>
            <p className="text-[11px] leading-snug text-muted-foreground">{c.rule}</p>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] font-mono text-muted-foreground">
              <span>today {c.today.trades} · {inr(c.today.pnl)}</span>
              <span>worst streak {c.worst_streak}</span>
              <span>oversize {c.oversize}</span>
              <span>risk {c.risk_pct}% / day {c.daily_loss_pct}%</span>
            </div>
            {c.open.map((p) => (
              <div key={p.opened_at} className="text-[10px] font-mono border-t border-border/60 pt-1.5">
                OPEN {p.side} {p.symbol} · {p.lots} lot @ {inr(p.entry_premium, 2)}
                <span className={cn('ml-2', (p.unrealized ?? 0) >= 0 ? 'text-green-500' : 'text-red-500')}>{inr(p.unrealized ?? 0)}</span>
              </div>
            ))}
          </div>
        ))}
      </div>

      <div className="border border-border rounded-md p-4 bg-card/40 space-y-2">
        <div className="text-[10px] font-mono uppercase tracking-[0.25em] flex items-center gap-2"><TriangleAlert className="w-3.5 h-3.5" />Read this before drawing a conclusion</div>
        <p className="text-xs text-muted-foreground leading-relaxed">{data?.rules}</p>
        <p className="text-xs text-amber-500/90 leading-relaxed">{data?.note}</p>
      </div>
    </div>
  );
}
