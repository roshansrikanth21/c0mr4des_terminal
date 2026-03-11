import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useBroker } from "@/hooks/use-broker";
import { cn } from "@/lib/utils";

export function PortfolioTable({ broker }: { broker: ReturnType<typeof useBroker> }) {
    const { portfolio } = broker;
    const positions = portfolio?.positions || [];

    if (positions.length === 0) {
        return (
            <Card className="w-full border-border/40 bg-card/50 backdrop-blur-sm">
                <CardHeader>
                    <CardTitle className="text-sm font-medium">Active Positions</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="text-center py-8 text-muted-foreground text-sm">
                        No open positions
                    </div>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="w-full border-border/40 bg-card/50 backdrop-blur-sm overflow-hidden">
            <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Active Positions ({positions.length})</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
                <Table>
                    <TableHeader>
                        <TableRow className="hover:bg-transparent">
                            <TableHead>Symbol</TableHead>
                            <TableHead className="text-right">Qty</TableHead>
                            <TableHead className="text-right">Avg</TableHead>
                            <TableHead className="text-right">LTP</TableHead>
                            <TableHead className="text-right">P&L</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {positions.map((pos, idx) => (
                            <TableRow key={idx} className="hover:bg-accent/50">
                                <TableCell className="font-medium">{pos.symbol}</TableCell>
                                <TableCell className="text-right">{pos.quantity}</TableCell>
                                <TableCell className="text-right">₹{(pos.avg_price || 0).toFixed(2)}</TableCell>
                                <TableCell className="text-right">₹{(pos.ltp || 0).toFixed(2)}</TableCell>
                                <TableCell className="text-right">
                                    <Badge variant="outline" className={cn(
                                        "bg-opacity-10 min-w-[80px] justify-center",
                                        (pos.pnl || 0) >= 0
                                            ? "bg-green-500 text-green-500 border-green-500/20"
                                            : "bg-red-500 text-red-500 border-red-500/20"
                                    )}>
                                        {(pos.pnl || 0) >= 0 ? "+" : ""}₹{(pos.pnl || 0).toFixed(2)}
                                    </Badge>
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </CardContent>
        </Card>
    );
}
