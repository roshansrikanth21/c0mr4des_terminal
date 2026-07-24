import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { blink } from '@/lib/blink';
import { useAuth } from '@/hooks/use-auth';
import { toast } from 'sonner';
import { ShieldAlert, Save, Layout, RotateCcw } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'; // Assumes you have this ui component, if not use standard div or Radix
import { Switch } from '@/components/ui/switch';
import { useDashboardStore } from '@/hooks/use-dashboard-store';

import { Skeleton } from '@/components/ui/skeleton';

const LOCAL_RISK_SETTINGS_KEY = 'c0mr4de_risk_settings';

export function Settings() {
  const { user } = useAuth();
  const [isLoading, setIsLoading] = useState(true);
  const [settings, setSettings] = useState({
    maxLossPerTradePct: 1,
    maxLossPerDayPct: 2,
    maxTradesPerDay: 3,
    stopTradingAfterLosses: 2
  });

  const [apiKeys, setApiKeys] = useState({
    angel_client_id: '',
    angel_password: '',
    angel_api_key: '',
    angel_totp_key: '',
    gemini_api_key: '',
    news_api_key: ''
  });
  const [isSavingKeys, setIsSavingKeys] = useState(false);

  const handleSaveApiKeys = async () => {
    setIsSavingKeys(true);
    try {
      const res = await fetch('/api/credentials', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(apiKeys)
      });
      const data = await res.json();
      if (data.status === 'success') {
        toast.success('API Credentials updated & persisted successfully!');
      } else {
        toast.error(data.message || 'Failed to save API credentials.');
      }
    } catch (e: any) {
      toast.error('Error connecting to backend API.');
    } finally {
      setIsSavingKeys(false);
    }
  };

  const { isEditMode, toggleEditMode, resetLayout } = useDashboardStore();

  useEffect(() => {
    async function fetchCredentialsStatus() {
      try {
        const res = await fetch('/api/credentials');
        const data = await res.json();
        if (data.status === 'success') {
          setApiKeys(prev => ({
            ...prev,
            angel_client_id: data.angel_one.client_id || '',
            angel_api_key: data.angel_one.api_key || '',
            gemini_api_key: data.gemini.api_key || '',
            news_api_key: data.news_api.api_key || ''
          }));
        }
      } catch (e) {}
    }
    fetchCredentialsStatus();
  }, []);

  useEffect(() => {
    function loadSettings() {
      try {
        const raw = localStorage.getItem(LOCAL_RISK_SETTINGS_KEY);
        if (raw) {
          const parsed = JSON.parse(raw);
          setSettings({
            maxLossPerTradePct: Number(parsed.maxLossPerTradePct || 1),
            maxLossPerDayPct: Number(parsed.maxLossPerDayPct || 2),
            maxTradesPerDay: Number(parsed.maxTradesPerDay || 3),
            stopTradingAfterLosses: Number(parsed.stopTradingAfterLosses || 2)
          });
        }
      } catch (error) {
        console.warn('Error loading risk settings:', error);
      } finally {
        setIsLoading(false);
      }
    }
    loadSettings();
  }, []);

  const handleSave = async () => {
    try {
      localStorage.setItem(LOCAL_RISK_SETTINGS_KEY, JSON.stringify(settings));
      if (user && isBlinkAvailable()) {
        try {
          const list = await (blink!.db as any).riskSettings.list({
            where: { user_id: user.id },
            limit: 1
          });
          if (list.length > 0) {
            await (blink!.db as any).riskSettings.update(list[0].id, {
              max_loss_per_trade_pct: settings.maxLossPerTradePct,
              max_loss_per_day_pct: settings.maxLossPerDayPct,
              max_trades_per_day: settings.maxTradesPerDay,
              stop_trading_after_losses: settings.stopTradingAfterLosses
            });
          }
        } catch (e) {}
      }
      toast.success('Risk parameters updated successfully.');
    } catch (error) {
      toast.error('Failed to update parameters.');
    }
  };

  const handleResetLayout = () => {
    if (confirm("Are you sure you want to reset the dashboard layout to default?")) {
      resetLayout();
      toast.success("Dashboard layout reset to default.");
    }
  };

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto space-y-8 pb-20">
        <div className="space-y-2">
          <Skeleton className="h-8 w-64 bg-primary/10" />
          <Skeleton className="h-4 w-96 bg-muted/20" />
        </div>
        <div className="space-y-6">
          <Skeleton className="h-12 w-full bg-primary/5 rounded-lg" />
          <Skeleton className="h-64 w-full bg-muted/10 rounded-lg" />
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-20">
      <div>
        <h1 className="text-3xl font-bold tracking-tighter mb-2 uppercase">System Configuration</h1>
        <p className="text-muted-foreground text-sm">Manage risk protocols and interface customization.</p>
      </div>

      <Tabs defaultValue="credentials" className="w-full">
        <TabsList className="grid w-full grid-cols-3 mb-8">
          <TabsTrigger value="credentials">API & Broker Credentials</TabsTrigger>
          <TabsTrigger value="risk">Risk Management</TabsTrigger>
          <TabsTrigger value="customization">Interface Customization</TabsTrigger>
        </TabsList>

        <TabsContent value="credentials" className="space-y-6">
          <Card className="border-border">
            <CardHeader>
              <CardTitle className="text-sm font-mono uppercase tracking-widest flex items-center gap-2">
                Broker & AI Model Keys
              </CardTitle>
              <CardDescription>Configure live broker authentication and intelligence model keys directly from the terminal.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-4">
                <h3 className="text-xs font-mono font-bold uppercase text-primary tracking-wider">Angel One SmartAPI Trading Keys</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <Label htmlFor="angel_client_id" className="text-[10px] font-mono uppercase text-muted-foreground">Angel Client ID</Label>
                    <Input
                      id="angel_client_id"
                      placeholder="e.g. AAAQ749757"
                      value={apiKeys.angel_client_id}
                      onChange={(e) => setApiKeys({ ...apiKeys, angel_client_id: e.target.value })}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="angel_password" className="text-[10px] font-mono uppercase text-muted-foreground">Angel Password / Pin</Label>
                    <Input
                      id="angel_password"
                      type="password"
                      placeholder="••••••••"
                      value={apiKeys.angel_password}
                      onChange={(e) => setApiKeys({ ...apiKeys, angel_password: e.target.value })}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="angel_api_key" className="text-[10px] font-mono uppercase text-muted-foreground">SmartAPI Key</Label>
                    <Input
                      id="angel_api_key"
                      placeholder="e.g. 96vGptbK..."
                      value={apiKeys.angel_api_key}
                      onChange={(e) => setApiKeys({ ...apiKeys, angel_api_key: e.target.value })}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="angel_totp_key" className="text-[10px] font-mono uppercase text-muted-foreground">TOTP Secret Key (2FA)</Label>
                    <Input
                      id="angel_totp_key"
                      type="password"
                      placeholder="32-character TOTP Secret Key"
                      value={apiKeys.angel_totp_key}
                      onChange={(e) => setApiKeys({ ...apiKeys, angel_totp_key: e.target.value })}
                    />
                  </div>
                </div>
              </div>

              <div className="pt-4 border-t border-border space-y-4">
                <h3 className="text-xs font-mono font-bold uppercase text-primary tracking-wider">AI Models & News Feeds</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <Label htmlFor="gemini_api_key" className="text-[10px] font-mono uppercase text-muted-foreground">Google Gemini API Key</Label>
                    <Input
                      id="gemini_api_key"
                      type="password"
                      placeholder="AIzaSy..."
                      value={apiKeys.gemini_api_key}
                      onChange={(e) => setApiKeys({ ...apiKeys, gemini_api_key: e.target.value })}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="news_api_key" className="text-[10px] font-mono uppercase text-muted-foreground">News API Key</Label>
                    <Input
                      id="news_api_key"
                      type="password"
                      placeholder="e.g. 066028..."
                      value={apiKeys.news_api_key}
                      onChange={(e) => setApiKeys({ ...apiKeys, news_api_key: e.target.value })}
                    />
                  </div>
                </div>
              </div>

              <div className="pt-6 border-t border-border">
                <Button onClick={handleSaveApiKeys} disabled={isSavingKeys} className="w-full h-12">
                  <Save className="w-4 h-4 mr-2" />
                  {isSavingKeys ? "Saving Credentials..." : "Save & Sync Credentials"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="risk" className="space-y-6">
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
        </TabsContent>

        <TabsContent value="customization" className="space-y-6">
          <Card className="border-border">
            <CardHeader>
              <CardTitle className="text-sm font-mono uppercase tracking-widest flex items-center gap-2">
                <Layout className="w-4 h-4" />
                Dashboard Layout
              </CardTitle>
              <CardDescription>Customize your workspace. Enable edit mode to resize and rearrange widgets.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-8">
              <div className="flex items-center justify-between p-4 border border-border rounded-lg bg-secondary/10">
                <div className="space-y-1">
                  <Label className="text-base font-bold">Edit Mode</Label>
                  <p className="text-xs text-muted-foreground">Enable to drag, drop, and resize dashboard widgets.</p>
                </div>
                <Switch checked={isEditMode} onCheckedChange={toggleEditMode} />
              </div>

              <div className="flex items-center justify-between p-4 border border-border rounded-lg bg-secondary/10">
                <div className="space-y-1">
                  <Label className="text-base font-bold text-muted-foreground">Reset Layout</Label>
                  <p className="text-xs text-muted-foreground">Restore the default dashboard arrangement.</p>
                </div>
                <Button variant="outline" onClick={handleResetLayout} className="border-dashed">
                  <RotateCcw className="w-4 h-4 mr-2" />
                  Reset to Default
                </Button>
              </div>

              <div className="p-4 bg-primary/5 border border-primary/20 rounded-md">
                <p className="text-[10px] font-mono text-primary uppercase mb-2">Pro Tip</p>
                <p className="text-sm text-muted-foreground">
                  Go to the Dashboard while <strong>Edit Mode</strong> is active to customize your view.
                  Your layout is automatically saved to your local device.
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <div className="pt-10 text-center">
        <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-[0.2em] leading-relaxed">
          The goal of C0MR4DE TERMINAL is not to make you smart, but to keep you disciplined.<br />
          If you can't follow your own rules, the market will follow its rules on your account.
        </p>
      </div>
    </div>
  );
}
