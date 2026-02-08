
import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Sigma } from 'lucide-react';

interface Greeks {
    delta: number;
    gamma: number;
    theta: number;
    vega: number;
}

interface OptionStrike {
    strike: number;
    call: {
        price: number;
        oi: number;
        greeks: Greeks;
    };
    put: {
        price: number;
        oi: number;
        greeks: Greeks;
    };
}

interface OptionGreeksTableProps {
    data: OptionStrike[];
    spotPrice: number;
    expiry: string;
    isLoading: boolean;
}

export function OptionGreeksTable({ data, spotPrice, expiry, isLoading }: OptionGreeksTableProps) {
    if (isLoading) {
        return (
            <Card className="border border-border/50">
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-mono uppercase text-muted-foreground">Option Matrix</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="h-48 animate-pulse bg-secondary/50 rounded-md" />
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="border border-border/50 bg-card/50">
            <CardHeader className="pb-2 border-b border-border/30">
                <div className="flex justify-between items-center">
                    <CardTitle className="text-sm font-mono uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                        <Sigma className="w-4 h-4" />
                        Greeks Matrix ({expiry})
                    </CardTitle>
                    <div className="text-xs font-mono">
                        Spot: <span className="font-bold text-primary">{spotPrice}</span>
                    </div>
                </div>
            </CardHeader>
            <CardContent className="p-0">
                <Table>
                    <TableHeader>
                        <TableRow className="text-[10px] uppercase hover:bg-transparent">
                            <TableHead className="w-[50px] text-center">Delta</TableHead>
                            <TableHead className="w-[50px] text-center">Theta</TableHead>
                            <TableHead className="text-center font-bold text-primary">Strike</TableHead>
                            <TableHead className="w-[50px] text-center">Theta</TableHead>
                            <TableHead className="w-[50px] text-center">Delta</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {data.map((row) => (
                            <TableRow key={row.strike} className={`text-xs font-mono hover:bg-muted/50 ${Math.abs(row.strike - spotPrice) < 50 ? "bg-primary/5" : ""}`}>
                                {/* Call Side */}
                                <TableCell className="text-center text-green-500">{row.call.greeks.delta.toFixed(2)}</TableCell>
                                <TableCell className="text-center text-destructive">{row.call.greeks.theta.toFixed(1)}</TableCell>

                                {/* Strike */}
                                <TableCell className="text-center font-bold border-x border-border/50 bg-card">
                                    {row.strike}
                                </TableCell>

                                {/* Put Side */}
                                <TableCell className="text-center text-destructive">{row.put.greeks.theta.toFixed(1)}</TableCell>
                                <TableCell className="text-center text-red-500">{row.put.greeks.delta.toFixed(2)}</TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </CardContent>
        </Card>
    );
}
