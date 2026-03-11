import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Terminal, Activity, Zap, ShieldCheck, ShieldAlert, Clock, BarChart3, RefreshCw, Cpu, Server, Database } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Progress } from '@/components/ui/progress';

interface LogEntry {
    id: string;
    timestamp: string;
    method: string;
    path: string;
    status: number;
    duration: number;
}

interface MonitorStats {
    total_requests: number;
    success_count: number;
    error_count: number;
    avg_latency: number;
    uptime: string;
}

interface SystemHealth {
    api: string;
    monitor: string;
    gemini: string;
    market_data: string;
    timestamp: string;
}

interface DeepStatusData {
    news_engine?: {
        last_mode?: string;
        last_provider?: string;
        last_live_count?: number;
        last_duration_ms?: number;
        last_error?: string | null;
        cache_hit?: boolean;
        gemini_available?: boolean;
        gemini_disabled?: boolean;
    };
    market_providers?: {
        cache_entries?: number;
        inflight_requests?: number;
        providers?: Array<{
            provider: string;
            connected?: boolean;
        }>;
    };
    chart_analyzer?: {
        total_requests?: number;
        success_count?: number;
        failure_count?: number;
        last_model?: string | null;
        last_duration_ms?: number;
        last_error?: string | null;
        last_files_count?: number;
    };
    fusion_engine?: {
        fusion_weights?: {
            strategy?: number;
            ml_confirmation?: number;
            regime?: number;
            quant?: number;
            news?: number;
            risk_penalty?: number;
        };
        ml_confirmation_model?: {
            available?: boolean;
            reason?: string;
        };
        news_event_study?: {
            available?: boolean;
        };
        execution_quality?: {
            available?: boolean;
            summary?: {
                summary?: {
                    quality_score?: number;
                    reject_rate?: number;
                };
            };
        };
    };
    prewarm?: {
        status?: string;
        last_started_at?: string | null;
        last_completed_at?: string | null;
        tickers?: string[];
        last_error?: string | null;
    };
    routing?: {
        recommended_execution_broker?: {
            broker?: string;
            recommendation?: string;
            score?: number;
        };
        recommended_market_data_provider?: {
            provider?: string;
            recommendation?: string;
            route_score?: number;
        };
    };
    ops?: {
        config?: {
            manual_safety_lock?: boolean;
            auto_broker_switch_enabled?: boolean;
        };
    };
    execution_models?: {
        model_count?: number;
        updated_at?: string | null;
    };
    memory_engine?: {
        active_memories?: number;
        expired_memories?: number;
    };
    request_coordinator?: {
        inflight?: number;
        cached?: number;
    };
}

