import { useState } from 'react';
import { FlaskConical, Play } from 'lucide-react';
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { getJSON, inr, type Symbol } from '@/lib/api';

interface BT {
  instrument: string; source: string; trades: number; summary: string; win_rate?: number; avg_r?: number;
  expectancy_per_lot?: number; net_pnl_per_lot?: number; profit_factor?: number | null; max_drawdown_per_lot?: number;
  by_exit?: Record<string, number>; from?: string; to?: string; equity?: { time: string; equity: number }[];
  trade_list?: { time: string; verdict: string; entry: number; exit: number; reason: string; points: number; r: number; pnl_per_lot: number }[];
}

export function Backtest() {
  const [symbol, setSymbol] = useState<Symbol>('NIFTY');
  const [res, setRes] = useState<BT | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');

  const run = (refresh = false) => {
    setLoading(true); setErr('');
    getJSON<BT>(`/api/backtest?symbol=${symbol}&refresh=${refresh}`, 300000).then(setRes).catch((e) => setErr(e.message)).finally(() => setLoading(false));
  };

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="pb-6 border-b border-border">
        <h1 className="text-3xl font-black tracking-tighter uppercase flex items-center gap-3"><FlaskConical className="w-7 h-7" />Backtest</h1>
        <p className="text-sm text-muted-foreground mt-2 max-w-3xl">
          Replays the exact live engine bar-by-bar over the last ~60 days of real 5-minute candles. No future data, entries at the
          next candle's open, stop checked before target, square-off 15:15, full charges and 1 point slippage. News is not replayed.
          Option P&amp;L is approximated with delta 0.5. Use it to sanity-check, not to prove an edge.
        </p>
      </div>
      <div className="flex items-center gap-3">
        {(['NIFTY', 'SENSEX'] as Symbol[]).map((s) => (
          <button key={s} onClick={() => setSymbol(s)} className={cn('px-5 py-2 text-xs font-mono font-black tracking-widest uppercase rounded-md border',
            symbol === s ? 'bg-primary text-primary-foreground border-primary' : 'border-border text-muted-foreground')}>{s}</button>
        ))}
        <Button onClick={() => run(false)} disabled={loading} className="font-mono uppercase text-xs tracking-widest">
          <Play className="w-4 h-4 mr-2" />{loading ? 'Running (~1 min)...' : 'Run backtest'}
        </Button>
        {res && <Button variant="ghost" onClick={() => run(true)} disabled={loading} className="text-xs">Re-run fresh</Button>}
      </div>
      {err && <p className="text-sm text-destructive font-mono">{err}</p>}
      {res && (
        <>
          <p className="text-sm">{res.summary}</p>
          {res.trades > 0 && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
                {[['Trades', res.trades], ['Win rate', `${res.win_rate}%`], ['Avg R', res.avg_r],
                  ['Per trade', inr(res.expectancy_per_lot || 0)], ['Profit factor', res.profit_factor ?? '--'], ['Max DD', inr(res.max_drawdown_per_lot || 0)]].map(([k, v]) => (
                  <div key={String(k)} className="border border-border rounded-md p-3 bg-card/40">
                    <div className="text-[9px] font-mono uppercase tracking-widest text-muted-foreground">{k}</div>
                    <div className="text-lg font-mono font-bold mt-1">{v}</div>
                  </div>
                ))}
              </div>
              <div className="h-64 border border-border rounded-md p-3 bg-card/40">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={res.equity}>
                    <XAxis dataKey="time" hide /><YAxis width={60} tick={{ fontSize: 10, fontFamily: 'Geist Mono' }} />
                    <Tooltip contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', fontSize: 11 }} />
                    <Area dataKey="equity" stroke="hsl(var(--primary))" fill="hsl(var(--primary) / 0.1)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <div className="border border-border rounded-md overflow-auto max-h-96">
                <table className="w-full text-xs font-mono">
                  <thead className="sticky top-0 bg-card"><tr className="text-muted-foreground uppercase text-[9px] tracking-widest">
                    {['Time', 'Side', 'Entry', 'Exit', 'Why', 'Pts', 'R', 'P&L / lot'].map((h) => <th key={h} className="text-left p-2">{h}</th>)}</tr></thead>
                  <tbody>
                    {[...(res.trade_list || [])].reverse().map((t) => (
                      <tr key={t.time} className="border-t border-border">
                        <td className="p-2">{new Date(t.time).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
                        <td className={cn('p-2 font-bold', t.verdict === 'BUY' ? 'text-green-500' : 'text-red-500')}>{t.verdict}</td>
                        <td className="p-2">{t.entry}</td><td className="p-2">{t.exit}</td><td className="p-2">{t.reason}</td>
                        <td className="p-2">{t.points}</td><td className="p-2">{t.r}</td>
                        <td className={cn('p-2', t.pnl_per_lot >= 0 ? 'text-green-500' : 'text-red-500')}>{inr(t.pnl_per_lot)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
