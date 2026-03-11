import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useBroker } from "@/hooks/use-broker";
import { Loader2, TrendingUp, TrendingDown } from "lucide-react";
import { toast } from "sonner";

export function OrderEntry({ broker, defaultSymbol }: { broker: ReturnType<typeof useBroker>, defaultSymbol?: string }) {
    const { placeOrder, loading, status } = broker;

    const [symbol, setSymbol] = useState(defaultSymbol || "SBIN-EQ");
    const [quantity, setQuantity] = useState(1);
    const [action, setAction] = useState<'BUY' | 'SELL'>('BUY');
    const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('MARKET');

    const handleSubmit = async () => {
        if (!status.connected) {
            toast.error("Broker not connected");
            return;
        }

        const res = await placeOrder({
            symbol: symbol.toUpperCase(),
            action,
            quantity,
            type: orderType
        });

        if (res.success) {
            toast.success(`Order Placed: ${action} ${quantity} ${symbol} @ ${orderType}`);
        } else {
            toast.error(`Order Failed: ${res.message}`);
        }
    };

    return (
        <Card className="w-full border-border/40 bg-card/50 backdrop-blur-sm">
            <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Quick Order Entry</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                        <Label>Symbol</Label>
                        <Input
                            value={symbol}
                            onChange={(e) => setSymbol(e.target.value)}
                            placeholder="e.g. SBIN-EQ"
                            className="uppercase"
                        />
                    </div>
                    <div className="space-y-2">
                        <Label>Quantity</Label>
                        <Input
                            type="number"
                            min={1}
                            value={quantity}
                            onChange={(e) => setQuantity(parseInt(e.target.value))}
                        />
                    </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                    <Button
                        variant={action === 'BUY' ? "default" : "outline"}
                        className={action === 'BUY' ? "bg-green-600 hover:bg-green-700" : ""}
                        onClick={() => setAction('BUY')}
                    >
                        <TrendingUp className="mr-2 h-4 w-4" /> BUY
                    </Button>
                    <Button
                        variant={action === 'SELL' ? "default" : "outline"}
                        className={action === 'SELL' ? "bg-red-600 hover:bg-red-700" : ""}
                        onClick={() => setAction('SELL')}
                    >
                        <TrendingDown className="mr-2 h-4 w-4" /> SELL
                    </Button>
                </div>

                <Button
                    className="w-full"
                    onClick={handleSubmit}
                    disabled={loading || !status.connected}
                >
                    {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : "Place Order"}
                </Button>
            </CardContent>
        </Card>
    );
}
