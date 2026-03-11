import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useBroker } from "@/hooks/use-broker";
import { RefreshCw, Wallet, ShieldCheck, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";

export function BrokerStatus({ broker }: { broker: ReturnType<typeof useBroker> }) {
    const { status, portfolio, connect, refresh, loading } = broker;

    const isPaper = status.mode === 'PAPER';
    const isLive = status.mode === 'ANGEL_ONE';

    return (
        <Card className="w-full border-border/40 bg-card/50 backdrop-blur-sm">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <Wallet className="h-4 w-4 text-primary" />
                    Broker Connection
                </CardTitle>
                <div className="flex gap-2">
                    {status.connected ? (
                        <Badge variant={isPaper ? "secondary" : "destructive"} className="animate-pulse">
                            {isPaper ? "PAPER TRADING" : "LIVE: ANGEL ONE"}
                        </Badge>
                    ) : (
                        <Badge variant="outline" className="text-muted-foreground">DISCONNECTED</Badge>
                    )}
                </div>
            </CardHeader>
            <CardContent>
                {!status.connected ? (
                    <div className="flex gap-2 mt-2">
                        <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => connect('PAPER')}
                            disabled={loading}
                        >
                            <ShieldCheck className="h-4 w-4 mr-2" />
                            Connect Paper
                        </Button>
                        <Button
                            size="sm"
                            variant="destructive"
                            onClick={() => connect('ANGEL_ONE')}
                            disabled={loading}
                        >
                            <ShieldAlert className="h-4 w-4 mr-2" />
                            Connect Angel One
                        </Button>
                    </div>
                ) : (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-2">
                        <div>
                            <p className="text-xs text-muted-foreground">Balance</p>
                            <p className="text-lg font-bold">₹{status.balance?.toLocaleString()}</p>
                        </div>
                        <div>
                            <p className="text-xs text-muted-foreground">Unrealized P&L</p>
                            <p className={cn(
                                "text-lg font-bold",
                                (portfolio?.pnl || 0) >= 0 ? "text-green-500" : "text-red-500"
                            )}>
                                ₹{portfolio?.pnl?.toFixed(2) || '0.00'}
                            </p>
                        </div>
                        <div>
                            <p className="text-xs text-muted-foreground">Positions</p>
                            <p className="text-lg font-bold">{portfolio?.positions?.length || 0}</p>
                        </div>
                        <div className="flex justify-end items-center">
                            <Button size="icon" variant="ghost" onClick={refresh} title="Refresh Data">
                                <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
                            </Button>
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
