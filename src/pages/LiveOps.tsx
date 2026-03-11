import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface OpsConfigResponse {
  status: string;
  config?: {
    manual_safety_lock: boolean;
    auto_broker_switch_enabled: boolean;
    preferred_live_broker: string;
    last_updated_at?: string | null;
  };
}

interface BrokerStatusResponse {
  connected?: boolean;
  mode?: string;
  status?: string;
  broker?: string;
  pnl?: number;
  balance?: number;
}

interface RoutingStatusResponse {
  status: string;
  notes?: string[];
  recommended_execution_broker?: { broker: string; recommendation: string; score: number };
  recommended_market_data_provider?: { provider: string; recommendation: string; route_score: number };
  execution_brokers?: Array<{
    broker: string;
    current: boolean;
    available: boolean;
    score: number;
    reject_rate: number;
    avg_slippage_bps: number;
    avg_fill_ratio: number;
    avg_time_to_fill_ms: number;
    recommendation: string;
  }>;
  market_data_providers?: Array<{
    provider: string;
    route_score: number;
    priority: number;
    recommendation: string;
    connected?: boolean;
    cooled_down?: boolean;
  }>;
}

interface ExecutionForecastResponse {
  status: string;
  forecast?: {
    sample_count: number;
    basis: string;
    model_basis?: string | null;
    model_confidence?: number;
    quality_score: number;
    expected_slippage_bps: number;
    expected_reject_rate: number;
    expected_fill_ratio: number;
    expected_time_to_fill_ms: number;
    risk_multiplier: number;
    recommendation: string;
  };
}

interface ExportSignalResponse {
  status: string;
  signal?: {
    signal_id?: string;
    symbol?: string;
    action?: string;
    entry?: number;
    stop_loss?: number;
    take_profit?: number;
    confidence?: number;
  };
  message?: string;
}

interface LatestSignalResponse {
  status: string;
  data?: {
    signal_id?: string;
    symbol?: string;
    action?: string;
    entry?: number;
    stop_loss?: number;
    take_profit?: number;
    confidence?: number;
  };
  message?: string;
}

interface ExecutionModelsResponse {
  status: string;
  updated_at?: string | null;
  model_count?: number;
  models?: Array<{
    model_key: string;
    dimensions: {
      model_type: string;
      broker?: string;
      order_type?: string;
      symbol?: string;
      session_bucket?: string;
    };
    sample_count: number;
    quality_score: number;
    confidence: number;
    reject_rate: number;
    avg_slippage_bps: number;
    avg_fill_ratio: number;
    avg_time_to_fill_ms: number;
  }>;
}

interface MemoryStatusResponse {
  status: string;
  active_memories?: number;
  expired_memories?: number;
  remote_enabled?: boolean;
  remote_search_enabled?: boolean;
  memory_type_counts?: Record<string, number>;
}

interface MemoryContextResponse {
  status: string;
  query?: string;
  retrieved?: Array<{
    memory_id?: string;
    content: string;
    source: string;
    similarity: number;
    directional_hint?: number;
    metadata?: {
      memory_type?: string;
      ticker?: string | null;
      interval?: string | null;
      regime?: string | null;
      session_bucket?: string | null;
      setup_family?: string | null;
      confidence?: number;
      freshness_score?: number;
      sample_count?: number;
    };
  }>;
  influence?: {
    memory_count: number;
    average_confidence: number;
    average_freshness: number;
    alignment_bias: number;
    risk_bias: number;
    component_hints?: Record<string, number>;
    notes?: string[];
  };
}

