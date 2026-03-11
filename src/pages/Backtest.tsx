import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Play, RotateCcw, TrendingUp, TrendingDown, Minus, ShieldOff, AlertCircle, BrainCircuit, DatabaseZap, Target } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatCurrency } from '@/lib/market-config';

interface TradeResult {
  entry_time: string;
  exit_time: string;
  entry_price: number;
  exit_price: number;
  reason: string;
  pnl: number;
  trade_cost?: number;
}

interface BacktestSummary {
  mode?: 'walkforward' | 'legacy';
  status?: string;
  period: string;
  interval: string;
  total_trades: number;
  win_rate: number;
  total_pnl: number;
  profit_factor: number;
  avg_win: number;
  avg_loss: number;
  final_balance: number;
  trades: TradeResult[];
  error?: string;
  is_simulation?: boolean;
  ticker?: string;
  training_logs?: string[];
  data_source?: string;
  total_trade_cost?: number;
  sharpe_ratio?: number;
  max_drawdown?: number;
  total_return_pct?: number;
  ending_equity?: number;
  folds?: Array<{
    test_start: string;
    test_end: string;
    hit_rate: number;
    pnl_sum: number;
    samples: number;
  }>;
}

interface ApprovedPattern {
  pattern_id: string;
  samples: number;
  wins: number;
  losses: number;
  win_rate: number;
  approved: boolean;
}

interface PatternTrainingSummary {
  status: string;
  message?: string;
  ticker?: string;
  interval?: string;
  rows?: number;
  trained_at?: string;
  thresholds?: {
    min_samples: number;
    min_win_rate: number;
    horizon_bars: number;
    stop_atr: number;
    target_atr: number;
  };
  approved_patterns?: ApprovedPattern[];
  approved_pattern_ids?: string[];
}

interface NewsEventStudySummary {
  status: string;
  message?: string;
  benchmark_ticker?: string;
  interval?: string;
  horizon_bars?: number;
  samples?: number;
  trained_at?: string;
  metrics?: {
    direction_hit_rate: number;
    impact_correlation: number;
    base_multiplier: number;
  };
  buckets?: Array<{
    bucket: string;
    samples: number;
    direction_hit_rate: number;
    median_impact_multiplier: number;
    avg_realized_move_pct: number;
  }>;
}

interface LiveSignalPerformanceSummary {
  status: string;
  summary?: {
    total_signals: number;
    open_signals: number;
    settled_signals: number;
    win_rate: number;
    avg_realized_return_pct: number;
  };
  by_source?: Array<{
    source: string;
    signals: number;
    win_rate: number;
    avg_return_pct: number;
  }>;
  component_reliability?: Array<{
    component: string;
    samples: number;
    hit_rate: number;
    avg_abs_weight: number;
    avg_component_value: number;
  }>;
  signals?: Array<{
    signal_id: string;
    created_at: string;
    ticker: string;
    source: string;
    action: string;
    confidence: number;
    status: string;
    outcome?: string | null;
    realized_return_pct?: number;
  }>;
}

interface ExecutionQualitySummary {
  status: string;
  summary?: {
    total_orders: number;
    filled_orders: number;
    pending_orders: number;
    rejected_orders: number;
    fill_rate: number;
    reject_rate: number;
    avg_slippage_bps: number;
    avg_latency_ms: number;
    avg_fill_ratio: number;
    avg_time_to_fill_ms: number;
    quality_score: number;
  };
  by_broker?: Array<{
    broker: string;
    orders: number;
    fill_rate: number;
    reject_rate: number;
    avg_slippage_bps: number;
    avg_fill_ratio: number;
    avg_time_to_fill_ms: number;
    quality_score: number;
  }>;
  recent?: Array<{
    execution_id: string;
    created_at: string;
    symbol: string;
    side: string;
    status: string;
    broker: string;
    slippage_bps?: number | null;
    fill_ratio?: number | null;
    time_to_fill_ms?: number | null;
    quality_score: number;
    reason?: string | null;
  }>;
}

interface ExecutionForecastSummary {
  status: string;
  forecast?: {
    sample_count: number;
    basis: string;
    session_bucket: string | null;
    quality_score: number;
    expected_slippage_bps: number;
    expected_reject_rate: number;
    expected_pending_rate: number;
    expected_fill_ratio: number;
    expected_time_to_fill_ms: number;
    expected_latency_ms: number;
    risk_multiplier: number;
    recommendation: string;
  };
}

interface RoutingStatusSummary {
  status: string;
  notes?: string[];
  recommended_execution_broker?: {
    broker: string;
    recommendation: string;
    score: number;
  };
  recommended_market_data_provider?: {
    provider: string;
    recommendation: string;
    route_score: number;
  };
  execution_brokers?: Array<{
    broker: string;
    mode: string;
    current: boolean;
    live: boolean;
    available: boolean;
    score: number;
    reject_rate: number;
    avg_slippage_bps: number;
    recommendation: string;
  }>;
  market_data_providers?: Array<{
    provider: string;
    priority: number;
    route_score: number;
    cooled_down?: boolean;
    connected?: boolean;
    recommendation: string;
  }>;
}

