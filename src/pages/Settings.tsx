import { useEffect, useState } from 'react';
import { Settings as SettingsIcon, Save, PlugZap } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { getJSON, inr } from '@/lib/api';
import { setTheme, setViewMode, useAppearance } from '@/lib/appearance';

interface Risk { capital: number; risk_per_trade_pct: number; max_trades_per_day: number; max_daily_loss_pct: number; autopilot_instruments?: string[] }
interface Broker { configured: boolean; connected: boolean; note: string }

const FIELDS: [keyof Risk, string, string][] = [
  ['capital', 'Trading capital (₹)', 'Money you are willing to use for options. Sizing is based on this.'],
  ['risk_per_trade_pct', 'Risk per trade (%)', 'Max you can lose on one trade. Pros use 0.5-2%.'],
  ['max_trades_per_day', 'Max trades per day', 'Overtrading is the #1 way option buyers bleed. 2-3 is plenty.'],
  ['max_daily_loss_pct', 'Max daily loss (%)', 'Stop trading for the day after losing this much.'],
];

export function Settings() {
  const [risk, setRisk] = useState<Risk | null>(null);
  const [broker, setBroker] = useState<Broker | null>(null);
  const { theme, view } = useAppearance();

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
        <Choice label="Theme" help="Dark is easier on the eyes over a 6-hour session." value={theme}
          options={[['dark', 'Dark'], ['light', 'Light']]} onChange={(v) => setTheme(v as 'dark' | 'light')} />
        <Choice label="Dashboard view" help="Focus shows only what you need mid-trade: chart, verdict, playbook, trade plan and autopilot, bigger."
          value={view} options={[['full', 'Full terminal'], ['focus', 'Focus mode']]} onChange={(v) => setViewMode(v as 'full' | 'focus')} />
      </div>
      {risk && (
        <div className="border border-border rounded-md p-6 bg-card/40 space-y-5">
          {FIELDS.map(([k, label, help]) => (
            <div key={k} className="grid md:grid-cols-2 gap-2 items-center">
              <div>
                <div className="text-xs font-mono font-bold uppercase tracking-wider">{label}</div>
                <div className="text-[11px] text-muted-foreground">{help}</div>
              </div>
              <input type="number" value={risk[k]} step={k === 'capital' ? 1000 : k === 'max_trades_per_day' ? 1 : 0.1}
                onChange={(e) => setRisk({ ...risk, [k]: Number(e.target.value) })}
                className="h-10 px-3 rounded-md border border-input bg-transparent font-mono text-sm" />
            </div>
          ))}
          <Choice label="Autopilot trades" help="With a small account, trade one index. NIFTY has the best 2-year record and cheaper lots."
            value={(risk.autopilot_instruments || ['NIFTY']).join('+')}
            options={[['NIFTY', 'NIFTY only'], ['SENSEX', 'SENSEX only'], ['NIFTY+SENSEX', 'Both']]}
            onChange={(v) => setRisk({ ...risk, autopilot_instruments: v.split('+') })} />
          <div className="text-xs text-muted-foreground font-mono">
            Max risk per trade: {inr(risk.capital * risk.risk_per_trade_pct / 100)} · daily stop: {inr(risk.capital * risk.max_daily_loss_pct / 100)}
          </div>
          <Button onClick={save} className="font-mono uppercase text-xs tracking-widest"><Save className="w-4 h-4 mr-2" />Save</Button>
        </div>
      )}
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