export function LiveOps() {
  const [opsConfig, setOpsConfig] = useState<OpsConfigResponse | null>(null);
  const [brokerStatus, setBrokerStatus] = useState<BrokerStatusResponse | null>(null);
  const [routingStatus, setRoutingStatus] = useState<RoutingStatusResponse | null>(null);
  const [forecast, setForecast] = useState<ExecutionForecastResponse | null>(null);
  const [executionModels, setExecutionModels] = useState<ExecutionModelsResponse | null>(null);
  const [memoryStatus, setMemoryStatus] = useState<MemoryStatusResponse | null>(null);
  const [memoryContext, setMemoryContext] = useState<MemoryContextResponse | null>(null);
  const [latestSignal, setLatestSignal] = useState<LatestSignalResponse | null>(null);
  const [exportResult, setExportResult] = useState<ExportSignalResponse | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const [ticker, setTicker] = useState('^NSEI');
  const [interval, setInterval] = useState('15m');
  const [period, setPeriod] = useState('60d');
  const [capital, setCapital] = useState('100000');
  const [forecastSide, setForecastSide] = useState<'BUY' | 'SELL'>('BUY');
  const [connectMode, setConnectMode] = useState<'PAPER' | 'ANGEL_ONE'>('PAPER');
  const [memoryQuery, setMemoryQuery] = useState('');
  const [memoryRegime, setMemoryRegime] = useState('');
  const [memorySetupFamily, setMemorySetupFamily] = useState('');
  const [memorySessionBucket, setMemorySessionBucket] = useState('');
  const [feedbackForm, setFeedbackForm] = useState({
    signal_id: '',
    status: 'FILLED',
    executed_price: '',
    filled_quantity: '',
    latency_ms: '',
    reason: '',
  });

  const loadOpsConfig = async () => {
    const res = await fetch('/api/ops/config');
    setOpsConfig(await res.json());
  };

  const loadBrokerStatus = async () => {
    const res = await fetch('/api/broker/status');
    setBrokerStatus(await res.json());
  };

  const loadRouting = async () => {
    const res = await fetch(`/api/routing/status?ticker=${encodeURIComponent(ticker)}`);
    setRoutingStatus(await res.json());
  };

  const loadForecast = async () => {
    const query = new URLSearchParams({ ticker, side: forecastSide, order_type: 'MARKET' });
    const res = await fetch(`/api/execution/forecast?${query.toString()}`);
    setForecast(await res.json());
  };

  const loadExecutionModels = async () => {
    const query = new URLSearchParams({ ticker });
    const res = await fetch(`/api/execution/models?${query.toString()}`);
    setExecutionModels(await res.json());
  };

  const loadMemoryStatus = async () => {
    const res = await fetch('/api/memory/status');
    setMemoryStatus(await res.json());
  };

  const loadMemoryContext = async () => {
    const query = new URLSearchParams({
      ticker,
      interval,
      query: memoryQuery,
      regime: memoryRegime,
      setup_family: memorySetupFamily,
      session_bucket: memorySessionBucket,
      limit: '6',
    });
    const res = await fetch(`/api/memory/context?${query.toString()}`);
    setMemoryContext(await res.json());
  };

  const loadLatestSignal = async () => {
    const res = await fetch('/api/ea/latest_signal');
    const data = await res.json();
    setLatestSignal(data);
    const signalId = data?.data?.signal_id || '';
    setFeedbackForm(prev => ({ ...prev, signal_id: signalId }));
  };

  const refreshAll = async () => {
    setIsBusy(true);
    try {
      await Promise.all([
        loadOpsConfig(),
        loadBrokerStatus(),
        loadRouting(),
        loadForecast(),
        loadExecutionModels(),
        loadMemoryStatus(),
        loadMemoryContext(),
        loadLatestSignal(),
      ]);
    } finally {
      setIsBusy(false);
    }
  };

  useEffect(() => {
    refreshAll();
  }, []);

  const saveOpsConfig = async (patch: Partial<NonNullable<OpsConfigResponse['config']>>) => {
    setIsBusy(true);
    try {
      const res = await fetch('/api/ops/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      });
      setOpsConfig(await res.json());
      setActionMessage('Ops control updated.');
      await loadRouting();
    } finally {
      setIsBusy(false);
    }
  };

  const connectBroker = async () => {
    setIsBusy(true);
    try {
      await fetch('/api/broker/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: connectMode }),
      });
      setActionMessage(`Broker switch requested: ${connectMode}.`);
      await Promise.all([loadBrokerStatus(), loadRouting(), loadForecast(), loadExecutionModels()]);
    } finally {
      setIsBusy(false);
    }
  };

  const applyRecommendedRoute = async () => {
    setIsBusy(true);
    try {
      const res = await fetch('/api/routing/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker }),
      });
      const data = await res.json();
      setActionMessage(data?.reason || 'Routing apply completed.');
      await Promise.all([loadBrokerStatus(), loadRouting(), loadForecast(), loadExecutionModels(), loadMemoryContext()]);
    } finally {
      setIsBusy(false);
    }
  };

  const exportSignal = async () => {
    setIsBusy(true);
    try {
      const res = await fetch('/api/ea/export_signal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker, interval, period, capital: Number(capital) }),
      });
      const data = await res.json();
      setExportResult(data);
      setActionMessage(data?.status === 'success' ? 'EA signal exported.' : (data?.message || 'Signal export failed.'));
      await Promise.all([loadLatestSignal(), loadMemoryContext()]);
    } finally {
      setIsBusy(false);
    }
  };

  const submitFeedback = async () => {
    setIsBusy(true);
    try {
      await fetch('/api/ea/execution_feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          signal_id: feedbackForm.signal_id || latestSignal?.data?.signal_id,
          status: feedbackForm.status,
          executed_price: feedbackForm.executed_price ? Number(feedbackForm.executed_price) : undefined,
          filled_quantity: feedbackForm.filled_quantity ? Number(feedbackForm.filled_quantity) : undefined,
          latency_ms: feedbackForm.latency_ms ? Number(feedbackForm.latency_ms) : undefined,
          reason: feedbackForm.reason || undefined,
          symbol: latestSignal?.data?.symbol || ticker,
          action: latestSignal?.data?.action || forecastSide,
        }),
      });
      setActionMessage('Execution feedback submitted.');
      await Promise.all([loadForecast(), loadRouting(), loadExecutionModels(), loadMemoryStatus(), loadMemoryContext()]);
    } finally {
      setIsBusy(false);
    }
  };

  const rebuildExecutionModels = async () => {
    setIsBusy(true);
    try {
      const res = await fetch('/api/execution/models/rebuild', { method: 'POST' });
      const data = await res.json();
      setActionMessage(`Execution models rebuilt: ${data?.model_count ?? 0} profiles.`);
      await Promise.all([loadExecutionModels(), loadForecast(), loadMemoryStatus()]);
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <div className="space-y-8 pb-10">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter uppercase">Live Ops</h1>
          <p className="text-muted-foreground font-mono text-xs uppercase tracking-widest">
            Safety lock, broker routing, execution forecast, EA export, and feedback controls.
          </p>
        </div>
        <Button onClick={refreshAll} disabled={isBusy} className="font-mono uppercase tracking-wider">
          Refresh Ops
        </Button>
      </div>

      {actionMessage && (
        <div className="rounded-lg border border-border/60 bg-secondary/30 px-4 py-3 text-xs font-mono uppercase tracking-wider text-muted-foreground">
          {actionMessage}
        </div>
      )}

      <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
        <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
          <CardTitle className="text-lg font-mono uppercase tracking-widest">Ops Controls</CardTitle>
          <CardDescription>
            Automatic broker switching is only permitted when the manual safety lock is armed.
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-6 grid grid-cols-1 gap-6 md:grid-cols-3">
          <div className="rounded-lg border border-border/60 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono uppercase tracking-wider">Safety Lock</span>
              <Switch
                checked={Boolean(opsConfig?.config?.manual_safety_lock)}
                onCheckedChange={(checked) => saveOpsConfig({ manual_safety_lock: checked })}
              />
            </div>
            <div className="text-xs text-muted-foreground">
              Must be enabled before any automatic broker switch can happen.
            </div>
          </div>

          <div className="rounded-lg border border-border/60 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono uppercase tracking-wider">Auto Switch</span>
              <Switch
                checked={Boolean(opsConfig?.config?.auto_broker_switch_enabled)}
                onCheckedChange={(checked) => saveOpsConfig({ auto_broker_switch_enabled: checked })}
              />
            </div>
            <div className="text-xs text-muted-foreground">
              Only applies when the routing layer recommends an alternate broker and safety lock is armed.
            </div>
          </div>

          <div className="rounded-lg border border-border/60 p-4 space-y-3">
            <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Preferred Live Broker</Label>
            <Select
              value={opsConfig?.config?.preferred_live_broker || 'ANGEL_ONE'}
              onValueChange={(value) => saveOpsConfig({ preferred_live_broker: value })}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="ANGEL_ONE">Angel One</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
        <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <CardTitle className="text-lg font-mono uppercase tracking-widest">Memory Context</CardTitle>
              <CardDescription>Scoped long-term context retrieved for the current ticker, regime, and setup.</CardDescription>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Input value={memoryQuery} onChange={(e) => setMemoryQuery(e.target.value)} placeholder="query" className="w-[160px]" />
              <Input value={memoryRegime} onChange={(e) => setMemoryRegime(e.target.value)} placeholder="regime" className="w-[140px]" />
              <Input value={memorySetupFamily} onChange={(e) => setMemorySetupFamily(e.target.value)} placeholder="setup" className="w-[140px]" />
              <Select value={memorySessionBucket || 'any'} onValueChange={(value) => setMemorySessionBucket(value === 'any' ? '' : value)}>
                <SelectTrigger className="w-[130px]"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="any">Any Session</SelectItem>
                  <SelectItem value="open">Open</SelectItem>
                  <SelectItem value="midday">Midday</SelectItem>
                  <SelectItem value="close">Close</SelectItem>
                  <SelectItem value="offhours">Offhours</SelectItem>
                </SelectContent>
              </Select>
              <Button onClick={loadMemoryContext} disabled={isBusy} className="font-mono uppercase tracking-wider">Load Memory</Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-6 space-y-4">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
            <div className="rounded-lg border border-border/60 p-4">
              <div className="text-[10px] font-mono uppercase text-muted-foreground">Active</div>
              <div className="font-mono text-sm">{memoryStatus?.active_memories ?? 0}</div>
            </div>
            <div className="rounded-lg border border-border/60 p-4">
              <div className="text-[10px] font-mono uppercase text-muted-foreground">Expired</div>
              <div className="font-mono text-sm">{memoryStatus?.expired_memories ?? 0}</div>
            </div>
            <div className="rounded-lg border border-border/60 p-4">
              <div className="text-[10px] font-mono uppercase text-muted-foreground">Remote Sync</div>
              <div className="font-mono text-sm uppercase">{memoryStatus?.remote_enabled ? 'ON' : 'OFF'}</div>
            </div>
            <div className="rounded-lg border border-border/60 p-4">
              <div className="text-[10px] font-mono uppercase text-muted-foreground">Retrieved</div>
              <div className="font-mono text-sm">{memoryContext?.influence?.memory_count ?? 0}</div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-5">
            <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Align Bias</div><div className="font-mono text-xs">{(memoryContext?.influence?.alignment_bias ?? 0).toFixed(2)}</div></div>
            <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Risk Bias</div><div className="font-mono text-xs">{(memoryContext?.influence?.risk_bias ?? 0).toFixed(2)}</div></div>
            <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Avg Conf</div><div className="font-mono text-xs">{((memoryContext?.influence?.average_confidence ?? 0) * 100).toFixed(0)}%</div></div>
            <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Avg Fresh</div><div className="font-mono text-xs">{((memoryContext?.influence?.average_freshness ?? 0) * 100).toFixed(0)}%</div></div>
            <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Types</div><div className="font-mono text-xs uppercase">{Object.entries(memoryStatus?.memory_type_counts || {}).map(([key, value]) => `${key}:${value}`).join(' | ') || 'n/a'}</div></div>
          </div>

          <div className="space-y-2">
            {(memoryContext?.influence?.notes || []).map((note) => (
              <div key={note} className="text-xs font-mono text-muted-foreground">{note}</div>
            ))}
          </div>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="font-mono text-[10px] uppercase">Type</TableHead>
                <TableHead className="font-mono text-[10px] uppercase">Source</TableHead>
                <TableHead className="font-mono text-[10px] uppercase">Score</TableHead>
                <TableHead className="font-mono text-[10px] uppercase">Conf</TableHead>
                <TableHead className="font-mono text-[10px] uppercase">Fresh</TableHead>
                <TableHead className="font-mono text-[10px] uppercase">Content</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {!(memoryContext?.retrieved || []).length ? (
                <TableRow><TableCell colSpan={6} className="h-20 text-center text-xs font-mono text-muted-foreground uppercase">No scoped memories loaded</TableCell></TableRow>
              ) : (
                memoryContext!.retrieved!.map((row) => (
                  <TableRow key={row.memory_id || `${row.source}-${row.content}`}>
                    <TableCell className="font-mono text-xs uppercase">{row.metadata?.memory_type || 'n/a'}</TableCell>
                    <TableCell className="font-mono text-xs">{row.source}</TableCell>
                    <TableCell className="font-mono text-xs">{row.similarity.toFixed(2)}</TableCell>
                    <TableCell className="font-mono text-xs">{(((row.metadata?.confidence ?? 0) * 100)).toFixed(0)}%</TableCell>
                    <TableCell className="font-mono text-xs">{(((row.metadata?.freshness_score ?? 0) * 100)).toFixed(0)}%</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{row.content}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
          <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
            <CardTitle className="text-lg font-mono uppercase tracking-widest">Broker Control</CardTitle>
          </CardHeader>
          <CardContent className="pt-6 space-y-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div className="rounded-lg border border-border/60 p-4">
                <div className="text-[10px] font-mono uppercase text-muted-foreground">Current Broker</div>
                <div className="font-mono text-sm uppercase">{brokerStatus?.broker || 'n/a'}</div>
              </div>
              <div className="rounded-lg border border-border/60 p-4">
                <div className="text-[10px] font-mono uppercase text-muted-foreground">Mode</div>
                <div className="font-mono text-sm uppercase">{brokerStatus?.mode || 'n/a'}</div>
              </div>
              <div className="rounded-lg border border-border/60 p-4">
                <div className="text-[10px] font-mono uppercase text-muted-foreground">Status</div>
                <div className="font-mono text-sm uppercase">{brokerStatus?.status || 'n/a'}</div>
              </div>
            </div>

            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-2 min-w-[180px]">
                <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Target Broker</Label>
                <Select value={connectMode} onValueChange={(value: 'PAPER' | 'ANGEL_ONE') => setConnectMode(value)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="PAPER">Paper</SelectItem>
                    <SelectItem value="ANGEL_ONE">Angel One</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button onClick={connectBroker} disabled={isBusy} className="font-mono uppercase tracking-wider">Switch Broker</Button>
              <Button onClick={applyRecommendedRoute} disabled={isBusy} variant="secondary" className="font-mono uppercase tracking-wider">
                Apply Recommended Route
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
          <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
            <CardTitle className="text-lg font-mono uppercase tracking-widest">Route Context</CardTitle>
          </CardHeader>
          <CardContent className="pt-6 space-y-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="rounded-lg border border-border/60 p-4">
                <div className="text-[10px] font-mono uppercase text-muted-foreground">Recommended Execution</div>
                <div className="font-mono text-sm uppercase">{routingStatus?.recommended_execution_broker?.broker || 'n/a'}</div>
                <div className="font-mono text-xs text-muted-foreground">
                  {routingStatus?.recommended_execution_broker?.recommendation || 'unknown'} | score {(routingStatus?.recommended_execution_broker?.score || 0).toFixed(2)}
                </div>
              </div>
              <div className="rounded-lg border border-border/60 p-4">
                <div className="text-[10px] font-mono uppercase text-muted-foreground">Recommended Data</div>
                <div className="font-mono text-sm uppercase">{routingStatus?.recommended_market_data_provider?.provider || 'n/a'}</div>
                <div className="font-mono text-xs text-muted-foreground">
                  {routingStatus?.recommended_market_data_provider?.recommendation || 'unknown'} | score {(routingStatus?.recommended_market_data_provider?.route_score || 0).toFixed(2)}
                </div>
              </div>
            </div>

            <div className="space-y-2">
              {(routingStatus?.notes || []).map((note) => (
                <div key={note} className="text-xs font-mono text-muted-foreground">{note}</div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
        <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <CardTitle className="text-lg font-mono uppercase tracking-widest">Execution Forecast</CardTitle>
              <CardDescription>Pre-trade execution friction estimate for the current symbol and route.</CardDescription>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Input value={ticker} onChange={(e) => setTicker(e.target.value)} className="w-[140px]" />
              <Select value={forecastSide} onValueChange={(value: 'BUY' | 'SELL') => setForecastSide(value)}>
                <SelectTrigger className="w-[120px]"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="BUY">BUY</SelectItem>
                  <SelectItem value="SELL">SELL</SelectItem>
                </SelectContent>
              </Select>
              <Button onClick={loadForecast} disabled={isBusy} className="font-mono uppercase tracking-wider">Refresh Forecast</Button>
              <Button onClick={rebuildExecutionModels} disabled={isBusy} variant="secondary" className="font-mono uppercase tracking-wider">Rebuild Models</Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-6">
          {!forecast?.forecast ? (
            <div className="text-xs font-mono uppercase tracking-wider text-muted-foreground">No forecast loaded</div>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-8">
              <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Basis</div><div className="font-mono text-xs uppercase">{forecast.forecast.basis}</div></div>
              <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Model</div><div className="font-mono text-xs uppercase">{forecast.forecast.model_basis || 'none'}</div></div>
              <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Samples</div><div className="font-mono text-xs">{forecast.forecast.sample_count}</div></div>
              <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Confidence</div><div className="font-mono text-xs">{((forecast.forecast.model_confidence || 0) * 100).toFixed(0)}%</div></div>
              <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Slip</div><div className="font-mono text-xs">{forecast.forecast.expected_slippage_bps.toFixed(2)} bps</div></div>
              <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Reject</div><div className="font-mono text-xs">{forecast.forecast.expected_reject_rate.toFixed(1)}%</div></div>
              <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Fill %</div><div className="font-mono text-xs">{(forecast.forecast.expected_fill_ratio * 100).toFixed(1)}%</div></div>
              <div><div className="text-[10px] font-mono uppercase text-muted-foreground">TTF</div><div className="font-mono text-xs">{Math.round(forecast.forecast.expected_time_to_fill_ms)} ms</div></div>
              <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Risk Mult</div><div className="font-mono text-xs">{forecast.forecast.risk_multiplier.toFixed(2)}</div></div>
              <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Action</div><div className={cn("font-mono text-xs uppercase", forecast.forecast.recommendation === 'avoid' ? 'text-destructive' : forecast.forecast.recommendation === 'reduce_size' ? 'text-amber-400' : 'text-primary')}>{forecast.forecast.recommendation}</div></div>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
          <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
            <CardTitle className="text-lg font-mono uppercase tracking-widest">EA Export</CardTitle>
          </CardHeader>
          <CardContent className="pt-6 space-y-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
              <div className="space-y-2">
                <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Ticker</Label>
                <Input value={ticker} onChange={(e) => setTicker(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Interval</Label>
                <Select value={interval} onValueChange={setInterval}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="5m">5m</SelectItem>
                    <SelectItem value="15m">15m</SelectItem>
                    <SelectItem value="30m">30m</SelectItem>
                    <SelectItem value="1h">1h</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Period</Label>
                <Select value={period} onValueChange={setPeriod}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="60d">60d</SelectItem>
                    <SelectItem value="6mo">6mo</SelectItem>
                    <SelectItem value="1y">1y</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Capital</Label>
                <Input value={capital} onChange={(e) => setCapital(e.target.value)} />
              </div>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button onClick={exportSignal} disabled={isBusy} className="font-mono uppercase tracking-wider">Export Signal</Button>
              <Button onClick={loadLatestSignal} disabled={isBusy} variant="secondary" className="font-mono uppercase tracking-wider">Load Latest Signal</Button>
            </div>
            {(exportResult?.signal || latestSignal?.data) && (
              <div className="rounded-lg border border-border/60 p-4 space-y-2">
                <div className="text-[10px] font-mono uppercase text-muted-foreground">Latest Signal</div>
                <div className="font-mono text-xs uppercase">
                  {(exportResult?.signal?.symbol || latestSignal?.data?.symbol || 'n/a')} | {(exportResult?.signal?.action || latestSignal?.data?.action || 'n/a')}
                </div>
                <div className="font-mono text-xs text-muted-foreground">
                  ID: {exportResult?.signal?.signal_id || latestSignal?.data?.signal_id || 'n/a'}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
          <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
            <CardTitle className="text-lg font-mono uppercase tracking-widest">Execution Feedback</CardTitle>
          </CardHeader>
          <CardContent className="pt-6 space-y-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Signal ID</Label>
                <Input value={feedbackForm.signal_id} onChange={(e) => setFeedbackForm(prev => ({ ...prev, signal_id: e.target.value }))} />
              </div>
              <div className="space-y-2">
                <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Status</Label>
                <Select value={feedbackForm.status} onValueChange={(value) => setFeedbackForm(prev => ({ ...prev, status: value }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="FILLED">FILLED</SelectItem>
                    <SelectItem value="PARTIAL">PARTIAL</SelectItem>
                    <SelectItem value="REJECTED">REJECTED</SelectItem>
                    <SelectItem value="CANCELLED">CANCELLED</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Executed Price</Label>
                <Input value={feedbackForm.executed_price} onChange={(e) => setFeedbackForm(prev => ({ ...prev, executed_price: e.target.value }))} />
              </div>
              <div className="space-y-2">
                <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Filled Quantity</Label>
                <Input value={feedbackForm.filled_quantity} onChange={(e) => setFeedbackForm(prev => ({ ...prev, filled_quantity: e.target.value }))} />
              </div>
              <div className="space-y-2">
                <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Latency ms</Label>
                <Input value={feedbackForm.latency_ms} onChange={(e) => setFeedbackForm(prev => ({ ...prev, latency_ms: e.target.value }))} />
              </div>
              <div className="space-y-2">
                <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Reason</Label>
                <Input value={feedbackForm.reason} onChange={(e) => setFeedbackForm(prev => ({ ...prev, reason: e.target.value }))} />
              </div>
            </div>
            <Button onClick={submitFeedback} disabled={isBusy} className="font-mono uppercase tracking-wider">Submit Feedback</Button>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
          <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
            <CardTitle className="text-sm font-mono uppercase tracking-wider">Execution Models</CardTitle>
            <CardDescription>
              Broker and session-specific profiles derived from real fill history.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="font-mono text-[10px] uppercase">Type</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Broker</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Samples</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Conf</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Fill %</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Slip</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {!(executionModels?.models || []).length ? (
                  <TableRow><TableCell colSpan={6} className="h-20 text-center text-xs font-mono text-muted-foreground uppercase">No execution models</TableCell></TableRow>
                ) : (
                  executionModels!.models!.slice(0, 8).map((row) => (
                    <TableRow key={row.model_key}>
                      <TableCell className="font-mono text-xs uppercase">{row.dimensions.model_type}</TableCell>
                      <TableCell className="font-mono text-xs">{row.dimensions.broker || '-'}</TableCell>
                      <TableCell className="font-mono text-xs">{row.sample_count}</TableCell>
                      <TableCell className="font-mono text-xs">{(row.confidence * 100).toFixed(0)}%</TableCell>
                      <TableCell className="font-mono text-xs">{(row.avg_fill_ratio * 100).toFixed(1)}%</TableCell>
                      <TableCell className="font-mono text-xs">{row.avg_slippage_bps.toFixed(2)} bps</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
          <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
            <CardTitle className="text-sm font-mono uppercase tracking-wider">Execution Brokers</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="font-mono text-[10px] uppercase">Broker</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Score</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Fill %</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Reco</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {!(routingStatus?.execution_brokers || []).length ? (
                  <TableRow><TableCell colSpan={4} className="h-20 text-center text-xs font-mono text-muted-foreground uppercase">No broker routes</TableCell></TableRow>
                ) : (
                  routingStatus!.execution_brokers!.map((row) => (
                    <TableRow key={row.broker}>
                      <TableCell className="font-mono text-xs">{row.current ? `${row.broker} *` : row.broker}</TableCell>
                      <TableCell className="font-mono text-xs">{row.score.toFixed(2)}</TableCell>
                      <TableCell className="font-mono text-xs">{(row.avg_fill_ratio * 100).toFixed(1)}%</TableCell>
                      <TableCell className="font-mono text-xs uppercase">{row.recommendation}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
          <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
            <CardTitle className="text-sm font-mono uppercase tracking-wider">Market Data Providers</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="font-mono text-[10px] uppercase">Provider</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Score</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">State</TableHead>
                  <TableHead className="font-mono text-[10px] uppercase">Reco</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {!(routingStatus?.market_data_providers || []).length ? (
                  <TableRow><TableCell colSpan={4} className="h-20 text-center text-xs font-mono text-muted-foreground uppercase">No provider routes</TableCell></TableRow>
                ) : (
                  routingStatus!.market_data_providers!.map((row) => (
                    <TableRow key={row.provider}>
                      <TableCell className="font-mono text-xs">{row.provider}</TableCell>
                      <TableCell className="font-mono text-xs">{row.route_score.toFixed(2)}</TableCell>
                      <TableCell className="font-mono text-xs uppercase">{row.cooled_down ? 'COOLDOWN' : row.connected === false ? 'DEGRADED' : 'READY'}</TableCell>
                      <TableCell className="font-mono text-xs uppercase">{row.recommendation}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
