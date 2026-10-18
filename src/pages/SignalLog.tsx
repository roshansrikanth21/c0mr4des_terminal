import { useEffect, useState } from 'react';
import { History } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getJSON, inr, type PaperSummary } from '@/lib/api';

interface Row {
  generated_at: string; instrument: string; verdict: string; lean: string; score: number; price: number;
  option: string | null; plan: { stop: number; target: number; reward_risk: number };
}

export function SignalLog() {
  const [rows, setRows] = useState<Row[]>([]);
  const [paper, setPaper] = useState<PaperSummary | null>(null);
  useEffect(() => {
    getJSON<{ items: Row[] }>('/api/signals/log?limit=300').then((r) => setRows(r.items)).catch(() => undefined);
    getJSON<PaperSummary>('/api/paper').then(setPaper).catch(() => undefined);
  }, []);
  return (
    <div className="space-y-6 max-w-6xl">
      <div className="pb-6 border-b border-border">
        <h1 className="text-3xl font-black tracking-tighter uppercase flex items-center gap-3"><History className="w-7 h-7" />Trade Journal</h1>
        <p className="text-sm text-muted-foreground mt-2 max-w-3xl">
          Every verdict change during market hours is written to <code>data/signals.jsonl</code>. This is your real track record:
          check it against what the market actually did before trusting the tool with size.
        </p>
      </div>
      {paper && (
        <div className="space-y-3">
          <div className="text-[10px] font-mono uppercase tracking-[0.25em]">Paper autopilot</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[['Today', inr(paper.today.pnl)], ['Today trades', `${paper.today.trades} (${paper.today.wins} won)`],
              ['All-time', inr(paper.all_time.pnl)], ['Win rate', paper.all_time.win_rate === null ? '--' : `${paper.all_time.win_rate}%`]].map(([k, v]) => (
              <div key={k} className="border border-border rounded-md p-3 bg-card/40">
                <div className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground">{k}</div>
                <div className="text-lg font-mono font-bold mt-1">{v}</div>
              </div>
            ))}
          </div>
          {paper.closed.length > 0 && (
            <div className="border border-border rounded-md overflow-auto max-h-96">
              <table className="w-full text-xs font-mono">
                <thead className="bg-card sticky top-0"><tr className="text-muted-foreground uppercase text-[9px] tracking-widest">
                  {['Opened', 'Contract', 'Qty', 'In', 'Out', 'Spot in→out', 'Exit', 'Charges', 'P&L'].map((h) => <th key={h} className="text-left p-2">{h}</th>)}</tr></thead>
                <tbody>
                  {paper.closed.map((t) => (
                    <tr key={t.opened_at + t.instrument} className="border-t border-border">
                      <td className="p-2">{new Date(t.opened_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
                      <td className={cn('p-2 font-bold', t.dir > 0 ? 'text-green-500' : 'text-red-500')}>{t.symbol}</td>
                      <td className="p-2">{t.quantity}</td><td className="p-2">{t.entry_premium}</td><td className="p-2">{t.exit_premium}</td>
                      <td className="p-2">{Math.round(t.entry_spot)}→{Math.round(t.exit_spot ?? 0)}</td><td className="p-2">{t.reason}</td>
                      <td className="p-2">{inr(t.charges ?? 0)}</td>
                      <td className={cn('p-2 font-bold', (t.pnl ?? 0) >= 0 ? 'text-green-500' : 'text-red-500')}>{inr(t.pnl ?? 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="text-[10px] font-mono uppercase tracking-[0.25em] pt-4">Verdict changes</div>
        </div>
      )}
      {rows.length === 0 ? <p className="text-sm text-muted-foreground font-mono">No signals logged yet. They appear once the app runs during market hours.</p> : (
        <div className="border border-border rounded-md overflow-auto">
          <table className="w-full text-xs font-mono">
            <thead className="bg-card"><tr className="text-muted-foreground uppercase text-[9px] tracking-widest">
              {['Time', 'Index', 'Verdict', 'Lean', 'Score', 'Spot', 'Option', 'Stop', 'Target', 'R:R'].map((h) => <th key={h} className="text-left p-2">{h}</th>)}</tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.generated_at + r.instrument} className="border-t border-border">
                  <td className="p-2">{new Date(r.generated_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
                  <td className="p-2">{r.instrument}</td>
                  <td className={cn('p-2 font-bold', r.verdict === 'BUY' ? 'text-green-500' : r.verdict === 'SELL' ? 'text-red-500' : 'text-muted-foreground')}>{r.verdict}</td>
                  <td className="p-2">{r.lean}</td><td className="p-2">{r.score}</td><td className="p-2">{r.price}</td>
                  <td className="p-2">{r.verdict === 'NO TRADE' ? '--' : r.option}</td><td className="p-2">{r.plan.stop}</td>
                  <td className="p-2">{r.plan.target}</td><td className="p-2">{r.plan.reward_risk}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