export function Backtest() {
  const [summary, setSummary] = useState<BacktestSummary | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [engineMode, setEngineMode] = useState<'walkforward' | 'legacy'>('walkforward');
  const [patternTraining, setPatternTraining] = useState<PatternTrainingSummary | null>(null);
  const [isPatternBusy, setIsPatternBusy] = useState(false);
  const [eventStudy, setEventStudy] = useState<NewsEventStudySummary | null>(null);
  const [isEventStudyBusy, setIsEventStudyBusy] = useState(false);
  const [signalPerformance, setSignalPerformance] = useState<LiveSignalPerformanceSummary | null>(null);
  const [isSignalBusy, setIsSignalBusy] = useState(false);
  const [executionQuality, setExecutionQuality] = useState<ExecutionQualitySummary | null>(null);
  const [isExecutionBusy, setIsExecutionBusy] = useState(false);
  const [executionForecast, setExecutionForecast] = useState<ExecutionForecastSummary | null>(null);
  const [forecastSide, setForecastSide] = useState<'BUY' | 'SELL'>('BUY');
  const [routingStatus, setRoutingStatus] = useState<RoutingStatusSummary | null>(null);
  const [backtestForm, setBacktestForm] = useState({
    ticker: '^NSEI',
    interval: '15m',
    period: '1y',
    horizon: '5',
    train_window: '320',
    test_window: '80',
    step_size: '40',
    slippage_bps: '3',
    transaction_cost_bps: '2',
    allow_synthetic: false,
  });
  const [patternForm, setPatternForm] = useState({
    ticker: '^NSEI',
    interval: '15m',
    period: '1y',
    min_samples: '12',
    min_win_rate_percent: '80',
    horizon_bars: '12',
    stop_atr: '1.0',
    target_atr: '1.5',
  });

  const updatePatternField = (key: keyof typeof patternForm, value: string) => {
    setPatternForm(prev => ({ ...prev, [key]: value }));
  };

  const updateBacktestField = (key: keyof typeof backtestForm, value: string | boolean) => {
    setBacktestForm(prev => ({ ...prev, [key]: value }));
  };

  const runPatternTraining = async () => {
    setIsPatternBusy(true);
    try {
      const payload = {
        ticker: patternForm.ticker,
        interval: patternForm.interval,
        period: patternForm.period,
        min_samples: Number(patternForm.min_samples),
        min_win_rate: Number(patternForm.min_win_rate_percent) / 100,
        horizon_bars: Number(patternForm.horizon_bars),
        stop_atr: Number(patternForm.stop_atr),
        target_atr: Number(patternForm.target_atr),
      };

      const res = await fetch('/api/patterns/train', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      setPatternTraining(data);
    } catch (error) {
      console.error('Pattern training failed:', error);
      setPatternTraining({
        status: 'error',
        message: 'Pattern training request failed.',
        approved_patterns: [],
      });
    } finally {
      setIsPatternBusy(false);
    }
  };

  const loadApprovedPatterns = async () => {
    setIsPatternBusy(true);
    try {
      const query = new URLSearchParams({
        ticker: patternForm.ticker,
        interval: patternForm.interval,
      });
      const res = await fetch(`/api/patterns/approved?${query.toString()}`);
      const data = await res.json();
      setPatternTraining(data);
    } catch (error) {
      console.error('Pattern load failed:', error);
      setPatternTraining({
        status: 'error',
        message: 'Approved pattern lookup failed.',
        approved_patterns: [],
      });
    } finally {
      setIsPatternBusy(false);
    }
  };

  const trainEventStudy = async () => {
    setIsEventStudyBusy(true);
    try {
      const res = await fetch('/api/news/event_study/train', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          benchmark_ticker: backtestForm.ticker,
          interval: backtestForm.interval,
          period: backtestForm.period,
          horizon_bars: Number(backtestForm.horizon),
          min_samples: 10,
          auto_backfill: true,
        }),
      });
      const data = await res.json();
      setEventStudy(data);
    } catch (error) {
      console.error('Event study training failed:', error);
      setEventStudy({ status: 'error', message: 'News event-study training failed.' });
    } finally {
      setIsEventStudyBusy(false);
    }
  };

  const loadEventStudy = async () => {
    setIsEventStudyBusy(true);
    try {
      const query = new URLSearchParams({
        benchmark_ticker: backtestForm.ticker,
        interval: backtestForm.interval,
      });
      const res = await fetch(`/api/news/event_study/latest?${query.toString()}`);
      const data = await res.json();
      setEventStudy(data);
    } catch (error) {
      console.error('Event study load failed:', error);
      setEventStudy({ status: 'error', message: 'News event-study lookup failed.' });
    } finally {
      setIsEventStudyBusy(false);
    }
  };

  const loadSignalPerformance = async () => {
    setIsSignalBusy(true);
    try {
      const query = new URLSearchParams({ ticker: backtestForm.ticker });
      const res = await fetch(`/api/signals/performance?${query.toString()}`);
      const data = await res.json();
      setSignalPerformance(data);
    } catch (error) {
      console.error('Signal performance load failed:', error);
      setSignalPerformance({ status: 'error' });
    } finally {
      setIsSignalBusy(false);
    }
  };

  const settleSignals = async () => {
    setIsSignalBusy(true);
    try {
      await fetch('/api/signals/settle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: backtestForm.ticker }),
      });
      await loadSignalPerformance();
    } catch (error) {
      console.error('Signal settle failed:', error);
    } finally {
      setIsSignalBusy(false);
    }
  };

  const loadExecutionQuality = async () => {
    setIsExecutionBusy(true);
    try {
      const query = new URLSearchParams({ ticker: backtestForm.ticker });
      const res = await fetch(`/api/execution/quality?${query.toString()}`);
      const data = await res.json();
      setExecutionQuality(data);
    } catch (error) {
      console.error('Execution quality load failed:', error);
      setExecutionQuality({ status: 'error' });
    } finally {
      setIsExecutionBusy(false);
    }
  };

  const loadExecutionForecast = async () => {
    setIsExecutionBusy(true);
    try {
      const query = new URLSearchParams({
        ticker: backtestForm.ticker,
        side: forecastSide,
        order_type: 'MARKET',
      });
      const res = await fetch(`/api/execution/forecast?${query.toString()}`);
      const data = await res.json();
      setExecutionForecast(data);
    } catch (error) {
      console.error('Execution forecast load failed:', error);
      setExecutionForecast({ status: 'error' });
    } finally {
      setIsExecutionBusy(false);
    }
  };

  const loadRoutingStatus = async () => {
    setIsExecutionBusy(true);
    try {
      const query = new URLSearchParams({ ticker: backtestForm.ticker });
      const res = await fetch(`/api/routing/status?${query.toString()}`);
      const data = await res.json();
      setRoutingStatus(data);
    } catch (error) {
      console.error('Routing status load failed:', error);
      setRoutingStatus({ status: 'error' });
    } finally {
      setIsExecutionBusy(false);
    }
  };

  const normalizeBacktestPayload = (payload: any, mode: 'walkforward' | 'legacy'): BacktestSummary => {
    if (mode === 'walkforward') {
      const wf = payload || {};
      const cfg = wf.config || {};
      const sum = wf.summary || {};
      if (wf.status === 'error') {
        return {
          mode: 'walkforward',
          status: 'error',
          period: backtestForm.period,
          interval: backtestForm.interval,
          total_trades: 0,
          win_rate: 0,
          total_pnl: 0,
          profit_factor: 0,
          avg_win: 0,
          avg_loss: 0,
          final_balance: 0,
          trades: [],
          error: wf.message || 'Walk-forward validation failed.',
          ticker: backtestForm.ticker,
        };
      }
      return {
        mode: 'walkforward',
        status: wf.status,
        period: cfg.period || backtestForm.period,
        interval: cfg.interval || backtestForm.interval,
        total_trades: Number(sum.total_trades || 0),
        win_rate: Number(((sum.win_rate || 0) * 100).toFixed(2)),
        total_pnl: 0,
        profit_factor: 0,
        avg_win: 0,
        avg_loss: 0,
        final_balance: Number(sum.ending_equity || 1),
        trades: [],
        ticker: cfg.ticker || backtestForm.ticker,
        total_return_pct: Number(((sum.total_return || 0) * 100).toFixed(2)),
        ending_equity: Number(sum.ending_equity || 1),
        sharpe_ratio: Number(sum.sharpe || 0),
        max_drawdown: Number(((sum.max_drawdown || 0) * 100).toFixed(2)),
        folds: wf.folds || [],
      };
    }

    const bt = payload?.backtest || payload || {};
    if (payload?.status === 'error' && !payload?.backtest) {
      return {
        mode: 'legacy',
        status: 'error',
        period: backtestForm.period,
        interval: backtestForm.interval,
        total_trades: 0,
        win_rate: 0,
        total_pnl: 0,
        profit_factor: 0,
        avg_win: 0,
        avg_loss: 0,
        final_balance: 0,
        trades: [],
        error: payload?.message || 'Legacy backtest failed.',
        ticker: backtestForm.ticker,
      };
    }
    return {
      mode: 'legacy',
      status: payload?.status || bt?.status,
      period: bt.period || backtestForm.period,
      interval: bt.interval || backtestForm.interval,
      total_trades: Number(bt.total_trades || 0),
      win_rate: Number(bt.win_rate || 0),
      total_pnl: Number(bt.total_pnl || 0),
      profit_factor: Number(bt.profit_factor || 0),
      avg_win: Number(bt.avg_win || 0),
      avg_loss: Number(bt.avg_loss || 0),
      final_balance: Number(bt.final_balance || 0),
      trades: bt.trades || [],
      error: payload?.message || bt?.error,
      is_simulation: Boolean(bt.is_simulation),
      ticker: backtestForm.ticker,
      data_source: bt.data_source,
      total_trade_cost: bt.total_trade_cost,
      sharpe_ratio: bt.sharpe_ratio,
      max_drawdown: bt.max_drawdown,
    };
  };

  const runBacktest = async () => {
    setIsRunning(true);
    setSummary(null);
    setProgress(0);

    // Simulate progress bar while fetching
    const progressInterval = setInterval(() => {
      setProgress(prev => {
        if (prev >= 90) return prev;
        return prev + 10;
      });
    }, 500);

    try {
      const isWalkforward = engineMode === 'walkforward';
      const endpoint = isWalkforward ? '/api/backtest/walkforward' : `/api/backtest?ticker=${encodeURIComponent(backtestForm.ticker)}&interval=${encodeURIComponent(backtestForm.interval)}&period=${encodeURIComponent(backtestForm.period)}&slippage_bps=${encodeURIComponent(backtestForm.slippage_bps)}&transaction_cost_bps=${encodeURIComponent(backtestForm.transaction_cost_bps)}&allow_synthetic=${backtestForm.allow_synthetic ? 'true' : 'false'}`;
      const res = await fetch(endpoint, isWalkforward ? {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticker: backtestForm.ticker,
          interval: backtestForm.interval,
          period: backtestForm.period,
          horizon: Number(backtestForm.horizon),
          train_window: Number(backtestForm.train_window),
          test_window: Number(backtestForm.test_window),
          step_size: Number(backtestForm.step_size),
          slippage_bps: Number(backtestForm.slippage_bps),
          transaction_cost_bps: Number(backtestForm.transaction_cost_bps),
        }),
      } : {
        method: 'POST'
      });
      const data = await res.json();

      clearInterval(progressInterval);
      setProgress(100);
      setSummary(normalizeBacktestPayload(data, engineMode));
    } catch (error) {
      console.error("Backtest failed:", error);
      clearInterval(progressInterval);
      setProgress(0);
    } finally {
      setIsRunning(false);
    }
  };

  const getBadTradesAvoided = () => {
    return 0; // The current backend logic doesn't explicitly track "filtered" trades yet, only executed ones
  };

  return (
    <div className="space-y-8 pb-10">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h1 className="text-4xl font-bold tracking-tighter uppercase">Backtest Engine</h1>
            {summary?.is_simulation && (
              <Badge variant="outline" className="text-amber-500 border-amber-500/50 animate-pulse font-mono uppercase text-[10px] tracking-wider">
                Simulation Mode
              </Badge>
            )}
          </div>
          <p className="text-muted-foreground font-mono text-xs uppercase tracking-widest">
            {engineMode === 'walkforward'
              ? `WALK-FORWARD VALIDATION ON ${backtestForm.ticker} (${backtestForm.period})`
              : `LEGACY SIMULATION ON ${summary?.is_simulation ? "SYNTHETIC MARKET DATA" : backtestForm.ticker}`}
          </p>
        </div>
        <div className="flex gap-4">
          <Button
            onClick={runBacktest}
            disabled={isRunning}
            className="font-mono uppercase tracking-tighter h-12 px-8"
          >
            {isRunning ? 'Processing...' : summary ? 'Re-run Validation' : 'Run Backtest'}
            <Play className="ml-2 w-4 h-4 fill-current" />
          </Button>
          {summary && (
            <Button
              variant="outline"
              onClick={() => { setSummary(null); setProgress(0); }}
              className="h-12 w-12 p-0"
            >
              <RotateCcw className="w-4 h-4" />
            </Button>
          )}
          <Button
            variant="secondary"
            onClick={async () => {
              setIsRunning(true);
              try {
                const res = await fetch('/api/train', { method: 'POST' });
                const response = await res.json();

                if (response.status === 'success') {
                  const { best_params, logs } = response.data;

                  // Update summary to include logs. If summary is null, create a temp one.
                  setSummary(prev => {
                    if (prev) {
                      return { ...prev, training_logs: logs };
                    }
                    return {
                      period: "Training Completed",
                      interval: "15m",
                      total_trades: 0,
                      win_rate: 0,
                      total_pnl: best_params.pnl || 0,
                      profit_factor: 0,
                      avg_win: 0,
                      avg_loss: 0,
                      final_balance: 0,
                      trades: [],
                      ticker: "^NSEI",
                      training_logs: logs
                    };
                  });
                  // Optional: Scroll to bottom
                } else {
                  alert("Training Error: " + response.message);
                }
              } catch (e) {
                alert("Training Failed");
              } finally {
                setIsRunning(false);
              }
            }}
            disabled={isRunning}
            className="font-mono uppercase tracking-tighter h-12 px-8 border border-primary/20"
          >
            Train / Optimize (AI v2)
          </Button>
        </div>
      </div>

      <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
        <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
          <CardTitle className="text-lg font-mono uppercase tracking-widest">Validation Profile</CardTitle>
          <CardDescription>
            Walk-forward is the default because it is the more honest validation path. Legacy mode is available only for quick heuristic checks.
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-6 space-y-5">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Engine</Label>
              <Select value={engineMode} onValueChange={(value: 'walkforward' | 'legacy') => setEngineMode(value)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="walkforward">Walk-Forward</SelectItem>
                  <SelectItem value="legacy">Legacy Sim</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Ticker</Label>
              <Input value={backtestForm.ticker} onChange={(e) => updateBacktestField('ticker', e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Interval</Label>
              <Select value={backtestForm.interval} onValueChange={(value) => updateBacktestField('interval', value)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="5m">5m</SelectItem>
                  <SelectItem value="15m">15m</SelectItem>
                  <SelectItem value="30m">30m</SelectItem>
                  <SelectItem value="1h">1h</SelectItem>
                  <SelectItem value="1d">1d</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Period</Label>
              <Select value={backtestForm.period} onValueChange={(value) => updateBacktestField('period', value)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="60d">60d</SelectItem>
                  <SelectItem value="6mo">6mo</SelectItem>
                  <SelectItem value="1y">1y</SelectItem>
                  <SelectItem value="2y">2y</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Horizon Bars</Label>
              <Input value={backtestForm.horizon} onChange={(e) => updateBacktestField('horizon', e.target.value)} />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Train Window</Label>
              <Input value={backtestForm.train_window} onChange={(e) => updateBacktestField('train_window', e.target.value)} disabled={engineMode === 'legacy'} />
            </div>
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Test Window</Label>
              <Input value={backtestForm.test_window} onChange={(e) => updateBacktestField('test_window', e.target.value)} disabled={engineMode === 'legacy'} />
            </div>
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Step Size</Label>
              <Input value={backtestForm.step_size} onChange={(e) => updateBacktestField('step_size', e.target.value)} disabled={engineMode === 'legacy'} />
            </div>
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Slippage / Costs (bps)</Label>
              <div className="grid grid-cols-2 gap-3">
                <Input value={backtestForm.slippage_bps} onChange={(e) => updateBacktestField('slippage_bps', e.target.value)} />
                <Input value={backtestForm.transaction_cost_bps} onChange={(e) => updateBacktestField('transaction_cost_bps', e.target.value)} />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
        <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <CardTitle className="text-lg font-mono uppercase tracking-widest">Live Signal Scoreboard</CardTitle>
              <CardDescription>
                Measures exported/live signals against realized market movement. This is the next layer after backtests.
              </CardDescription>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="secondary" onClick={loadSignalPerformance} disabled={isSignalBusy} className="font-mono uppercase tracking-wider">
                Load Scoreboard
              </Button>
              <Button onClick={settleSignals} disabled={isSignalBusy} className="font-mono uppercase tracking-wider">
                Settle Open Signals
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-6">
          {!signalPerformance?.summary ? (
            <div className="text-xs font-mono uppercase tracking-wider text-muted-foreground">No live signal performance loaded</div>
          ) : (
            <div className="space-y-6">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
                <Card className="border border-border/60"><CardContent className="pt-5"><div className="text-[10px] font-mono uppercase text-muted-foreground">Total Signals</div><div className="text-2xl font-bold">{signalPerformance.summary.total_signals}</div></CardContent></Card>
                <Card className="border border-border/60"><CardContent className="pt-5"><div className="text-[10px] font-mono uppercase text-muted-foreground">Open</div><div className="text-2xl font-bold">{signalPerformance.summary.open_signals}</div></CardContent></Card>
                <Card className="border border-border/60"><CardContent className="pt-5"><div className="text-[10px] font-mono uppercase text-muted-foreground">Settled Win Rate</div><div className="text-2xl font-bold">{signalPerformance.summary.win_rate.toFixed(1)}%</div></CardContent></Card>
                <Card className="border border-border/60"><CardContent className="pt-5"><div className="text-[10px] font-mono uppercase text-muted-foreground">Avg Return %</div><div className="text-2xl font-bold">{signalPerformance.summary.avg_realized_return_pct.toFixed(2)}%</div></CardContent></Card>
              </div>

              <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
                <Card className="border border-border/60">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-mono uppercase tracking-wider">By Source</CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="font-mono text-[10px] uppercase">Source</TableHead>
                          <TableHead className="font-mono text-[10px] uppercase">Signals</TableHead>
                          <TableHead className="font-mono text-[10px] uppercase">Win Rate</TableHead>
                          <TableHead className="font-mono text-[10px] uppercase">Avg Return %</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {!(signalPerformance.by_source || []).length ? (
                          <TableRow><TableCell colSpan={4} className="h-24 text-center text-xs font-mono text-muted-foreground uppercase">No settled sources yet</TableCell></TableRow>
                        ) : (
                          signalPerformance.by_source!.map((row) => (
                            <TableRow key={row.source}>
                              <TableCell className="font-mono text-xs">{row.source}</TableCell>
                              <TableCell className="font-mono text-xs">{row.signals}</TableCell>
                              <TableCell className="font-mono text-xs">{row.win_rate.toFixed(1)}%</TableCell>
                              <TableCell className="font-mono text-xs">{row.avg_return_pct.toFixed(2)}%</TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>

                <Card className="border border-border/60">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-mono uppercase tracking-wider">Recent Signals</CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    <div className="max-h-[280px] overflow-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="font-mono text-[10px] uppercase">Time</TableHead>
                            <TableHead className="font-mono text-[10px] uppercase">Action</TableHead>
                            <TableHead className="font-mono text-[10px] uppercase">Status</TableHead>
                            <TableHead className="font-mono text-[10px] uppercase">Return %</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {!(signalPerformance.signals || []).length ? (
                            <TableRow><TableCell colSpan={4} className="h-24 text-center text-xs font-mono text-muted-foreground uppercase">No signals tracked yet</TableCell></TableRow>
                          ) : (
                            signalPerformance.signals!.slice(0, 20).map((row) => (
                              <TableRow key={row.signal_id}>
                                <TableCell className="font-mono text-xs">{new Date(row.created_at).toLocaleString()}</TableCell>
                                <TableCell className="font-mono text-xs">{row.action}</TableCell>
                                <TableCell className="font-mono text-xs uppercase">{row.status}</TableCell>
                                <TableCell className={cn("font-mono text-xs", (row.realized_return_pct || 0) >= 0 ? "text-primary" : "text-destructive")}>
                                  {(row.realized_return_pct || 0).toFixed(2)}%
                                </TableCell>
                              </TableRow>
                            ))
                          )}
                        </TableBody>
                      </Table>
                    </div>
                  </CardContent>
                </Card>

                <Card className="border border-border/60">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-mono uppercase tracking-wider">Component Reliability</CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    <div className="max-h-[280px] overflow-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="font-mono text-[10px] uppercase">Component</TableHead>
                            <TableHead className="font-mono text-[10px] uppercase">Samples</TableHead>
                            <TableHead className="font-mono text-[10px] uppercase">Hit Rate</TableHead>
                            <TableHead className="font-mono text-[10px] uppercase">Avg Abs</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {!(signalPerformance.component_reliability || []).length ? (
                            <TableRow><TableCell colSpan={4} className="h-24 text-center text-xs font-mono text-muted-foreground uppercase">No component data yet</TableCell></TableRow>
                          ) : (
                            signalPerformance.component_reliability!.map((row) => (
                              <TableRow key={row.component}>
                                <TableCell className="font-mono text-xs">{row.component}</TableCell>
                                <TableCell className="font-mono text-xs">{row.samples}</TableCell>
                                <TableCell className="font-mono text-xs">{row.hit_rate.toFixed(1)}%</TableCell>
                                <TableCell className="font-mono text-xs">{row.avg_abs_weight.toFixed(3)}</TableCell>
                              </TableRow>
                            ))
                          )}
                        </TableBody>
                      </Table>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
        <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <CardTitle className="text-lg font-mono uppercase tracking-widest">Execution Quality</CardTitle>
              <CardDescription>
                Measures fill quality, broker rejects, and realized slippage so risk can adapt to actual execution conditions.
              </CardDescription>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Select value={forecastSide} onValueChange={(value: 'BUY' | 'SELL') => setForecastSide(value)}>
                <SelectTrigger className="w-[120px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="BUY">BUY</SelectItem>
                  <SelectItem value="SELL">SELL</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="outline" onClick={loadExecutionForecast} disabled={isExecutionBusy} className="font-mono uppercase tracking-wider">
                Load Forecast
              </Button>
              <Button variant="outline" onClick={loadRoutingStatus} disabled={isExecutionBusy} className="font-mono uppercase tracking-wider">
                Load Routing
              </Button>
              <Button variant="secondary" onClick={loadExecutionQuality} disabled={isExecutionBusy} className="font-mono uppercase tracking-wider">
                Load Execution Quality
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-6">
          {!executionQuality?.summary && !executionForecast?.forecast ? (
            <div className="text-xs font-mono uppercase tracking-wider text-muted-foreground">No execution quality or forecast loaded</div>
          ) : (
            <div className="space-y-6">
              {executionForecast?.forecast && (
                <Card className="border border-border/60">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-mono uppercase tracking-wider">Pre-Trade Forecast</CardTitle>
                    <CardDescription>
                      Symbol/broker/session-based estimate used to throttle strategy execution before sending the order.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-8">
                    <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Basis</div><div className="font-mono text-xs uppercase">{executionForecast.forecast.basis}</div></div>
                    <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Samples</div><div className="font-mono text-xs">{executionForecast.forecast.sample_count}</div></div>
                    <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Slip</div><div className="font-mono text-xs">{executionForecast.forecast.expected_slippage_bps.toFixed(2)} bps</div></div>
                    <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Reject</div><div className="font-mono text-xs">{executionForecast.forecast.expected_reject_rate.toFixed(1)}%</div></div>
                    <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Fill %</div><div className="font-mono text-xs">{(executionForecast.forecast.expected_fill_ratio * 100).toFixed(1)}%</div></div>
                    <div><div className="text-[10px] font-mono uppercase text-muted-foreground">TTF</div><div className="font-mono text-xs">{Math.round(executionForecast.forecast.expected_time_to_fill_ms)} ms</div></div>
                    <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Risk Mult</div><div className="font-mono text-xs">{executionForecast.forecast.risk_multiplier.toFixed(2)}</div></div>
                    <div><div className="text-[10px] font-mono uppercase text-muted-foreground">Action</div><div className={cn("font-mono text-xs uppercase", executionForecast.forecast.recommendation === 'avoid' ? 'text-destructive' : executionForecast.forecast.recommendation === 'reduce_size' ? 'text-amber-400' : 'text-primary')}>{executionForecast.forecast.recommendation}</div></div>
                  </CardContent>
                </Card>
              )}

              {routingStatus?.status === 'success' && (
                <Card className="border border-border/60">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-mono uppercase tracking-wider">Routing Snapshot</CardTitle>
                    <CardDescription>
                      Ranked execution and market-data paths used to decide whether to proceed, reduce size, or avoid a route.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                      <div className="rounded-lg border border-border/60 p-3">
                        <div className="text-[10px] font-mono uppercase text-muted-foreground">Execution Route</div>
                        <div className="font-mono text-sm uppercase">{routingStatus.recommended_execution_broker?.broker || 'n/a'}</div>
                        <div className="font-mono text-xs text-muted-foreground">
                          {routingStatus.recommended_execution_broker?.recommendation || 'unknown'} | score {(routingStatus.recommended_execution_broker?.score || 0).toFixed(2)}
                        </div>
                      </div>
                      <div className="rounded-lg border border-border/60 p-3">
                        <div className="text-[10px] font-mono uppercase text-muted-foreground">Data Route</div>
                        <div className="font-mono text-sm uppercase">{routingStatus.recommended_market_data_provider?.provider || 'n/a'}</div>
                        <div className="font-mono text-xs text-muted-foreground">
                          {routingStatus.recommended_market_data_provider?.recommendation || 'unknown'} | score {(routingStatus.recommended_market_data_provider?.route_score || 0).toFixed(2)}
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
                      <Card className="border border-border/60">
                        <CardHeader className="pb-3">
                          <CardTitle className="text-sm font-mono uppercase tracking-wider">Execution Brokers</CardTitle>
                        </CardHeader>
                        <CardContent className="p-0">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead className="font-mono text-[10px] uppercase">Broker</TableHead>
                                <TableHead className="font-mono text-[10px] uppercase">Score</TableHead>
                                <TableHead className="font-mono text-[10px] uppercase">Reject</TableHead>
                                <TableHead className="font-mono text-[10px] uppercase">Reco</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {!(routingStatus.execution_brokers || []).length ? (
                                <TableRow><TableCell colSpan={4} className="h-20 text-center text-xs font-mono text-muted-foreground uppercase">No broker routes</TableCell></TableRow>
                              ) : (
                                routingStatus.execution_brokers!.map((row) => (
                                  <TableRow key={row.broker}>
                                    <TableCell className="font-mono text-xs">{row.current ? `${row.broker} *` : row.broker}</TableCell>
                                    <TableCell className="font-mono text-xs">{row.score.toFixed(2)}</TableCell>
                                    <TableCell className="font-mono text-xs">{row.reject_rate.toFixed(1)}%</TableCell>
                                    <TableCell className="font-mono text-xs uppercase">{row.recommendation}</TableCell>
                                  </TableRow>
                                ))
                              )}
                            </TableBody>
                          </Table>
                        </CardContent>
                      </Card>

                      <Card className="border border-border/60">
                        <CardHeader className="pb-3">
                          <CardTitle className="text-sm font-mono uppercase tracking-wider">Market Data Providers</CardTitle>
                        </CardHeader>
                        <CardContent className="p-0">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead className="font-mono text-[10px] uppercase">Provider</TableHead>
                                <TableHead className="font-mono text-[10px] uppercase">Score</TableHead>
                                <TableHead className="font-mono text-[10px] uppercase">P</TableHead>
                                <TableHead className="font-mono text-[10px] uppercase">Reco</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {!(routingStatus.market_data_providers || []).length ? (
                                <TableRow><TableCell colSpan={4} className="h-20 text-center text-xs font-mono text-muted-foreground uppercase">No provider routes</TableCell></TableRow>
                              ) : (
                                routingStatus.market_data_providers!.map((row) => (
                                  <TableRow key={row.provider}>
                                    <TableCell className="font-mono text-xs">{row.provider}</TableCell>
                                    <TableCell className="font-mono text-xs">{row.route_score.toFixed(2)}</TableCell>
                                    <TableCell className="font-mono text-xs">{row.priority}</TableCell>
                                    <TableCell className="font-mono text-xs uppercase">{row.recommendation}</TableCell>
                                  </TableRow>
                                ))
                              )}
                            </TableBody>
                          </Table>
                        </CardContent>
                      </Card>
                    </div>
                  </CardContent>
                </Card>
              )}

              {executionQuality?.summary && (
                <>
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-7">
                    <Card className="border border-border/60"><CardContent className="pt-5"><div className="text-[10px] font-mono uppercase text-muted-foreground">Total Orders</div><div className="text-2xl font-bold">{executionQuality.summary.total_orders}</div></CardContent></Card>
                    <Card className="border border-border/60"><CardContent className="pt-5"><div className="text-[10px] font-mono uppercase text-muted-foreground">Fill Rate</div><div className="text-2xl font-bold">{executionQuality.summary.fill_rate.toFixed(1)}%</div></CardContent></Card>
                    <Card className="border border-border/60"><CardContent className="pt-5"><div className="text-[10px] font-mono uppercase text-muted-foreground">Reject Rate</div><div className="text-2xl font-bold">{executionQuality.summary.reject_rate.toFixed(1)}%</div></CardContent></Card>
                    <Card className="border border-border/60"><CardContent className="pt-5"><div className="text-[10px] font-mono uppercase text-muted-foreground">Avg Fill %</div><div className="text-2xl font-bold">{(executionQuality.summary.avg_fill_ratio * 100).toFixed(1)}%</div></CardContent></Card>
                    <Card className="border border-border/60"><CardContent className="pt-5"><div className="text-[10px] font-mono uppercase text-muted-foreground">Avg Slippage</div><div className="text-2xl font-bold">{executionQuality.summary.avg_slippage_bps.toFixed(2)} bps</div></CardContent></Card>
                    <Card className="border border-border/60"><CardContent className="pt-5"><div className="text-[10px] font-mono uppercase text-muted-foreground">Avg TTF</div><div className="text-2xl font-bold">{Math.round(executionQuality.summary.avg_time_to_fill_ms)} ms</div></CardContent></Card>
                    <Card className="border border-border/60"><CardContent className="pt-5"><div className="text-[10px] font-mono uppercase text-muted-foreground">Quality Score</div><div className="text-2xl font-bold">{(executionQuality.summary.quality_score * 100).toFixed(0)}</div></CardContent></Card>
                  </div>

                  <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
                    <Card className="border border-border/60">
                      <CardHeader className="pb-3">
                        <CardTitle className="text-sm font-mono uppercase tracking-wider">By Broker</CardTitle>
                      </CardHeader>
                      <CardContent className="p-0">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead className="font-mono text-[10px] uppercase">Broker</TableHead>
                              <TableHead className="font-mono text-[10px] uppercase">Orders</TableHead>
                              <TableHead className="font-mono text-[10px] uppercase">Fill Rate</TableHead>
                              <TableHead className="font-mono text-[10px] uppercase">Reject Rate</TableHead>
                              <TableHead className="font-mono text-[10px] uppercase">Fill %</TableHead>
                              <TableHead className="font-mono text-[10px] uppercase">Quality</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {!(executionQuality.by_broker || []).length ? (
                              <TableRow><TableCell colSpan={6} className="h-24 text-center text-xs font-mono text-muted-foreground uppercase">No broker execution data yet</TableCell></TableRow>
                            ) : (
                              executionQuality.by_broker!.map((row) => (
                                <TableRow key={row.broker}>
                                  <TableCell className="font-mono text-xs">{row.broker}</TableCell>
                                  <TableCell className="font-mono text-xs">{row.orders}</TableCell>
                                  <TableCell className="font-mono text-xs">{row.fill_rate.toFixed(1)}%</TableCell>
                                  <TableCell className="font-mono text-xs">{row.reject_rate.toFixed(1)}%</TableCell>
                                  <TableCell className="font-mono text-xs">{(row.avg_fill_ratio * 100).toFixed(1)}%</TableCell>
                                  <TableCell className="font-mono text-xs">{(row.quality_score * 100).toFixed(0)}</TableCell>
                                </TableRow>
                              ))
                            )}
                          </TableBody>
                        </Table>
                      </CardContent>
                    </Card>

                    <Card className="border border-border/60">
                      <CardHeader className="pb-3">
                        <CardTitle className="text-sm font-mono uppercase tracking-wider">Recent Execution Events</CardTitle>
                      </CardHeader>
                      <CardContent className="p-0">
                        <div className="max-h-[280px] overflow-auto">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead className="font-mono text-[10px] uppercase">Time</TableHead>
                                <TableHead className="font-mono text-[10px] uppercase">Broker</TableHead>
                                <TableHead className="font-mono text-[10px] uppercase">Status</TableHead>
                                <TableHead className="font-mono text-[10px] uppercase">Slip</TableHead>
                              <TableHead className="font-mono text-[10px] uppercase">Fill %</TableHead>
                              <TableHead className="font-mono text-[10px] uppercase">TTF</TableHead>
                              <TableHead className="font-mono text-[10px] uppercase">Score</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                              {!(executionQuality.recent || []).length ? (
                                <TableRow><TableCell colSpan={7} className="h-24 text-center text-xs font-mono text-muted-foreground uppercase">No execution events tracked yet</TableCell></TableRow>
                              ) : (
                                executionQuality.recent!.slice(0, 20).map((row) => (
                                  <TableRow key={row.execution_id}>
                                    <TableCell className="font-mono text-xs">{new Date(row.created_at).toLocaleString()}</TableCell>
                                    <TableCell className="font-mono text-xs">{row.broker}</TableCell>
                                    <TableCell className="font-mono text-xs uppercase">{row.status}</TableCell>
                                    <TableCell className={cn("font-mono text-xs", (row.slippage_bps || 0) > 8 ? "text-destructive" : "text-primary")}>
                                      {row.slippage_bps == null ? '-' : `${row.slippage_bps.toFixed(2)} bps`}
                                    </TableCell>
                                    <TableCell className="font-mono text-xs">{row.fill_ratio == null ? '-' : `${(row.fill_ratio * 100).toFixed(1)}%`}</TableCell>
                                    <TableCell className="font-mono text-xs">{row.time_to_fill_ms == null ? '-' : `${Math.round(row.time_to_fill_ms)} ms`}</TableCell>
                                    <TableCell className="font-mono text-xs">{(row.quality_score * 100).toFixed(0)}</TableCell>
                                  </TableRow>
                                ))
                              )}
                            </TableBody>
                          </Table>
                        </div>
                      </CardContent>
                    </Card>
                  </div>
                </>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
        <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <CardTitle className="text-lg font-mono uppercase tracking-widest flex items-center gap-2">
                <DatabaseZap className="w-4 h-4 text-primary" />
                News Event Study
              </CardTitle>
              <CardDescription>
                Calibrate headline impact against realized forward returns so the news model is scored on market outcomes, not only sentiment heuristics.
              </CardDescription>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="secondary" onClick={loadEventStudy} disabled={isEventStudyBusy} className="font-mono uppercase tracking-wider">
                Load Latest
              </Button>
              <Button onClick={trainEventStudy} disabled={isEventStudyBusy} className="font-mono uppercase tracking-wider">
                {isEventStudyBusy ? 'Training...' : 'Train Event Study'}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-6">
          {!eventStudy ? (
            <div className="text-xs font-mono uppercase tracking-wider text-muted-foreground">No event-study artifact loaded</div>
          ) : (
            <div className="grid grid-cols-1 gap-6 xl:grid-cols-[280px_minmax(0,1fr)]">
              <div className="rounded-lg border border-border/60 bg-background/70 p-4 space-y-3">
                <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">Calibration Snapshot</div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Status</span>
                  <Badge variant={eventStudy.status === 'success' ? 'default' : 'destructive'} className="font-mono uppercase text-[10px]">
                    {eventStudy.status}
                  </Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Benchmark</span>
                  <span className="font-mono text-xs">{eventStudy.benchmark_ticker || backtestForm.ticker}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Samples</span>
                  <span className="font-mono text-xs">{eventStudy.samples ?? 0}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Hit Rate</span>
                  <span className="font-mono text-xs text-primary">{eventStudy.metrics ? (eventStudy.metrics.direction_hit_rate * 100).toFixed(1) : '0.0'}%</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Impact Corr</span>
                  <span className="font-mono text-xs">{eventStudy.metrics?.impact_correlation ?? 0}</span>
                </div>
                {eventStudy.message && (
                  <div className="pt-3 border-t border-border/50 text-xs text-destructive">{eventStudy.message}</div>
                )}
              </div>

              <Card className="border border-border/60">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-mono uppercase tracking-wider">Calibration Buckets</CardTitle>
                  <CardDescription>Directional reliability and multiplier estimates derived from matured events.</CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                  <div className="max-h-[280px] overflow-auto">
                    <Table>
                      <TableHeader className="bg-secondary/30 sticky top-0">
                        <TableRow className="border-border hover:bg-transparent">
                          <TableHead className="font-mono text-[10px] uppercase">Bucket</TableHead>
                          <TableHead className="font-mono text-[10px] uppercase">Samples</TableHead>
                          <TableHead className="font-mono text-[10px] uppercase">Hit Rate</TableHead>
                          <TableHead className="font-mono text-[10px] uppercase">Multiplier</TableHead>
                          <TableHead className="font-mono text-[10px] uppercase">Avg Move %</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {!eventStudy.buckets || eventStudy.buckets.length === 0 ? (
                          <TableRow>
                            <TableCell colSpan={5} className="h-28 text-center text-xs font-mono text-muted-foreground uppercase tracking-wider">
                              No calibration buckets loaded
                            </TableCell>
                          </TableRow>
                        ) : (
                          eventStudy.buckets.map((bucket) => (
                            <TableRow key={bucket.bucket} className="border-border hover:bg-secondary/20">
                              <TableCell className="font-mono text-xs uppercase">{bucket.bucket}</TableCell>
                              <TableCell className="font-mono text-xs">{bucket.samples}</TableCell>
                              <TableCell className="font-mono text-xs">{(bucket.direction_hit_rate * 100).toFixed(1)}%</TableCell>
                              <TableCell className="font-mono text-xs">{bucket.median_impact_multiplier}</TableCell>
                              <TableCell className="font-mono text-xs">{bucket.avg_realized_move_pct}</TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border border-primary/20 bg-secondary/10 overflow-hidden">
        <CardHeader className="border-b border-border/50 bg-gradient-to-r from-primary/10 via-transparent to-transparent">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <CardTitle className="text-lg font-mono uppercase tracking-widest flex items-center gap-2">
                <BrainCircuit className="w-4 h-4 text-primary" />
                Pattern Governor Training
              </CardTitle>
              <CardDescription>
                Train and persist only historically approved patterns that clear your win-rate threshold.
              </CardDescription>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="secondary"
                onClick={loadApprovedPatterns}
                disabled={isPatternBusy}
                className="font-mono uppercase tracking-wider"
              >
                Load Latest
                <DatabaseZap className="ml-2 w-4 h-4" />
              </Button>
              <Button
                onClick={runPatternTraining}
                disabled={isPatternBusy}
                className="font-mono uppercase tracking-wider"
              >
                {isPatternBusy ? 'Training...' : 'Train Approved Set'}
                <Target className="ml-2 w-4 h-4" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-6 pt-6">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Ticker</Label>
              <Input value={patternForm.ticker} onChange={(e) => updatePatternField('ticker', e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Interval</Label>
              <Select value={patternForm.interval} onValueChange={(value) => updatePatternField('interval', value)}>
                <SelectTrigger>
                  <SelectValue placeholder="Interval" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="5m">5m</SelectItem>
                  <SelectItem value="15m">15m</SelectItem>
                  <SelectItem value="30m">30m</SelectItem>
                  <SelectItem value="1h">1h</SelectItem>
                  <SelectItem value="1d">1d</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">History Window</Label>
              <Select value={patternForm.period} onValueChange={(value) => updatePatternField('period', value)}>
                <SelectTrigger>
                  <SelectValue placeholder="Period" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="6mo">6mo</SelectItem>
                  <SelectItem value="1y">1y</SelectItem>
                  <SelectItem value="2y">2y</SelectItem>
                  <SelectItem value="5y">5y</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Win-Rate Floor %</Label>
              <Input value={patternForm.min_win_rate_percent} onChange={(e) => updatePatternField('min_win_rate_percent', e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Min Samples</Label>
              <Input value={patternForm.min_samples} onChange={(e) => updatePatternField('min_samples', e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Horizon Bars</Label>
              <Input value={patternForm.horizon_bars} onChange={(e) => updatePatternField('horizon_bars', e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Stop ATR</Label>
              <Input value={patternForm.stop_atr} onChange={(e) => updatePatternField('stop_atr', e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label className="text-[10px] uppercase font-mono tracking-widest text-muted-foreground">Target ATR</Label>
              <Input value={patternForm.target_atr} onChange={(e) => updatePatternField('target_atr', e.target.value)} />
            </div>
          </div>

          {patternTraining && (
            <div className="grid grid-cols-1 gap-6 xl:grid-cols-[280px_minmax(0,1fr)]">
              <div className="rounded-lg border border-border/60 bg-background/70 p-4 space-y-3">
                <div className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">Training Snapshot</div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Status</span>
                  <Badge variant={patternTraining.status === 'success' ? 'default' : 'destructive'} className="font-mono uppercase text-[10px]">
                    {patternTraining.status}
                  </Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Ticker</span>
                  <span className="font-mono text-xs">{patternTraining.ticker || patternForm.ticker}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Interval</span>
                  <span className="font-mono text-xs">{patternTraining.interval || patternForm.interval}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Rows</span>
                  <span className="font-mono text-xs">{patternTraining.rows ?? 0}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Approved</span>
                  <span className="font-mono text-xs text-primary">{patternTraining.approved_patterns?.length ?? 0}</span>
                </div>
                {patternTraining.thresholds && (
                  <div className="pt-3 border-t border-border/50 text-[10px] font-mono text-muted-foreground space-y-1">
                    <div>Floor: {(patternTraining.thresholds.min_win_rate * 100).toFixed(0)}%</div>
                    <div>Samples: {patternTraining.thresholds.min_samples}</div>
                    <div>Horizon: {patternTraining.thresholds.horizon_bars} bars</div>
                  </div>
                )}
                {patternTraining.message && (
                  <div className="pt-3 border-t border-border/50 text-xs text-destructive">
                    {patternTraining.message}
                  </div>
                )}
              </div>

              <Card className="border border-border/60">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-mono uppercase tracking-wider">Approved Patterns</CardTitle>
                  <CardDescription>
                    Patterns that passed the historical filter for this ticker and interval.
                  </CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                  <div className="max-h-[320px] overflow-auto">
                    <Table>
                      <TableHeader className="bg-secondary/30 sticky top-0">
                        <TableRow className="border-border hover:bg-transparent">
                          <TableHead className="font-mono text-[10px] uppercase">Pattern</TableHead>
                          <TableHead className="font-mono text-[10px] uppercase">Samples</TableHead>
                          <TableHead className="font-mono text-[10px] uppercase">Wins</TableHead>
                          <TableHead className="font-mono text-[10px] uppercase">Losses</TableHead>
                          <TableHead className="font-mono text-[10px] uppercase">Win Rate</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {!patternTraining.approved_patterns || patternTraining.approved_patterns.length === 0 ? (
                          <TableRow>
                            <TableCell colSpan={5} className="h-36 text-center text-xs font-mono text-muted-foreground uppercase tracking-wider">
                              No approved patterns loaded
                            </TableCell>
                          </TableRow>
                        ) : (
                          patternTraining.approved_patterns.map((pattern) => (
                            <TableRow key={pattern.pattern_id} className="border-border hover:bg-secondary/20">
                              <TableCell className="font-mono text-xs uppercase">{pattern.pattern_id}</TableCell>
                              <TableCell className="font-mono text-xs">{pattern.samples}</TableCell>
                              <TableCell className="font-mono text-xs text-primary">{pattern.wins}</TableCell>
                              <TableCell className="font-mono text-xs text-destructive">{pattern.losses}</TableCell>
                              <TableCell className="font-mono text-xs">{(pattern.win_rate * 100).toFixed(1)}%</TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </CardContent>
      </Card>

      {isRunning && (
        <div className="space-y-2 animate-pulse">
          <div className="flex justify-between text-[10px] font-mono uppercase text-muted-foreground">
            <span>{engineMode === 'walkforward' ? 'Rolling train/test windows and scoring out-of-sample...' : 'Downloading historical data and simulating trades...'}</span>
            <span>{Math.round(progress)}%</span>
          </div>
          <Progress value={progress} className="h-1 bg-secondary" />
        </div>
      )}

      {summary && summary.error && (
        <Card className="border-red-500/50 bg-red-500/10">
          <CardContent className="pt-6 flex items-center gap-4 text-red-600">
            <AlertCircle className="w-6 h-6" />
            <div>
              <p className="font-bold">Simulation Failed</p>
              <p className="text-sm">{summary.error}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {summary && !summary.error && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card className="border-2 border-primary/10">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-mono uppercase text-muted-foreground">
                {summary.mode === 'walkforward' ? 'Total Return' : 'Cumulative P/L'}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className={cn(
                "text-3xl font-bold tracking-tighter",
                (summary.mode === 'walkforward' ? (summary.total_return_pct || 0) : summary.total_pnl) >= 0 ? "text-primary" : "text-destructive"
              )}>
                {summary.mode === 'walkforward'
                  ? `${summary.total_return_pct?.toFixed(2) || '0.00'}%`
                  : formatCurrency(summary.total_pnl, 'IN')}
              </div>
            </CardContent>
          </Card>
          <Card className="border-2 border-primary/10">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-mono uppercase text-muted-foreground">Accuracy (Win Rate)</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold tracking-tighter">
                {summary.win_rate}%
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                {summary.mode === 'walkforward'
                  ? `${summary.folds?.length || 0} folds`
                  : `${summary.total_trades} total trades`}
              </div>
            </CardContent>
          </Card>
          <Card className="border-2 border-primary/10">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-mono uppercase text-muted-foreground">
                {summary.mode === 'walkforward' ? 'Sharpe / Max DD' : 'Profit Factor'}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold tracking-tighter">
                {summary.mode === 'walkforward'
                  ? `${summary.sharpe_ratio?.toFixed(2) || '0.00'} / ${summary.max_drawdown?.toFixed(2) || '0.00'}%`
                  : summary.profit_factor}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                {summary.mode === 'walkforward'
                  ? `Ending Equity: ${summary.ending_equity?.toFixed(3) || '1.000'}`
                  : `Avg Win: ${formatCurrency(summary.avg_win, 'IN')}`}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {summary && !summary.error && summary.mode !== 'walkforward' && (
        <Card className="border border-border">
          <CardHeader className="border-b border-border/50">
            <CardTitle className="text-lg font-mono uppercase tracking-tight">Trade Log</CardTitle>
            <CardDescription>Simulated Execution on {summary.ticker || "NIFTY 50"} ({summary.period})</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="max-h-[500px] overflow-auto">
              <Table>
                <TableHeader className="bg-secondary/30 sticky top-0">
                  <TableRow className="border-border hover:bg-transparent">
                    <TableHead className="font-mono text-[10px] uppercase">Entry Time</TableHead>
                    <TableHead className="font-mono text-[10px] uppercase">Exit Time</TableHead>
                    <TableHead className="font-mono text-[10px] uppercase">Type</TableHead>
                    <TableHead className="font-mono text-[10px] uppercase">Outcome</TableHead>
                    <TableHead className="font-mono text-[10px] uppercase text-right">P/L</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {summary.trades.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="h-64 text-center">
                        <div className="flex flex-col items-center justify-center opacity-30">
                          <ShieldOff className="w-12 h-12 mb-4" />
                          <p className="text-xs font-mono uppercase tracking-widest">No trades generated</p>
                          <p className="text-[10px] mt-2 italic">Strategy conditions were not met in this period</p>
                        </div>
                      </TableCell>
                    </TableRow>
                  ) : (
                    summary.trades.map((trade, idx) => (
                      <TableRow key={idx} className="border-border hover:bg-secondary/20 transition-colors">
                        <TableCell className="font-mono text-xs">
                          {new Date(trade.entry_time).toLocaleString()}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {new Date(trade.exit_time).toLocaleTimeString()}
                        </TableCell>
                        <TableCell className="text-xs font-mono italic">
                          {trade.reason || "Signal"}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={trade.pnl > 0 ? 'default' : 'destructive'}
                            className="font-mono text-[9px] px-2 py-0 uppercase"
                          >
                            {trade.pnl > 0 ? 'PROFIT' : 'LOSS'}
                          </Badge>
                        </TableCell>
                        <TableCell className={cn(
                          "text-right font-mono text-xs font-bold",
                          trade.pnl > 0 ? "text-primary" : "text-destructive"
                        )}>
                          {formatCurrency(trade.pnl, 'IN')}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {summary && !summary.error && summary.mode === 'walkforward' && (
        <Card className="border border-border">
          <CardHeader className="border-b border-border/50">
            <CardTitle className="text-lg font-mono uppercase tracking-tight">Walk-Forward Fold Log</CardTitle>
            <CardDescription>Rolling out-of-sample windows for {summary.ticker || backtestForm.ticker} ({summary.period})</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="max-h-[500px] overflow-auto">
              <Table>
                <TableHeader className="bg-secondary/30 sticky top-0">
                  <TableRow className="border-border hover:bg-transparent">
                    <TableHead className="font-mono text-[10px] uppercase">Test Start</TableHead>
                    <TableHead className="font-mono text-[10px] uppercase">Test End</TableHead>
                    <TableHead className="font-mono text-[10px] uppercase">Samples</TableHead>
                    <TableHead className="font-mono text-[10px] uppercase">Hit Rate</TableHead>
                    <TableHead className="font-mono text-[10px] uppercase text-right">Fold PnL</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {!summary.folds || summary.folds.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="h-36 text-center text-xs font-mono text-muted-foreground uppercase tracking-wider">
                        No walk-forward folds returned
                      </TableCell>
                    </TableRow>
                  ) : (
                    summary.folds.map((fold, idx) => (
                      <TableRow key={idx} className="border-border hover:bg-secondary/20 transition-colors">
                        <TableCell className="font-mono text-xs">{new Date(fold.test_start).toLocaleString()}</TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">{new Date(fold.test_end).toLocaleString()}</TableCell>
                        <TableCell className="font-mono text-xs">{fold.samples}</TableCell>
                        <TableCell className="font-mono text-xs">{(fold.hit_rate * 100).toFixed(1)}%</TableCell>
                        <TableCell className={cn("text-right font-mono text-xs font-bold", fold.pnl_sum >= 0 ? "text-primary" : "text-destructive")}>
                          {fold.pnl_sum.toFixed(4)}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Training Logs Dialog / Area */}
      {summary?.training_logs && (
        <Card className="border border-primary/20 bg-secondary/10 mt-6">
          <CardHeader>
            <CardTitle className="text-sm font-mono uppercase flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-primary" />
              AI Training Log (Optimization Process)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-48 overflow-y-auto font-mono text-[10px] space-y-1 p-2 bg-background border rounded-md">
              {summary.training_logs.map((log, i) => (
                <div key={i} className={cn(
                  "border-l-2 pl-2 py-1",
                  log.includes("Winner") ? "border-green-500 text-green-500 font-bold bg-green-500/10" : "border-border text-muted-foreground"
                )}>
                  {log}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

    </div>
  )
}
