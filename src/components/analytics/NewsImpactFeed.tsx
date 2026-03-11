import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Globe, AlertTriangle, TrendingDown, TrendingUp, Cpu, Flame, ExternalLink, Activity, Terminal } from 'lucide-react';
import { Progress } from '@/components/ui/progress';
import { formatDistanceToNow } from 'date-fns';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

interface NewsItem {
    title: string;
    source: string;
    published_at: string;
    url: string;
    assistant_insight?: string;
    nlp_metrics: {
        vader_compound: number;
        textblob_polarity: number;
        keyword_severity: number;
    };
    ml_votes: {
        xgboost_score: number;
        linear_reg_score: number;
    };
    affect_rate: number;
    market_direction: string;
}

function formatPublishedTime(value?: string): string {
    if (!value) return 'time unknown';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return 'time unknown';
    return `${formatDistanceToNow(parsed)} ago`;
}

export function NewsImpactFeed() {
    const [news, setNews] = useState<NewsItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [loadingMessage, setLoadingMessage] = useState('Initializing neural core...');
    const [error, setError] = useState<string | null>(null);

    const fetchNewsImpact = async () => {
        try {
            setLoading(true);
            setLoadingMessage('Contacting global news satellites...');

            const statusTimer = setTimeout(() => setLoadingMessage('Synchronizing with geopolitical ML model...'), 1500);
            const assistantTimer = setTimeout(() => setLoadingMessage('Running Gemini-2.0 impact analysis...'), 3500);

            const response = await fetch('/api/news/impact');
            const data = await response.json();

            clearTimeout(statusTimer);
            clearTimeout(assistantTimer);

            if (data.status === 'success') {
                setNews(data.data);
                setError(null);
            } else if (data.status === 'error') {
                setError(data.message || 'Failed to sync feed');
                toast.error('Intelligence synchronization offline', {
                    description: data.suggestion || 'Backend engine reported a structural error.'
                });
            }
        } catch (err) {
            console.error('Fetch error:', err);
            setError('Connection timeout or server unreachable');
            toast.error('Signal Interrupted', {
                description: 'Global intelligence feed is unreachable.'
            });
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchNewsImpact();
        const interval = setInterval(fetchNewsImpact, 300000); // 5 mins
        return () => clearInterval(interval);
    }, []);

    const getImpactColor = (rate: number) => {
        if (rate >= 80) return "text-red-500 bg-red-500/10 border-red-500/30";
        if (rate >= 50) return "text-orange-500 bg-orange-500/10 border-orange-500/30";
        if (rate >= 20) return "text-yellow-500 bg-yellow-500/10 border-yellow-500/30";
        return "text-green-500 bg-green-500/10 border-green-500/30";
    };

    const getProgressColor = (rate: number) => {
        if (rate >= 80) return "bg-red-500";
        if (rate >= 50) return "bg-orange-500";
        if (rate >= 20) return "bg-yellow-500";
        return "bg-green-500";
    };

    return (
        <Card className="h-full border border-border/40 bg-card/40 backdrop-blur-sm overflow-hidden flex flex-col">
            <CardHeader className="pb-3 border-b border-border/30 bg-primary/5">
                <div className="flex items-center justify-between">
                    <div className="space-y-1">
                        <CardTitle className="text-sm font-mono font-bold uppercase tracking-[0.2em] flex items-center gap-2 text-primary">
                            <Globe className="w-4 h-4" />
                            Global Intelligence Feed
                        </CardTitle>
                        <CardDescription className="text-xs font-mono opacity-60">
                            Real-time ML Ensemble Sentiment & Impact Analysis
                        </CardDescription>
                    </div>
                    <Badge variant="outline" className={cn("bg-primary/10 text-primary border-primary/20", loading && "animate-pulse")}>
                        <Activity className="w-3 h-3 mr-1" />
                        {loading ? "SYNCING..." : "LIVE SYNC"}
                    </Badge>
                </div>
            </CardHeader>

            <CardContent className="p-0 overflow-y-auto custom-scrollbar flex-1">
                {loading ? (
                    <div className="p-4 space-y-4">
                        <div className="flex items-center gap-2 mb-2 text-[10px] font-mono text-primary/60 animate-pulse">
                            <Terminal className="w-3 h-3" />
                            <span>{loadingMessage}</span>
                        </div>
                        {[1, 2, 3].map((i) => (
                            <div key={i} className="p-4 border border-border/20 rounded-lg bg-white/5 space-y-3">
                                <div className="flex justify-between items-start gap-4">
                                    <Skeleton className="h-4 w-[70%] bg-muted/20" />
                                    <Skeleton className="h-8 w-12 bg-muted/20 rounded border border-border/30" />
                                </div>
                                <Skeleton className="h-3 w-[40%] bg-muted/20" />
                                <div className="space-y-2 pt-2 border-t border-dashed border-border/20">
                                    <Skeleton className="h-3 w-4 bg-muted/20" />
                                    <Skeleton className="h-8 w-full bg-muted/20 rounded" />
                                </div>
                            </div>
                        ))}
                    </div>
                ) : error ? (
                    <div className="flex flex-col items-center justify-center p-8 text-center space-y-4">
                        <div className="p-3 rounded-full bg-destructive/10 border border-destructive/20">
                            <AlertTriangle className="w-6 h-6 text-destructive" />
                        </div>
                        <div className="space-y-1">
                            <h4 className="text-sm font-bold text-destructive uppercase tracking-widest font-mono">Signal Lost</h4>
                            <p className="text-xs text-muted-foreground font-mono max-w-[200px]">{error}</p>
                        </div>
                        <Button variant="outline" size="sm" onClick={fetchNewsImpact} className="font-mono text-[10px] h-8 border-destructive/30 hover:bg-destructive/5">
                            RETRY SYNCHRONIZATION
                        </Button>
                    </div>
                ) : news.length === 0 ? (
                    <div className="p-8 text-center text-muted-foreground font-mono text-xs">
                        No significant global events detected in current timeframe.
                    </div>
                ) : (
                    <div className="divide-y divide-border/20">
                        {news.map((item, idx) => (
                            <div key={idx} className="p-4 hover:bg-white/5 transition-colors space-y-3 group">
                                <div className="flex justify-between items-start gap-4">
                                    <h4 className="font-bold text-sm tracking-tight leading-snug group-hover:text-primary transition-colors flex-1">
                                        <a href={item.url} target="_blank" rel="noopener noreferrer" className="flex items-start gap-2">
                                            {item.title}
                                            <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity mt-1 shrink-0" />
                                        </a>
                                    </h4>
                                    <div className="text-right shrink-0">
                                        <div className={cn("px-2 py-1 rounded border font-mono text-xl font-black", getImpactColor(item.affect_rate))}>
                                            {item.affect_rate.toFixed(0)}
                                            <span className="text-[10px] ml-1 opacity-70">Impact</span>
                                        </div>
                                    </div>
                                </div>

                                <div className="flex items-center justify-between text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
                                    <span>{item.source} • {formatPublishedTime(item.published_at)}</span>
                                    <span className={cn("font-bold",
                                        item.market_direction === 'BEARISH' || item.market_direction === 'CRASH_WARNING' ? 'text-red-500' :
                                            item.market_direction === 'BULLISH' ? 'text-green-500' : 'text-gray-400'
                                    )}>{item.market_direction}</span>
                                </div>

                                {item.assistant_insight && (
                                    <div className="relative mt-2 p-3 bg-primary/5 border-l-2 border-primary/40 rounded-r-md">
                                        <div className="flex items-center gap-1.5 mb-1.5">
                                            <Cpu className="w-3 h-3 text-primary" />
                                            <span className="text-[9px] font-black uppercase tracking-tighter text-primary/80">Assistant Insight</span>
                                        </div>
                                        <p className="text-[11px] italic leading-relaxed text-foreground/90 font-medium font-serif">
                                            "{item.assistant_insight}"
                                        </p>
                                    </div>
                                )}

                                <div className="bg-secondary/20 rounded p-2 border border-border/30 space-y-2">
                                    <div className="flex justify-between text-[9px] font-mono opacity-70 uppercase tracking-tighter">
                                        <span className="flex items-center gap-1"><Cpu className="w-3 h-3" /> ML Ensemble Voting</span>
                                        <span>Confidence Matrix</span>
                                    </div>
                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="space-y-1">
                                            <div className="flex justify-between text-[8px] font-mono">
                                                <span>XGBoost</span>
                                                <span className="font-bold">{item.ml_votes.xgboost_score.toFixed(1)}</span>
                                            </div>
                                            <Progress value={item.ml_votes.xgboost_score} className="h-1 bg-border/40" indicatorClassName={getProgressColor(item.ml_votes.xgboost_score)} />
                                        </div>
                                        <div className="space-y-1">
                                            <div className="flex justify-between text-[8px] font-mono">
                                                <span>Linear Regression</span>
                                                <span className="font-bold">{item.ml_votes.linear_reg_score.toFixed(1)}</span>
                                            </div>
                                            <Progress value={item.ml_votes.linear_reg_score} className="h-1 bg-border/40" indicatorClassName={getProgressColor(item.ml_votes.linear_reg_score)} />
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
