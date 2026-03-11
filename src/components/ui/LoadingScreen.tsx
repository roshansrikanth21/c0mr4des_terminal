import React, { useEffect, useState } from 'react';
import { Shield, Activity, Cpu, Wifi, Terminal } from 'lucide-react';
import { cn } from '@/lib/utils';

interface LoadingScreenProps {
    progress?: number;
    status?: string;
}

export function LoadingScreen({ progress = 0, status = "Initializing..." }: LoadingScreenProps) {
    const [logs, setLogs] = useState<string[]>([]);
    const [glitchTitle, setGlitchTitle] = useState(false);

    useEffect(() => {
        const messages = [
            "0x7F4A [Handshake established]",
            "0x8B2C [Decrypting neural feed]",
            "0x9D1E [Calibrating alpha weights]",
            "0xA2F0 [Syncing institutional flow]",
            "0xB5C1 [System online]"
        ];

        let i = 0;
        const interval = setInterval(() => {
            if (i < messages.length) {
                setLogs(prev => [...prev, messages[i]].slice(-5));
                i++;
            }
        }, 500);

        const glitchInterval = setInterval(() => {
            setGlitchTitle(true);
            setTimeout(() => setGlitchTitle(false), 200);
        }, 3000);

        return () => {
            clearInterval(interval);
            clearInterval(glitchInterval);
        };
    }, []);

    // Generate segments for the cyberpunk progress bar (20 segments)
    const segments = Array.from({ length: 20 }, (_, i) => i);
    const completedSegments = Math.floor((progress / 100) * 20);

    return (
        <div className="fixed inset-0 z-[100] bg-[#050505] flex flex-col items-center justify-center p-4 overflow-hidden font-mono">
            {/* Scanline Overlay */}
            <div className="absolute inset-0 pointer-events-none z-[110] opacity-[0.03] bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%),linear-gradient(90deg,rgba(255,0,0,0.06),rgba(0,255,0,0.02),rgba(0,0,255,0.06))] bg-[length:100%_2px,3px_100%]"></div>
            <div className="scanline"></div>

            <div className="w-full max-w-lg space-y-12 relative z-[120]">

                {/* Logo / Header with Glitch */}
                <div className="text-center space-y-6">
                    <div className="relative inline-block group">
                        <div className="absolute -inset-4 bg-primary/10 blur-2xl rounded-full group-hover:bg-primary/20 transition-all duration-500 animate-pulse"></div>
                        <Shield className={cn(
                            "w-20 h-20 text-primary mx-auto relative transition-all duration-75",
                            glitchTitle && "translate-x-1 skew-x-12 opacity-50"
                        )} />
                    </div>

                    <div className="space-y-2">
                        <h1
                            data-text="C0MR4DE TERMINAL"
                            className={cn(
                                "text-4xl font-black tracking-[0.25em] uppercase text-primary transform transition-all",
                                glitchTitle ? "glitch-text scale-105" : ""
                            )}
                        >
                            C0MR4DE TERMINAL
                        </h1>
                        <div className="flex items-center justify-center gap-4 text-[10px] text-muted-foreground/60 tracking-[0.3em] uppercase">
                            <span className="w-8 h-[1px] bg-muted-foreground/20"></span>
                            Neural Intelligence Terminal
                            <span className="w-8 h-[1px] bg-muted-foreground/20"></span>
                        </div>
                    </div>
                </div>

                {/* Cyberpunk Segmented Progress Bar */}
                <div className="space-y-4 px-4">
                    <div className="flex justify-between items-end text-[10px] uppercase tracking-widest leading-none">
                        <div className="space-y-1">
                            <div className="text-muted-foreground/40 font-bold">System Status</div>
                            <div className="flex items-center gap-2 text-primary">
                                <Activity className="w-3 h-3 animate-pulse" />
                                <span className="font-bold">{status}</span>
                            </div>
                        </div>
                        <div className="text-right">
                            <div className="text-muted-foreground/40 font-bold">Sync Progress</div>
                            <div className="text-lg font-black text-primary italic">{progress}%</div>
                        </div>
                    </div>

                    <div className="flex gap-1.5 h-4 w-full">
                        {segments.map((seg) => (
                            <div
                                key={seg}
                                className={cn(
                                    "flex-1 skew-x-[-20deg] border transition-all duration-300",
                                    seg < completedSegments
                                        ? "bg-primary border-primary shadow-[0_0_10px_rgba(var(--primary),0.5)]"
                                        : "bg-primary/5 border-primary/20"
                                )}
                            />
                        ))}
                    </div>
                </div>

                {/* Matrix-style Console Logs */}
                <div className="mx-4 relative">
                    <div className="absolute -inset-0.5 bg-gradient-to-b from-primary/20 to-transparent blur opacity-20"></div>
                    <div className="relative bg-black/60 border border-primary/20 p-6 rounded-sm shadow-2xl backdrop-blur-md overflow-hidden min-h-[160px] flex flex-col justify-end">
                        <div className="absolute top-2 right-3 text-[10px] text-primary/30 uppercase tracking-tighter">Log_Buffer_A1</div>
                        <div className="space-y-2.5">
                            {logs.map((log, idx) => (
                                <div key={idx} className="text-[12px] flex gap-3 items-center">
                                    <span className="text-primary/30 text-[10px] font-bold">[{idx.toString().padStart(2, '0')}]</span>
                                    <span className="text-green-500/80 font-bold tracking-tight">{log}</span>
                                </div>
                            ))}
                            <div className="text-primary animate-pulse mt-2 flex items-center gap-2">
                                <span className="w-1.5 h-3 bg-primary shadow-[0_0_8px_rgba(var(--primary),1)]"></span>
                                <span className="text-[11px] font-bold opacity-60">AWAITING_DATA_BUNDLE_SYNC...</span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Advanced Footer Stats */}
                <div className="flex justify-center gap-10 opacity-40">
                    <div className="flex flex-col items-center gap-1 group cursor-default">
                        <Wifi className="w-4 h-4 group-hover:text-primary transition-colors" />
                        <span className="text-[8px] uppercase tracking-[0.2em] font-black">Secure_Link</span>
                    </div>
                    <div className="flex flex-col items-center gap-1 group cursor-default">
                        <Cpu className="w-4 h-4 group-hover:text-primary transition-colors" />
                        <span className="text-[8px] uppercase tracking-[0.2em] font-black">Neural_Core</span>
                    </div>
                    <div className="flex flex-col items-center gap-1 group cursor-default">
                        <Terminal className="w-4 h-4 group-hover:text-primary transition-colors" />
                        <span className="text-[8px] uppercase tracking-[0.2em] font-black">GDFL_Verified</span>
                    </div>
                </div>

            </div>
        </div>
    );
}
