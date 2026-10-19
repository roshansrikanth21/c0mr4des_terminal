import { useEffect, useState } from 'react';
import { History, Pause, Play, Square } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { getJSON } from '@/lib/api';

export interface ReplayStatus { active: boolean; day?: string; speed?: number; sim_time?: string; paused?: boolean; finished?: boolean }

const post = (url: string, body?: unknown) =>
  getJSON<ReplayStatus>(url, 20000, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });

export function useReplay() {
  const [st, setSt] = useState<ReplayStatus>({ active: false });
  useEffect(() => {
    let alive = true;
    const load = () => getJSON<ReplayStatus>('/api/replay').then((r) => alive && setSt(r)).catch(() => undefined);
    load();
    const id = window.setInterval(load, 2000);
    return () => { alive = false; window.clearInterval(id); };
  }, []);
  return st;
}

/** Thin banner shown on every page while a replay is running. */
export function ReplayBar() {
  const st = useReplay();
  if (!st.active) return null;
  const t = st.sim_time ? new Date(st.sim_time).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : '--';
  return (
    <div className="sticky top-0 z-30 -mx-6 lg:-mx-12 -mt-6 lg:-mt-12 mb-6 px-6 py-2 bg-amber-500/15 border-b border-amber-500/40 flex flex-wrap items-center gap-3 text-sm">
      <History className="w-4 h-4 text-amber-500" />
      <span className="font-bold text-amber-500">REPLAY</span>
      <span>{st.day && new Date(st.day).toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'short' })} · {t} · {st.speed}x</span>
      {st.finished && <span className="text-muted-foreground">session finished</span>}
      <span className="text-muted-foreground hidden md:inline">Practice only: trades go to a separate replay book.</span>
      <div className="ml-auto flex gap-2">
        <button onClick={() => post(`/api/replay/pause?on=${!st.paused}`)} className="px-2 py-1 rounded border border-amber-500/40 flex items-center gap-1">
          {st.paused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}{st.paused ? 'Resume' : 'Pause'}
        </button>
        <button onClick={() => post('/api/replay/stop').then(() => toast.success('Back to live market'))} className="px-2 py-1 rounded border border-amber-500/40 flex items-center gap-1">
          <Square className="w-3.5 h-3.5" />Stop
        </button>
      </div>
    </div>
  );
}

/** Settings card: pick a past day + speed and start. */
export function ReplayControls() {
  const st = useReplay();
  const [days, setDays] = useState<string[]>([]);
  const [day, setDay] = useState('');
  const [speed, setSpeed] = useState(60);
  useEffect(() => {
    getJSON<{ days: string[] }>('/api/replay/days', 60000).then((r) => { setDays(r.days); setDay(r.days[0] ?? ''); }).catch(() => undefined);
  }, []);
  const start = () => post('/api/replay/start', { day, speed })
    .then(() => toast.success(`Replaying ${day} at ${speed}x - open the Dashboard`))
    .catch((e) => toast.error(e.message));
  return (
    <div className="border border-border rounded-md p-6 bg-card/40 space-y-4">
      <div>
        <div className="text-xs font-mono font-bold uppercase tracking-wider">Replay a past day</div>
        <div className="text-[11px] text-muted-foreground">Runs the whole system on a real past session as if it were live: chart, verdicts, autopilot and Telegram (tagged [REPLAY]). Trades go to a separate practice book.</div>
      </div>
      <div className="flex flex-wrap gap-3 items-center">
        <select value={day} onChange={(e) => setDay(e.target.value)} className="h-10 px-3 rounded-md border border-input bg-transparent text-sm">
          {days.map((d) => <option key={d} value={d}>{new Date(d).toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' })}</option>)}
        </select>
        <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))} className="h-10 px-3 rounded-md border border-input bg-transparent text-sm">
          {[[30, '30x (~12 min/day)'], [60, '60x (~6 min/day)'], [120, '120x (~3 min/day)'], [300, '300x (~1 min/day)']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <button onClick={start} disabled={!day} className={cn('h-10 px-5 rounded-md bg-primary text-primary-foreground text-sm font-bold flex items-center gap-2', !day && 'opacity-50')}>
          <Play className="w-4 h-4" />{st.active ? 'Restart replay' : 'Start replay'}
        </button>
        {st.active && <button onClick={() => post('/api/replay/stop')} className="h-10 px-4 rounded-md border border-border text-sm">Stop</button>}
      </div>
    </div>
  );
}
