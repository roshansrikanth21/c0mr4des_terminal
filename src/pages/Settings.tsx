import { useEffect, useState } from 'react';
import { Settings as SettingsIcon, Save, PlugZap } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { getJSON, inr } from '@/lib/api';
import { PRESETS, setPreset, setViewMode, useAppearance } from '@/lib/appearance';
import { ReplayControls } from '@/components/ReplayBar';

interface Risk { capital: number; risk_per_trade_pct: number; max_trades_per_day: number; max_daily_loss_pct: number; max_open_positions?: number; autopilot_instruments?: string[]; autopilot_strategies?: string[] }
interface Broker { configured: boolean; connected: boolean; note: string }

const FIELDS: [keyof Risk, string, string][] = [
  ['capital', 'Trading capital (₹)', 'Money you are willing to use for options. Sizing is based on this.'],
  ['risk_per_trade_pct', 'Risk per trade (%)', 'Max you can lose on one trade. Pros use 0.5-2%.'],
  ['max_trades_per_day', 'Max trades per day', 'Overtrading is the #1 way option buyers bleed. 2-3 is plenty.'],
  ['max_daily_loss_pct', 'Max daily loss (%)', 'Stop trading for the day after losing this much.'],
  ['max_open_positions', 'Open at once', 'How many trades can run together. 1 means you never hold two positions at the same time.'],
];

export function Settings() {
  const [risk, setRisk] = useState<Risk | null>(null);
  const [broker, setBroker] = useState<Broker | null>(null);
  const { preset, view } = useAppearance();

  useEffect(() => {
    getJSON<Risk>('/api/settings').then(setRisk).catch(() => undefined);
    getJSON<Broker>('/api/broker/status').then(setBroker).catch(() => undefined);
  }, []);

  const save = () => {
    if (!risk) return;
    getJSON<Risk>('/api/settings', 10000, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(risk) })
      .then((r) => { setRisk(r); toast.success('Risk settings saved'); })
      .catch((e) => toast.error(e.message));
  };

  return (
    <div className="space-y-8 max-w-3xl">
      <div className="pb-6 border-b border-border">
        <h1 className="text-3xl font-black tracking-tighter uppercase flex items-center gap-3"><SettingsIcon className="w-7 h-7" />Settings</h1>
      </div>
      <div className="border border-border rounded-md p-6 bg-card/40 space-y-5">
        <div className="text-xs font-mono font-bold uppercase tracking-wider">Appearance</div>
        <div>
          <div className="text-xs font-mono font-bold uppercase tracking-wider">Look</div>
          <div className="text-[11px] text-muted-foreground mb-3">Same data and layout, different feel. Soft presets drop the all-caps mono labels and round the corners.</div>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
            {PRESETS.map((p) => (
              <button key={p.id} onClick={() => setPreset(p.id)}
                className={cn('text-left rounded-md border p-3 transition-all hover:border-primary/60',
                  preset === p.id ? 'border-primary ring-2 ring-primary/30' : 'border-border')}>
                <div className="flex h-10 rounded-sm overflow-hidden border border-border mb-2">
                  <div className="w-1/2" style={{ background: p.swatch[0] }} />
                  <div className="w-1/3" style={{ background: p.swatch[1] }} />
                  <div className="flex-1" style={{ background: p.swatch[2] }} />
                </div>
                <div className="text-xs font-bold">{p.name}</div>
                <div className="text-[10px] text-muted-foreground leading-snug mt-0.5">{p.blurb}</div>
              </button>
            ))}
          </div>
        </div>
        <Choice label="Dashboard view" help="Simple: one big BUY / SELL / WAIT answer in plain words. Full: every panel. Focus: the trading panels only, bigger."
          value={view} options={[['simple', 'Simple'], ['full', 'Full terminal'], ['focus', 'Focus mode']]} onChange={(v) => setViewMode(v as 'full' | 'focus' | 'simple')} />
      </div>
      {risk && (
        <div className="border border-border rounded-md p-6 bg-card/40 space-y-5">
          {FIELDS.map(([k, label, help]) => (
            <div key={k} className="grid md:grid-cols-2 gap-2 items-center">
              <div>
                <div className="text-xs font-mono font-bold uppercase tracking-wider">{label}</div>
                <div className="text-[11px] text-muted-foreground">{help}</div>
              </div>
              <input type="number" value={risk[k]} step={k === 'capital' ? 1000 : k === 'max_trades_per_day' || k === 'max_open_positions' ? 1 : 0.1}
                onChange={(e) => setRisk({ ...risk, [k]: Number(e.target.value) })}
                className="h-10 px-3 rounded-md border border-input bg-transparent font-mono text-sm" />
            </div>
          ))}
          <Choice label="Autopilot trades" help="With a small account, trade one index. NIFTY has the best 2-year record and cheaper lots."
            value={(risk.autopilot_instruments || ['NIFTY']).join('+')}
            options={[['NIFTY', 'NIFTY only'], ['SENSEX', 'SENSEX only'], ['NIFTY+SENSEX', 'Both']]}
            onChange={(v) => setRisk({ ...risk, autopilot_instruments: v.split('+') })} />
          <Choice label="Autopilot strategies" help="Engine is off by default: weakest backtest and it lost its first live trades. Switching one off never closes a trade it already holds."
            value={(risk.autopilot_strategies || ['First-Hour', 'First-30', 'Expiry']).join('+')}
            options={[['First-Hour+First-30+Expiry', 'First-Hour + First-30 + Tuesday expiry'], ['First-Hour+First-30', 'First-Hour + First-30'], ['First-Hour', 'First-Hour only'], ['First-Hour+First-30+Expiry+Engine', 'All four']]}
            onChange={(v) => setRisk({ ...risk, autopilot_strategies: v.split('+') })} />
          <CapitalHealth capital={risk.capital} />
          <div className="text-xs text-muted-foreground font-mono">
            Max risk per trade: {inr(risk.capital * risk.risk_per_trade_pct / 100)} · daily stop: {inr(risk.capital * risk.max_daily_loss_pct / 100)}
          </div>
          <Button onClick={save} className="font-mono uppercase text-xs tracking-widest"><Save className="w-4 h-4 mr-2" />Save</Button>
        </div>
      )}
      <ReplayControls />
      {broker && (
        <div className="border border-border rounded-md p-6 bg-card/40">
          <div className="flex items-center gap-2 text-xs font-mono font-bold uppercase tracking-wider">
            <PlugZap className="w-4 h-4" />Angel One data feed
            <span className={cn('ml-auto text-[10px]', broker.connected ? 'text-green-500' : broker.configured ? 'text-amber-500' : 'text-muted-foreground')}>
              {broker.connected ? 'CONNECTED' : broker.configured ? 'CONFIGURED (connects on first request)' : 'NOT CONFIGURED'}
            </span>
          </div>
          <p className="text-sm text-muted-foreground mt-2">{broker.note}</p>
        </div>
      )}
    </div>
  );
}

