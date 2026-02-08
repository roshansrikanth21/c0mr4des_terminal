
import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Clock, Zap } from 'lucide-react';

interface TimingSignal {
    time: string;
    event: string;
    action: string;
    urgency: string;
    message: string;
}

interface MarketTimingCardProps {
    session?: string;
    nextEvent?: TimingSignal;
    isLoading: boolean;
}

export function MarketTimingCard({ session, nextEvent, isLoading }: MarketTimingCardProps) {
    if (isLoading) {
        return (
            <Card className="border border-border/50">
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-mono uppercase text-muted-foreground">Timing</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="h-24 animate-pulse bg-secondary/50 rounded-md" />
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="border border-border/50 bg-card/50 h-full">
            <CardHeader className="pb-2 border-b border-border/30">
                <div className="flex justify-between items-center">
                    <CardTitle className="text-sm font-mono uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                        <Clock className="w-4 h-4" />
                        Market Timing
                    </CardTitle>
                    <Badge variant="outline" className="text-[10px] font-mono">
                        {session || "CLOSED"}
                    </Badge>
                </div>
            </CardHeader>
            <CardContent className="pt-4 space-y-4">
                {nextEvent ? (
                    <div className="space-y-3">
                        <div className="flex items-center gap-2 text-primary">
                            <Zap className="w-4 h-4 animate-pulse" />
                            <span className="text-sm font-bold font-mono">{nextEvent.event}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                            <span className="text-muted-foreground">Action:</span>
                            <span className="font-bold">{nextEvent.action}</span>
                        </div>
                        <div className="bg-secondary/30 p-2 rounded text-[10px] border border-border/30 italic">
                            "{nextEvent.message}"
                        </div>
                    </div>
                ) : (
                    <div className="text-center py-8 text-muted-foreground text-xs italic">
                        No upcoming critical events.
                    </div>
                )}

                {/* Global Clocks (Small) */}
                <div className="flex justify-between pt-4 border-t border-border/30 mt-auto">
                    <div className="text-center">
                        <div className="text-[9px] text-muted-foreground uppercase">London</div>
                        <div className="text-[10px] font-mono font-bold">OPEN</div>
                    </div>
                    <div className="text-center">
                        <div className="text-[9px] text-muted-foreground uppercase">New York</div>
                        <div className="text-[10px] font-mono font-bold text-muted-foreground">CLOSED</div>
                    </div>
                    <div className="text-center">
                        <div className="text-[9px] text-muted-foreground uppercase">Tokyo</div>
                        <div className="text-[10px] font-mono font-bold text-muted-foreground">CLOSED</div>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
