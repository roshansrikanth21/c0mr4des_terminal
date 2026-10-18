import { useEffect, useState } from 'react';
import { Radio, RefreshCw, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { getJSON, signalColor, type NewsItem } from '@/lib/api';
import { NewsList } from '@/components/terminal/Panels';

const KINDS = [['', 'All'], ['news', 'News'], ['official', 'RBI / SEBI'], ['reddit', 'Reddit'], ['x', 'X / Twitter']] as const;
const QUICK = ['RBI', 'FII', 'crude', 'rupee', 'Fed', 'tariff', 'HDFC Bank', 'Reliance', 'SEBI', 'GIFT Nifty', 'inflation', 'expiry'];

interface NewsResponse {
  items: NewsItem[]; sources: Record<string, string>; x_enabled: boolean;
  sentiment: { bias: number; count: number; text: string; drivers: { title: string; why: string }[] };
}

export function NewsRadar() {
  const [query, setQuery] = useState('');
  const [applied, setApplied] = useState('');
  const [kind, setKind] = useState('');
  const [relevant, setRelevant] = useState(true);
  const [data, setData] = useState<NewsResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true);
    const p = new URLSearchParams({ limit: '120', relevant: String(relevant) });
    if (applied) p.set('q', applied);
    if (kind) p.set('kind', kind);
    getJSON<NewsResponse>(`/api/news?${p}`).then(setData).catch(() => undefined).finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    const id = window.setInterval(load, 90000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applied, kind, relevant]);

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 pb-6 border-b border-border">
        <div>
          <h1 className="text-3xl font-black tracking-tighter uppercase flex items-center gap-3"><Radio className="w-7 h-7" />News & Social Radar</h1>
          <p className="text-sm text-muted-foreground mt-2 max-w-2xl">
            Live headlines from Indian market desks, RBI/SEBI, Google News and Reddit, scored for how they move NIFTY/SENSEX:
            <span className="text-green-500"> ▲ up</span>, <span className="text-red-500">▼ down</span>, dots = impact.
          </p>
        </div>
        <Button variant="outline" onClick={load} disabled={loading} className="font-mono uppercase text-xs tracking-widest">
          <RefreshCw className={cn('w-4 h-4 mr-2', loading && 'animate-spin')} />Refresh
        </Button>
      </div>

      {data && (
        <div className="border border-border rounded-md p-4 bg-card/40">
          <div className="text-[10px] font-mono uppercase tracking-[0.25em] mb-1">Mood · last 12h</div>
          <div className={cn('text-lg font-bold', signalColor(data.sentiment.bias))}>{data.sentiment.text}</div>
          {data.sentiment.drivers.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-muted-foreground list-disc pl-4">
              {data.sentiment.drivers.map((d) => <li key={d.title}><span className="text-foreground">{d.title}</span> - {d.why}</li>)}
            </ul>
          )}
        </div>
      )}

      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); setApplied(query.trim()); }}>
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Keyword finder: e.g. crude, RBI, HDFC Bank, tariff"
            className="w-full h-10 pl-9 pr-3 rounded-md border border-input bg-transparent text-sm font-mono focus:outline-none focus:ring-1 focus:ring-ring" />
        </div>
        <Button type="submit" className="font-mono uppercase text-xs tracking-widest">Find</Button>
        {applied && <Button type="button" variant="ghost" onClick={() => { setQuery(''); setApplied(''); }}>Clear</Button>}
      </form>

      <div className="flex flex-wrap gap-2">
        {QUICK.map((k) => (
          <button key={k} onClick={() => { setQuery(k); setApplied(k); }}
            className={cn('px-2.5 py-1 text-[10px] font-mono uppercase tracking-widest rounded-sm border',
              applied === k ? 'bg-primary text-primary-foreground border-primary' : 'border-border text-muted-foreground hover:text-foreground')}>{k}</button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {KINDS.map(([v, label]) => (
          <button key={v} onClick={() => setKind(v)}
            className={cn('px-4 py-2 text-[10px] font-mono font-bold uppercase tracking-widest rounded-md border',
              kind === v ? 'bg-primary text-primary-foreground border-primary' : 'border-border text-muted-foreground')}>{label}</button>
        ))}
        <label className="flex items-center gap-2 ml-auto text-[10px] font-mono uppercase tracking-widest text-muted-foreground cursor-pointer">
          <input type="checkbox" checked={relevant} onChange={(e) => setRelevant(e.target.checked)} />Market-moving only
        </label>
      </div>

      {kind === 'x' && data && !data.x_enabled && (
        <div className="border border-amber-500/40 bg-amber-500/10 rounded-md p-3 text-xs">
          X/Twitter has no free API anymore and the free mirrors (Nitter/xcancel) are blocked. To enable it, buy X API access and put
          <code className="mx-1">X_BEARER_TOKEN=...</code> in <code>backend/.env</code>. Reddit and news sources work without keys.
        </div>
      )}

      {data ? <NewsList items={data.items} /> : <p className="text-xs font-mono text-muted-foreground">Loading feeds...</p>}

      {data && (
        <div className="border-t border-border pt-4">
          <div className="text-[10px] font-mono uppercase tracking-[0.25em] mb-2">Sources</div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(data.sources).map(([k, v]) => (
              <span key={k} className={cn('text-[10px] font-mono px-2 py-1 rounded-sm border',
                v === 'ok' ? 'border-green-500/40 text-green-500' : 'border-border text-muted-foreground')}>{k}: {v}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
