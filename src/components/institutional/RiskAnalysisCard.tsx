
import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { AlertTriangle, TrendingDown, Target } from 'lucide-react';
import { formatCurrency } from '@/lib/market-config';

interface RiskMetrics {
    risk_metrics: {
        var_percent: number;
        es_percent: number;
        confidence_level: number;
    }
}

interface RiskAnalysisCardProps {
    metrics?: RiskMetrics;
    isLoading: boolean;
}

export function RiskAnalysisCard({ metrics, isLoading }: RiskAnalysisCardProps) {
    if (isLoading) {
        return (
            <Card className="border border-border/50">
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-mono uppercase text-muted-foreground">Risk Analysis</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="h-24 animate-pulse bg-secondary/50 rounded-md" />
                </CardContent>
            </Card>
        );
    }

    const varVal = metrics?.risk_metrics?.var_percent || 0;
    const esVal = metrics?.risk_metrics?.es_percent || 0;

    // Risk Level Logic
    let riskLevel = "LOW";
    let riskColor = "bg-green-500";

    if (Math.abs(varVal) > 3) {
        riskLevel = "HIGH";
        riskColor = "bg-destructive";
    } else if (Math.abs(varVal) > 1.5) {
        riskLevel = "MEDIUM";
        riskColor = "bg-yellow-500";
    }

    return (
        <Card className="border border-border/50 bg-card/50">
            <CardHeader className="pb-2 border-b border-border/30">
                <div className="flex justify-between items-center">
                    <CardTitle className="text-sm font-mono uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                        <AlertTriangle className="w-4 h-4" />
                        Monte Carlo Risk
                    </CardTitle>
                    <Badge variant="outline" className={`${riskColor} bg-opacity-10 text-xs border-0`}>
                        {riskLevel}
                    </Badge>
                </div>
            </CardHeader>
            <CardContent className="pt-4 space-y-4">
                {/* Value at Risk */}
                <div>
                    <div className="flex justify-between text-xs mb-1">
                        <span className="font-medium text-muted-foreground">95% Value at Risk (VaR)</span>
                        <span className="font-bold font-mono text-destructive">{varVal.toFixed(2)}%</span>
                    </div>
                    <Progress value={Math.min(Math.abs(varVal) * 20, 100)} className="h-1.5" />
                    <p className="text-[10px] text-muted-foreground mt-1 text-right">
                        Max potential loss in 1 day (95% conf.)
                    </p>
                </div>

                {/* Expected Shortfall */}
                <div className="bg-secondary/30 p-2 rounded border border-border/30 flex items-center gap-3">
                    <TrendingDown className="w-8 h-8 text-destructive opacity-80" />
                    <div>
                        <div className="text-[10px] uppercase font-mono text-muted-foreground">Expected Shortfall</div>
                        <div className="text-lg font-bold font-mono text-destructive">{esVal.toFixed(2)}%</div>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