export function SystemMonitor() {
    const [history, setHistory] = useState<LogEntry[]>([]);
    const [stats, setStats] = useState<MonitorStats | null>(null);
    const [health, setHealth] = useState<SystemHealth | null>(null);
    const [deepStatus, setDeepStatus] = useState<DeepStatusData | null>(null);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [bootLogs, setBootLogs] = useState<string[]>([]);
    const [isBooted, setIsBooted] = useState(false);

    const logContainerRef = useRef<HTMLDivElement>(null);

    // Terminal Boot Sequence Effect
    useEffect(() => {
        const logs = [
            "Initializing C0MR4DE TERMINAL Neural Core...",
            "Establishing secure proxy gateway on port 8000...",
            "Checking Gemini-2.0-Flash availability...",
            "Warming up XGBoost ensemble models...",
            "Connecting to Global News Satellites...",
            "System Link: STABLE",
            "Neural Core: READY"
        ];

        let current = 0;
        const interval = setInterval(() => {
            if (current < logs.length) {
                setBootLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${logs[current]}`]);
                current++;
            } else {
                clearInterval(interval);
                setTimeout(() => setIsBooted(true), 1000);
            }
        }, 400);

        return () => clearInterval(interval);
    }, []);

    const fetchMetrics = async () => {
        setIsRefreshing(true);
        try {
            // Fetch Request Metrics
            const metricsRes = await fetch('/api/monitor/requests');
            const metricsData = await metricsRes.json();
            if (metricsData.status === 'success') {
                setHistory(metricsData.history);
                setStats(metricsData.stats);
            }

            // Fetch System Health
            const healthRes = await fetch('/api/system/status');
            const healthData = await healthRes.json();
            if (healthData.status === 'success') {
                setHealth(healthData.data);
            }

            const deepRes = await fetch('/api/system/deep_status');
            const deepData = await deepRes.json();
            if (deepData.status === 'success') {
                setDeepStatus(deepData.data);
            }
        } catch (error) {
            console.error("Monitor Fetch Error:", error);
            setBootLogs(prev => [...prev, `[ERROR] Link Failure: Backend unreachable at ${new Date().toLocaleTimeString()}`]);
        } finally {
            setIsRefreshing(false);
        }
    };

    useEffect(() => {
        if (isBooted) {
            fetchMetrics();
            const interval = setInterval(fetchMetrics, 3000); // Poll every 3s
            return () => clearInterval(interval);
        }
    }, [isBooted]);

    // Auto-scroll logic for boot logs
    useEffect(() => {
        if (logContainerRef.current) {
            logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }
    }, [bootLogs]);

    const getStatusColor = (status: number) => {
        if (status >= 500) return "text-red-500 bg-red-500/10 border-red-500/20";
        if (status >= 400) return "text-orange-500 bg-orange-500/10 border-orange-500/20";
        return "text-green-500 bg-green-500/10 border-green-500/20";
    };

    const getLatencyColor = (ms: number) => {
        if (ms > 1000) return "text-red-400";
        if (ms > 300) return "text-orange-400";
        return "text-green-400";
    };

    const connectedProviders = (deepStatus?.market_providers?.providers || []).filter(p => p.connected).length;
    const providerCount = (deepStatus?.market_providers?.providers || []).length;

    if (!isBooted) {
        return (
            <Card className="h-full border border-border/40 bg-black backdrop-blur-md flex flex-col font-mono text-[11px] overflow-hidden">
                <CardHeader className="p-4 border-b border-white/10 flex flex-row items-center justify-between">
                    <div className="flex items-center gap-3">
                        <Terminal className="w-4 h-4 text-primary animate-pulse" />
                        <CardTitle className="text-xs tracking-widest uppercase font-black text-white">Neural Core Bootloader</CardTitle>
                    </div>
                </CardHeader>
                <CardContent className="p-4 flex-1 bg-black text-primary overflow-y-auto" ref={logContainerRef}>
                    {bootLogs.map((log, i) => (
                        <div key={i} className="mb-1">{log}</div>
                    ))}
                    <div className="animate-pulse">_</div>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="h-full border border-border/40 bg-black/40 backdrop-blur-md flex flex-col font-mono text-[11px] overflow-hidden">
            <CardHeader className="p-4 border-b border-white/5 bg-white/5 flex flex-row items-center justify-between space-y-0">
                <div className="flex items-center gap-3">
                    <Terminal className="w-4 h-4 text-primary" />
                    <div>
                        <CardTitle className="text-xs tracking-widest uppercase font-black text-white">System Request Monitor</CardTitle>
                        <CardDescription className="text-[9px] opacity-60">Real-time Backend Ops Logs</CardDescription>
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-3 mr-2">
                        <div className="flex flex-col items-center gap-0.5" title="API Status">
                            <Server className={cn("w-3 h-3", health?.api === 'ONLINE' ? 'text-green-500' : 'text-red-500')} />
                            <span className="text-[7px]">API</span>
                        </div>
                        <div className="flex flex-col items-center gap-0.5" title="Gemini Connectivity">
                            <Cpu className={cn("w-3 h-3", health?.gemini === 'CONNECTED' ? 'text-primary' : 'text-orange-500')} />
                            <span className="text-[7px]">GEMINI</span>
                        </div>
                        <div className="flex flex-col items-center gap-0.5" title="Database Sync">
                            <Database className={cn("w-3 h-3", health?.market_data === 'SYNC_ACTIVE' ? 'text-green-500' : 'text-yellow-500')} />
                            <span className="text-[7px]">DATA</span>
                        </div>
                    </div>
                    <RefreshCw className={cn("w-3 h-3 opacity-40 cursor-pointer hover:opacity-100 transition-opacity", isRefreshing && "animate-spin")} onClick={fetchMetrics} />
                </div>
            </CardHeader>

            <CardContent className="p-0 flex-1 flex flex-col min-h-0">
                {/* Stats Bar */}
                <div className="grid grid-cols-4 border-b border-white/5 bg-white/5 divide-x divide-white/5">
                    <div className="p-3 space-y-1">
                        <div className="flex items-center gap-1 opacity-50 uppercase text-[9px]">
                            <Zap className="w-3 h-3" /> Req Total
                        </div>
                        <div className="text-sm font-bold text-white">{stats?.total_requests || 0}</div>
                    </div>
                    <div className="p-3 space-y-1">
                        <div className="flex items-center gap-1 opacity-50 uppercase text-[9px]">
                            <BarChart3 className="w-3 h-3" /> Success
                        </div>
                        <div className="text-sm font-bold text-green-500">{stats?.success_count || 0}</div>
                    </div>
                    <div className="p-3 space-y-1">
                        <div className="flex items-center gap-1 opacity-50 uppercase text-[9px]">
                            <ShieldAlert className="w-3 h-3" /> Errors
                        </div>
                        <div className="text-sm font-bold text-red-500">{stats?.error_count || 0}</div>
                    </div>
                    <div className="p-3 space-y-1">
                        <div className="flex items-center gap-1 opacity-50 uppercase text-[9px]">
                            <Clock className="w-3 h-3" /> Latency
                        </div>
                        <div className="text-sm font-bold text-primary">{stats?.avg_latency || 0} ms</div>
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-4 border-b border-white/5 bg-black/20 divide-y md:divide-y-0 md:divide-x divide-white/5">
                    <div className="p-3 space-y-1.5">
                        <div className="text-[9px] uppercase tracking-wider opacity-60">News Engine</div>
                        <div className="text-[11px]">
                            Mode: <span className="font-bold">{deepStatus?.news_engine?.last_mode || 'unknown'}</span>
                        </div>
                        <div className="text-[11px]">
                            Provider: <span className="font-bold">{deepStatus?.news_engine?.last_provider || 'none'}</span>
                        </div>
                        <div className="text-[11px]">
                            Cache: <span className="font-bold">{deepStatus?.news_engine?.cache_hit ? 'HIT' : 'MISS'}</span>
                        </div>
                        <div className="text-[11px]">
                            Headlines: <span className="font-bold">{deepStatus?.news_engine?.last_live_count ?? 0}</span>
                            {" | "}
                            {Math.round(deepStatus?.news_engine?.last_duration_ms || 0)} ms
                        </div>
                        {deepStatus?.news_engine?.last_error && (
                            <div className="text-[10px] text-orange-400 truncate" title={deepStatus.news_engine.last_error}>
                                Error: {deepStatus.news_engine.last_error}
                            </div>
                        )}
                    </div>

                    <div className="p-3 space-y-1.5">
                        <div className="text-[9px] uppercase tracking-wider opacity-60">Chart Analyzer</div>
                        <div className="text-[11px]">
                            Model: <span className="font-bold">{deepStatus?.chart_analyzer?.last_model || 'none'}</span>
                        </div>
                        <div className="text-[11px]">
                            Success/Fail: <span className="font-bold text-green-400">{deepStatus?.chart_analyzer?.success_count ?? 0}</span>
                            {" / "}
                            <span className="font-bold text-red-400">{deepStatus?.chart_analyzer?.failure_count ?? 0}</span>
                        </div>
                        <div className="text-[11px]">
                            Last: <span className="font-bold">{Math.round(deepStatus?.chart_analyzer?.last_duration_ms || 0)} ms</span>
                            {" | "}
                            files {deepStatus?.chart_analyzer?.last_files_count ?? 0}
                        </div>
                        {deepStatus?.chart_analyzer?.last_error && (
                            <div className="text-[10px] text-orange-400 truncate" title={deepStatus.chart_analyzer.last_error}>
                                Error: {deepStatus.chart_analyzer.last_error}
                            </div>
                        )}
                    </div>

                    <div className="p-3 space-y-1.5">
                        <div className="text-[9px] uppercase tracking-wider opacity-60">Data Providers</div>
                        <div className="text-[11px]">
                            Connected: <span className="font-bold">{connectedProviders}/{providerCount}</span>
                        </div>
                        <div className="text-[11px]">
                            Cache: <span className="font-bold">{deepStatus?.market_providers?.cache_entries ?? 0}</span>
                            {" | "}
                            Inflight: <span className="font-bold">{deepStatus?.market_providers?.inflight_requests ?? 0}</span>
                        </div>
                        <div className="text-[11px] truncate">
                            {((deepStatus?.market_providers?.providers || []).map(p => `${p.provider}:${p.connected ? 'UP' : 'CFG'}`)).join(' | ') || 'No providers'}
                        </div>
                    </div>

                    <div className="p-3 space-y-1.5">
                        <div className="text-[9px] uppercase tracking-wider opacity-60">Fusion Core</div>
                        <div className="text-[11px]">
                            ML: <span className="font-bold">{deepStatus?.fusion_engine?.ml_confirmation_model?.available ? 'TRAINED' : 'OFFLINE'}</span>
                        </div>
                        <div className="text-[11px]">
                            NewsCal: <span className="font-bold">{deepStatus?.fusion_engine?.news_event_study?.available ? 'READY' : 'MISSING'}</span>
                        </div>
                        <div className="text-[11px]">
                            ExecQ: <span className="font-bold">
                                {Math.round((((deepStatus?.fusion_engine?.execution_quality?.summary || {}).summary || {}).quality_score || 0) * 100)}
                            </span>
                            {" | "}
                            Rejects: <span className="font-bold">
                                {(((deepStatus?.fusion_engine?.execution_quality?.summary || {}).summary || {}).reject_rate ?? 0).toFixed?.(1) ?? '0.0'}%
                            </span>
                        </div>
                        <div className="text-[11px]">
                            W: <span className="font-bold">
                                S{deepStatus?.fusion_engine?.fusion_weights?.strategy?.toFixed?.(2) ?? '0.00'}
                                {' / '}
                                M{deepStatus?.fusion_engine?.fusion_weights?.ml_confirmation?.toFixed?.(2) ?? '0.00'}
                                {' / '}
                                N{deepStatus?.fusion_engine?.fusion_weights?.news?.toFixed?.(2) ?? '0.00'}
                            </span>
                        </div>
                        <div className="text-[11px]">
                            Prewarm: <span className="font-bold">{deepStatus?.prewarm?.status || 'idle'}</span>
                        </div>
                        <div className="text-[11px] truncate">
                            Route: <span className="font-bold">
                                {(deepStatus?.routing?.recommended_execution_broker?.broker || 'n/a')} / {(deepStatus?.routing?.recommended_market_data_provider?.provider || 'n/a')}
                            </span>
                        </div>
                        <div className="text-[11px] truncate">
                            Ops: <span className="font-bold">
                                {deepStatus?.ops?.config?.manual_safety_lock ? 'LOCKED' : 'OPEN'}
                                {' / '}
                                {deepStatus?.ops?.config?.auto_broker_switch_enabled ? 'AUTO' : 'MANUAL'}
                            </span>
                        </div>
                        <div className="text-[11px] truncate">
                            ExecModels: <span className="font-bold">{deepStatus?.execution_models?.model_count ?? 0}</span>
                        </div>
                        <div className="text-[11px] truncate">
                            Mem: <span className="font-bold">
                                A{deepStatus?.memory_engine?.active_memories ?? 0} / X{deepStatus?.memory_engine?.expired_memories ?? 0}
                            </span>
                        </div>
                        <div className="text-[11px] truncate">
                            Coord: <span className="font-bold">
                                I{deepStatus?.request_coordinator?.inflight ?? 0} / C{deepStatus?.request_coordinator?.cached ?? 0}
                            </span>
                        </div>
                        <div className="text-[11px] truncate">
                            {(deepStatus?.prewarm?.tickers || []).join(', ') || 'No warm targets'}
                        </div>
                    </div>
                </div>

                {/* Log Feed */}
                <div className="flex-1 overflow-y-auto custom-scrollbar">
                    <table className="w-full text-left border-collapse">
                        <thead className="sticky top-0 bg-black/80 backdrop-blur z-10 text-white/40 uppercase text-[9px] border-b border-white/5">
                            <tr>
                                <th className="p-2 pl-4 font-normal">Timestamp</th>
                                <th className="p-2 font-normal text-center">Method</th>
                                <th className="p-2 font-normal">Endpoint</th>
                                <th className="p-2 font-normal text-center">Status</th>
                                <th className="p-2 pr-4 font-normal text-right">Latency</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                            {history.map((log) => (
                                <tr key={log.id} className="hover:bg-white/5 transition-colors group">
                                    <td className="p-2 pl-4 text-white/40 whitespace-nowrap">
                                        {new Date(log.timestamp).toLocaleTimeString()}
                                    </td>
                                    <td className="p-2 text-center">
                                        <Badge variant="outline" className="text-[9px] py-0 px-1 border-white/20 text-white/60">
                                            {log.method}
                                        </Badge>
                                    </td>
                                    <td className="p-2 font-bold text-white/90 max-w-[150px] truncate">
                                        {log.path}
                                    </td>
                                    <td className="p-2 text-center">
                                        <span className={cn("inline-block px-2 py-0.5 rounded text-[9px] font-black border", getStatusColor(log.status))}>
                                            {log.status}
                                        </span>
                                    </td>
                                    <td className={cn("p-2 pr-4 text-right font-bold", getLatencyColor(log.duration))}>
                                        {log.duration.toFixed(0)} ms
                                    </td>
                                </tr>
                            ))}
                            {history.length === 0 && (
                                <tr>
                                    <td colSpan={5} className="p-8 text-center text-white/20 italic tracking-widest uppercase">
                                        Awaiting Traffic Discovery...
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </CardContent>
        </Card>
    );
}
