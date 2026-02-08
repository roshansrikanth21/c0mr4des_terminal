
import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Brain, ThumbsUp, ThumbsDown, Activity } from 'lucide-react';

interface BayesianMetrics {
    win_rate: {
        mean: number;
        credible_interval_95: [number, number];
    };
    probabilities: {
        profitable: number;
    };
    recommendation: {
        action: string;
        message: string;
        risk_level: string;
    };
}

interface BayesianStrategyCardProps {
    metrics?: BayesianMetrics;
    isLoading: boolean;
}

export function BayesianStrategyCard({ metrics, isLoading }: BayesianStrategyCardProps) {
    if (isLoading || !metrics) {
        return (
            <Card className="border border-border/50">
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-mono uppercase text-muted-foreground">Strategy AI</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="h-24 animate-pulse bg-secondary/50 rounded-md" />
                </CardContent>
            </Card>
        );
    }

    const winRate = metrics.win_rate.mean * 100;
    const confidence = metrics.probabilities.profitable * 100;
    const action = metrics.recommendation.action;

    return (
        <Card className="border border-border/50 bg-card/50">
            <CardHeader className="pb-2 border-b border-border/30">
                <div className="flex justify-between items-center">
                    <CardTitle className="text-sm font-mono uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                        <Brain className="w-4 h-4" />
                        Bayesian Optimizer
                    </CardTitle>
                    <Badge variant={action === "INCREASE_SIZE" ? "default" : "secondary"} className="text-[10px]">
                        {action.replace('_', ' ')}
                    </Badge>
                </div>
            </CardHeader>
            <CardContent className="pt-4 space-y-4">
                {/* Win Rate */}
                <div className="flex items-center justify-between">
                    <div>
                        <div className="text-[10px] uppercase font-mono text-muted-foreground">Calibrated Win Rate</div>
                        <div className="text-2xl font-bold font-mono text-primary">{winRate.toFixed(1)}%</div>
                        <div className="text-[9px] text-muted-foreground">
                            ± {((metrics.win_rate.credible_interval_95[1] - metrics.win_rate.mean) * 100).toFixed(1)}% (95% CI)
                        </div>
                    </div>
                    <Activity className="w-8 h-8 text-primary opacity-50" />
                </div>

                {/* Confidence Probability */}
                <div>
                    <div className="flex justify-between text-xs mb-1">
                        <span className="font-medium text-muted-foreground">Probability of Profit</span>
                        <span className="font-bold font-mono">{confidence.toFixed(0)}%</span>
                    </div>
                    <Progress value={confidence} className="h-1.5" />
                </div>

                <div className="bg-secondary/30 p-2 rounded text-[10px] font-mono border border-border/30">
                    {metrics.recommendation.message}
                </div>
            </CardContent>
        </Card>
    );
}