function Choice({ label, help, value, options, onChange }: { label: string; help: string; value: string; options: [string, string][]; onChange: (v: string) => void }) {
  return (
    <div className="grid md:grid-cols-2 gap-2 items-center">
      <div>
        <div className="text-xs font-mono font-bold uppercase tracking-wider">{label}</div>
        <div className="text-[11px] text-muted-foreground">{help}</div>
      </div>
      <div className="flex border border-border rounded-md p-1 bg-muted/20 w-fit">
        {options.map(([v, l]) => (
          <button key={v} onClick={() => onChange(v)}
            className={cn('px-4 py-1.5 text-[11px] font-mono font-bold uppercase tracking-widest rounded-sm transition-colors',
              value === v ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}>{l}</button>
        ))}
      </div>
    </div>
  );
}

/** Monte Carlo of the 2-year first-hour breakout trades (1 strike OTM, 1 NIFTY lot, 250 trades ~ 1 year). */
const RUIN: [number, number, number][] = [
  // capital, ruin% (all days), ruin% (excluding expiry days - conservative)
  [10000, 41, 64], [20000, 15, 37], [30000, 5, 22], [50000, 1, 9], [75000, 0.2, 3], [100000, 0, 1],
];

function CapitalHealth({ capital }: { capital: number }) {
  const row = [...RUIN].reverse().find(([c]) => capital >= c) ?? RUIN[0];
  const [, ruin, ruinCons] = row;
  const tone = ruinCons <= 5 ? 'border-green-500/40 bg-green-500/10 text-green-500'
    : ruinCons <= 25 ? 'border-amber-500/40 bg-amber-500/10 text-amber-500' : 'border-red-500/40 bg-red-500/10 text-red-500';
  return (
    <div className={cn('rounded-md border p-3 text-xs', tone)}>
      <div className="font-mono font-bold uppercase tracking-widest text-[10px]">Capital check · first-hour breakout, 1 NIFTY lot</div>
      <p className="mt-1 text-foreground">
        Simulated over a year of trades from the 2-year backtest: with this capital the account blows up (can't afford a lot)
        in about <b>{ruin}%</b> of cases, or <b>{ruinCons}%</b> if expiry-day profits don't hold up.
        {ruinCons > 25 ? ' Paper-trade first or build capital - normal losing streaks are bigger than this account.' : ruinCons > 5 ? ' Survivable, but expect deep drawdowns.' : ' Normal losing streaks are survivable at this size.'}
      </p>
    </div>
  );
}
