import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { blink } from '@/lib/blink';
import { useAuth } from '@/hooks/use-auth';
import { toast } from 'sonner';
import { ShieldAlert, Save } from 'lucide-react';

export function Settings() {
  const { user } = useAuth();
  const [isLoading, setIsLoading] = useState(true);
  const [settings, setSettings] = useState({
    maxLossPerTradePct: 1,
    maxLossPerDayPct: 2,
    maxTradesPerDay: 3,
    stopTradingAfterLosses: 2
  });

  useEffect(() => {
    async function fetchSettings() {
      if (!user) return;
      try {
        const list = await blink.db.riskSettings.list({
          where: { user_id: user.id },
          limit: 1
        });
        if (list.length > 0) {
          const s = list[0];
          setSettings({
            maxLossPerTradePct: Number(s.max_loss_per_trade_pct),
            maxLossPerDayPct: Number(s.max_loss_per_day_pct),
            maxTradesPerDay: Number(s.max_trades_per_day),
            stopTradingAfterLosses: Number(s.stop_trading_after_losses)
          });
        }
      } catch (error) {
        console.error('Error fetching settings:', error);
      } finally {
        setIsLoading(false);
      }
    }
    fetchSettings();
  }, [user]);

  const handleSave = async () => {
    if (!user) return;
    try {
      const list = await blink.db.riskSettings.list({
        where: { user_id: user.id },
        limit: 1
      });

      if (list.length > 0) {
        await blink.db.riskSettings.update(list[0].id, {
          max_loss_per_trade_pct: settings.maxLossPerTradePct,
          max_loss_per_day_pct: settings.maxLossPerDayPct,
          max_trades_per_day: settings.maxTradesPerDay,
          stop_trading_after_losses: settings.stopTradingAfterLosses
        });
      } else {
        await blink.db.riskSettings.create({
          user_id: user.id,
          max_loss_per_trade_pct: settings.maxLossPerTradePct,
          max_loss_per_day_pct: settings.maxLossPerDayPct,
          max_trades_per_day: settings.maxTradesPerDay,
          stop_trading_after_losses: settings.stopTradingAfterLosses
        });
      }
      toast.success('Risk parameters updated successfully.');
    } catch (error) {
      toast.error('Failed to update parameters.');
      console.error(error);
    }
  };

  if (isLoading) return <div className="p-10 text-center font-mono animate-pulse">Initializing Security Protocol...</div>;

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tighter mb-2 uppercase">Risk Configuration</h1>
        <p className="text-muted-foreground text-sm">Strict enforcement of capital preservation rules.</p>
      </div>

      <div className="bg-destructive/5 border border-destructive/20 p-4 rounded-sm mb-6 flex gap-4">
        <ShieldAlert className="w-5 h-5 text-destructive shrink-0 mt-0.5" />
        <p className="text-xs text-destructive leading-relaxed font-medium">
          WARNING: These parameters are non-negotiable once a session is active. Changes made will apply to the next trading session.
        </p>
      </div>

      <Card className="border-border">
        <CardHeader>
          <CardTitle className="text-sm font-mono uppercase tracking-widest">Global Parameters</CardTitle>
          <CardDescription>Configure absolute limits for strategy execution.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <Label htmlFor="maxLossTrade" className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Max Loss / Trade (%)</Label>
              <Input 
                id="maxLossTrade" 
                type="number" 
                step="0.1"
                value={settings.maxLossPerTradePct}
                onChange={(e) => setSettings({ ...settings, maxLossPerTradePct: parseFloat(e.target.value) })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="maxLossDay" className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Max Loss / Day (%)</Label>
              <Input 
                id="maxLossDay" 
                type="number" 
                step="0.1"
                value={settings.maxLossPerDayPct}
                onChange={(e) => setSettings({ ...settings, maxLossPerDayPct: parseFloat(e.target.value) })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="maxTrades" className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Max Trades / Day</Label>
              <Input 
                id="maxTrades" 
                type="number" 
                value={settings.maxTradesPerDay}
                onChange={(e) => setSettings({ ...settings, maxTradesPerDay: parseInt(e.target.value) })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="stopLosses" className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">Stop after X Losses</Label>
              <Input 
                id="stopLosses" 
                type="number" 
                value={settings.stopTradingAfterLosses}
                onChange={(e) => setSettings({ ...settings, stopTradingAfterLosses: parseInt(e.target.value) })}
              />
            </div>
          </div>

          <div className="pt-6 border-t border-border">
            <Button onClick={handleSave} className="w-full h-12">
              <Save className="w-4 h-4 mr-2" />
              Store Security Protocol
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="pt-10 text-center">
        <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-[0.2em] leading-relaxed">
          The goal of EDGE-OPS is not to make you smart, but to keep you disciplined.<br />
          If you can't follow your own rules, the market will follow its rules on your account.
        </p>
      </div>
    </div>
  );
}
