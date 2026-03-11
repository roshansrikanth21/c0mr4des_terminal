import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { blink } from '@/lib/blink';
import { useAuth } from '@/hooks/use-auth';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface Trade {
  id: string;
  symbol: string;
  strategy: string;
  regime: string;
  entryPrice: number;
  exitPrice: number;
  status: string;
  pnl: number;
  createdAt: string;
}

export function History() {
  const { user } = useAuth();
  const [trades, setTrades] = useState<Trade[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function fetchTrades() {
      if (!user) return;
      try {
        const list = await (blink.db as any).trades.list({
          where: { user_id: user.id },
          orderBy: { created_at: 'desc' }
        });

        setTrades(list.map((t: any) => ({
          id: t.id,
          symbol: t.symbol,
          strategy: t.strategy,
          regime: t.regime,
          entryPrice: Number(t.entry_price),
          exitPrice: Number(t.exit_price),
          status: t.status,
          pnl: Number(t.pnl),
          createdAt: t.created_at
        })));
      } catch (error) {
        console.error('Error fetching trades:', error);
      } finally {
        setIsLoading(false);
      }
    }
    fetchTrades();
  }, [user]);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'closed': return <Badge variant="outline">CLOSED</Badge>;
      case 'open': return <Badge variant="secondary" className="bg-primary text-primary-foreground">OPEN</Badge>;
      case 'rejected': return <Badge variant="destructive">FILTERED</Badge>;
      default: return <Badge variant="outline">{status.toUpperCase()}</Badge>;
    }
  };

  const getPnlDisplay = (pnl: number) => {
    if (pnl > 0) return <span className="text-primary font-bold flex items-center"><TrendingUp className="w-3 h-3 mr-1" />+${pnl.toFixed(2)}</span>;
    if (pnl < 0) return <span className="text-destructive font-bold flex items-center"><TrendingDown className="w-3 h-3 mr-1" />-${Math.abs(pnl).toFixed(2)}</span>;
    return <span className="text-muted-foreground flex items-center"><Minus className="w-3 h-3 mr-1" />$0.00</span>;
  };

  if (isLoading) return <div className="p-10 text-center font-mono animate-pulse">Retrieving Operational Records...</div>;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tighter mb-2 uppercase">Execution Log</h1>
        <p className="text-muted-foreground text-sm">Review of all strategy implementations and filtered signals.</p>
      </div>

      <Card className="border-border">
        <CardHeader className="border-b border-border/50">
          <CardTitle className="text-sm font-mono uppercase tracking-widest text-muted-foreground">Historical Records</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {trades.length === 0 ? (
            <div className="p-20 text-center">
              <p className="text-muted-foreground font-mono text-xs uppercase tracking-widest">No execution records found.</p>
            </div>
          ) : (
            <Table>
              <TableHeader className="bg-secondary/30 font-mono">
                <TableRow>
                  <TableHead className="text-[10px] uppercase">Timestamp</TableHead>
                  <TableHead className="text-[10px] uppercase">Symbol</TableHead>
                  <TableHead className="text-[10px] uppercase">Regime / Strategy</TableHead>
                  <TableHead className="text-[10px] uppercase">Entry/Exit</TableHead>
                  <TableHead className="text-[10px] uppercase text-right">PnL</TableHead>
                  <TableHead className="text-[10px] uppercase text-right">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trades.map((trade) => (
                  <TableRow key={trade.id} className="font-mono text-xs">
                    <TableCell className="text-muted-foreground">
                      {new Date(trade.createdAt).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="font-bold tracking-tighter">
                      {trade.symbol}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="text-[10px] text-muted-foreground">{trade.regime}</span>
                        <span className="font-medium">{trade.strategy}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      ${trade.entryPrice.toFixed(2)} / ${trade.exitPrice?.toFixed(2) || '---'}
                    </TableCell>
                    <TableCell className="text-right">
                      {getPnlDisplay(trade.pnl)}
                    </TableCell>
                    <TableCell className="text-right">
                      {getStatusBadge(trade.status)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <div className="pt-10 text-center">
        <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-[0.15em] leading-relaxed max-w-xl mx-auto">
          "The best trades are the ones you didn't take because they didn't meet your criteria.
          Execution logs show profit, but your filtered signals show discipline."
        </p>
      </div>
    </div>
  );
}
