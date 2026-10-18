import { useEffect, useState } from 'react';
import { History } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getJSON } from '@/lib/api';

interface Row {
  generated_at: string; instrument: string; verdict: string; lean: string; score: number; price: number;
  option: string | null; plan: { stop: number; target: number; reward_risk: number };
}

export function SignalLog() {
  const [rows, setRows] = useState<Row[]>([]);
  useEffect(() => { getJSON<{ items: Row[] }>('/api/signals/log?limit=300').then((r) => setRows(r.items)).catch(() => undefined); }, []);
  return (
    <div className="space-y-6 max-w-6xl">
      <div className="pb-6 border-b border-border">
        <h1 className="text-3xl font-black tracking-tighter uppercase flex items-center gap-3"><History className="w-7 h-7" />Signal Log</h1>
        <p className="text-sm text-muted-foreground mt-2 max-w-3xl">
          Every verdict change during market hours is written to <code>data/signals.jsonl</code>. This is your real track record:
          check it against what the market actually did before trusting the tool with size.
        </p>
      </div>
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
