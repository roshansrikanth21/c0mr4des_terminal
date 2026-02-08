import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Play, RotateCcw, TrendingUp, TrendingDown, Minus, ShieldOff, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatCurrency } from '@/lib/market-config';

interface TradeResult {
  entry_time: string;
  exit_time: string;
  entry_price: number;
  exit_price: number;
  reason: string;
  pnl: number;
}

interface BacktestSummary {
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
}

export function Backtest() {
  const [summary, setSummary] = useState<BacktestSummary | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState(0);

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
      const res = await fetch('http://localhost:8000/api/backtest?ticker=^NSEI&interval=15m&period=60d', {
        method: 'POST'
      });
      const data = await res.json();

      clearInterval(progressInterval);
      setProgress(100);
      setSummary(data);
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
            SIMULATING INTRADAY STRATEGY ON {summary?.is_simulation ? "SYNTHETIC MARKET DATA" : "NIFTY 50 (LAST 60 DAYS)"}
          </p>
        </div>
        <div className="flex gap-4">
          <Button
            onClick={runBacktest}
            disabled={isRunning}
            className="font-mono uppercase tracking-tighter h-12 px-8"
          >
            {isRunning ? 'Processing...' : summary ? 'Re-run Simulation' : 'Run Backtest'}
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
                const res = await fetch('http://localhost:8000/api/train', { method: 'POST' });
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

      {isRunning && (
        <div className="space-y-2 animate-pulse">
          <div className="flex justify-between text-[10px] font-mono uppercase text-muted-foreground">
            <span>Downloading Historical Data & Simulating Trades...</span>
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
              <CardTitle className="text-xs font-mono uppercase text-muted-foreground">Cumulative P/L</CardTitle>
            </CardHeader>
            <CardContent>
              <div className={cn(
                "text-3xl font-bold tracking-tighter",
                summary.total_pnl >= 0 ? "text-primary" : "text-destructive"
              )}>
                {formatCurrency(summary.total_pnl, 'IN')}
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
                {summary.total_trades} total trades
              </div>
            </CardContent>
          </Card>
          <Card className="border-2 border-primary/10">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-mono uppercase text-muted-foreground">Profit Factor</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold tracking-tighter">
                {summary.profit_factor}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                Avg Win: {formatCurrency(summary.avg_win, 'IN')}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {summary && !summary.error && (
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
