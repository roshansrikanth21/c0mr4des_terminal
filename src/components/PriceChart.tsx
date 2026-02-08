import React, { useEffect, useState } from 'react';
import {
    ComposedChart,
    Line,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    ReferenceDot,
    ReferenceLine,
    Legend
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2 } from 'lucide-react';
import { formatCurrency, getMarketByRegion, MarketRegion } from '@/lib/market-config';

interface PricePoint {
    date: string;
    price: number;
    sma50: number | null;
    sma200: number | null;
    upper_bb: number | null;
    lower_bb: number | null;
    rsi: number;
    signal: 'ENTRY' | 'EXIT' | null;
    reason?: string;
    confidence?: number;
    stop_loss?: number;
    take_profit?: number;
}

interface PriceChartProps {
    ticker: string;
    region: MarketRegion;
}

const TIMEFRAMES = [
    { label: '1D (1m)', value: '1d', interval: '1m' },
    { label: '1W (5m)', value: '5d', interval: '5m' },
    { label: '1M (1h)', value: '1mo', interval: '1h' },
    { label: '3M (Daily)', value: '3mo', interval: '1d' },
    { label: '1Y (Daily)', value: '1y', interval: '1d' },
    { label: '5Y (Weekly)', value: '5y', interval: '1wk' },
];

export function PriceChart({ ticker, region }: PriceChartProps) {
    const [ictData, setIctData] = useState<any[]>([]);
    const [quantData, setQuantData] = useState<any>(null);
    const [data, setData] = useState<PricePoint[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [selectedTf, setSelectedTf] = useState(TIMEFRAMES[4]); // Default 1Y

    useEffect(() => {
        const fetchHistory = async () => {
            setIsLoading(true);
            setError(null);
            try {
                const encodedTicker = encodeURIComponent(ticker);
                const period = selectedTf.value;

                // Parallel Fetching
                const [histRes, ictRes, quantRes] = await Promise.all([
                    fetch(`http://localhost:8000/api/history?ticker=${encodedTicker}&period=${period}&interval=${selectedTf.interval}`),
                    fetch(`http://localhost:8000/api/ict_analysis?ticker=${encodedTicker}&period=${period}`),
                    fetch(`http://localhost:8000/api/quant_analysis?ticker=${encodedTicker}&period=1y`)
                ]);

                if (!histRes.ok) throw new Error('Failed to fetch history');

                const histJson = await histRes.json();
                setData(histJson);

                if (ictRes.ok) {
                    const ictJson = await ictRes.json();
                    if (ictJson.status === 'success') setIctData(ictJson.data);
                }

                if (quantRes.ok) {
                    const quantJson = await quantRes.json();
                    if (quantJson.status === 'success') setQuantData(quantJson.data);
                }

            } catch (err) {
                console.error(err);
                setError('Failed to load chart data');
            } finally {
                setIsLoading(false);
            }
        };

        fetchHistory();
    }, [ticker, selectedTf]);

    if (error) {
        return (
            <Card className="h-[450px] flex items-center justify-center text-destructive bg-destructive/10 border-destructive/20">
                <p>Error: {error}</p>
            </Card>
        );
    }

    if (isLoading && data.length === 0) {
        return (
            <Card className="h-[450px] flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-primary" />
                <span className="ml-2 text-muted-foreground">Loading Market Data...</span>
            </Card>
        );
    }

    // Filter signals for annotation
    const signals = data.filter(d => d.signal !== null);

    // Filter visible ICT elements
    const fvgBull = ictData.filter(i => i.type === 'FVG_BULL');
    const fvgBear = ictData.filter(i => i.type === 'FVG_BEAR');

    return (
        <Card className="border border-border shadow-sm">
            <CardHeader className="pb-2 border-b border-border/50 flex flex-row items-center justify-between">
                <div className="flex flex-col gap-1">
                    <CardTitle className="text-lg font-mono tracking-tight flex items-center gap-2">
                        Price Action & Signals
                        {quantData && (
                            <Badge variant="outline" className={
                                quantData.market_state === 'Defensive'
                                    ? "bg-red-500/10 text-red-500 border-red-500/20"
                                    : "bg-blue-500/10 text-blue-500 border-blue-500/20"
                            }>
                                {quantData.regime_cluster}
                            </Badge>
                        )}
                    </CardTitle>
                    <div className="flex gap-2">
                        <Badge variant="outline" className="text-[10px] bg-green-500/10 text-green-500 border-green-500/20">ENTRY</Badge>
                        <Badge variant="outline" className="text-[10px] bg-red-500/10 text-red-500 border-red-500/20">EXIT</Badge>
                        <Badge variant="outline" className="text-[10px] bg-emerald-500/10 text-emerald-500 border-emerald-500/20">FVG BULL</Badge>
                        <Badge variant="outline" className="text-[10px] bg-rose-500/10 text-rose-500 border-rose-500/20">FVG BEAR</Badge>
                    </div>
                </div>
                <div className="flex bg-secondary/50 rounded-md p-1 gap-1">
                    {TIMEFRAMES.map((tf) => (
                        <button
                            key={tf.label}
                            onClick={() => setSelectedTf(tf)}
                            className={`px-3 py-1 text-[10px] font-medium rounded-sm transition-all whitespace-nowrap ${selectedTf.label === tf.label
                                ? 'bg-background shadow-sm text-foreground'
                                : 'text-muted-foreground hover:text-foreground hover:bg-background/50'
                                }`}
                        >
                            {tf.label}
                        </button>
                    ))}
                </div>
            </CardHeader>
            <CardContent className="p-0 h-[400px] relative">
                {isLoading && (
                    <div className="absolute inset-0 bg-background/50 z-10 flex items-center justify-center backdrop-blur-[1px]">
                        <Loader2 className="w-8 h-8 animate-spin text-primary" />
                    </div>
                )}
                <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={data} margin={{ top: 20, right: 30, left: 0, bottom: 0 }}>
                        <defs>
                            <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.2} />
                                <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.4} />
                        <XAxis
                            dataKey="date"
                            tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                            tickFormatter={(val) => {
                                const d = new Date(val);
                                if (selectedTf.interval === '1m' || selectedTf.interval === '5m' || selectedTf.interval === '1h') {
                                    return `${d.getDate()}/${d.getMonth() + 1} ${d.getHours()}:${d.getMinutes() < 10 ? '0' : ''}${d.getMinutes()}`;
                                }
                                return `${d.getMonth() + 1}/${d.getDate()}`;
                            }}
                            minTickGap={30}
                        />
                        <YAxis
                            domain={['auto', 'auto']}
                            tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                            tickFormatter={(val) => formatCurrency(val, region).replace('₹', '').replace('$', '')}
                        />
                        <Tooltip
                            contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', fontSize: '12px' }}
                            itemStyle={{ color: 'hsl(var(--foreground))' }}
                            labelFormatter={(label) => new Date(label).toLocaleString()}
                            formatter={(value: number, name: string) => {
                                if (name === 'stop_loss') return [formatCurrency(value, region), 'Stop Loss'];
                                if (name === 'price') return [formatCurrency(value, region), 'Close Price'];
                                if (name === 'sma50' || name === 'sma200') return [formatCurrency(value, region), name.toUpperCase()];
                                return [value, name];
                            }}
                        />
                        <Legend verticalAlign="top" height={36} iconType="circle" wrapperStyle={{ fontSize: '10px' }} />

                        {/* Reference Areas for FVGs - Simplified rendering for performance */}
                        {/* Only draw last 50 FVGs to avoid DOM overload */}
                        {fvgBull.slice(-50).map((fvg, i) => (
                            <ReferenceLine
                                key={`fvg-b-${i}`}
                                y={fvg.bottom}
                                stroke="#10b981"
                                strokeDasharray="2 2"
                                strokeOpacity={0.5}
                                label={{ position: 'left', value: 'FVG', fill: '#10b981', fontSize: 8 }}
                            />
                        ))}

                        {fvgBear.slice(-50).map((fvg, i) => (
                            <ReferenceLine
                                key={`fvg-s-${i}`}
                                y={fvg.top}
                                stroke="#f43f5e"
                                strokeDasharray="2 2"
                                strokeOpacity={0.5}
                                label={{ position: 'left', value: 'FVG', fill: '#f43f5e', fontSize: 8 }}
                            />
                        ))}

                        <Area
                            dataKey="upper_bb"
                            stroke="transparent"
                            fill="hsl(var(--muted-foreground))"
                            fillOpacity={0.05}
                            name="Boll Upper"
                        />
                        <Area
                            dataKey="lower_bb"
                            stroke="transparent"
                            fill="hsl(var(--muted-foreground))"
                            fillOpacity={0.05}
                            name="Boll Lower"
                        />

                        <Area
                            type="monotone"
                            dataKey="price"
                            stroke="hsl(var(--primary))"
                            fillOpacity={1}
                            fill="url(#colorPrice)"
                            strokeWidth={2}
                            name="Price"
                            dot={false}
                        />

                        {/* Show SMAs only on daily/weekly charts to allow short-term clarity */}
                        {(selectedTf.interval === '1d' || selectedTf.interval === '1wk') && (
                            <>
                                <Line
                                    type="monotone"
                                    dataKey="sma50"
                                    stroke="#3b82f6"
                                    strokeWidth={1.5}
                                    dot={false}
                                    name="SMA 50"
                                />
                                <Line
                                    type="monotone"
                                    dataKey="sma200"
                                    stroke="#64748b"
                                    strokeWidth={1.5}
                                    strokeDasharray="5 5"
                                    dot={false}
                                    name="SMA 200"
                                />
                            </>
                        )}

                        {/* Render Signals as Reference Dots */}
                        {signals.map((s, i) => (
                            <ReferenceDot
                                key={i}
                                x={s.date}
                                y={s.price}
                                r={5}
                                fill={s.signal === 'ENTRY' ? '#22c55e' : '#ef4444'}
                                stroke="white"
                                strokeWidth={1}
                                ifOverflow="extendDomain"
                            />
                        ))}

                        {/* VISUAL TRADE GUIDES (Toddler-Proofing) */}
                        {data.length > 0 && data[data.length - 1].signal === 'ENTRY' && (
                            <>
                                {/* ENTRY LINE */}
                                <ReferenceLine
                                    y={data[data.length - 1].price}
                                    stroke="#22c55e"
                                    strokeDasharray="3 3"
                                    label={{ position: 'right', value: 'ENTRY', fill: '#22c55e', fontSize: 10 }}
                                />
                                {/* STOP LOSS LINE */}
                                {data[data.length - 1].stop_loss && (
                                    <ReferenceLine
                                        y={data[data.length - 1].stop_loss}
                                        stroke="#ef4444"
                                        label={{ position: 'right', value: 'STOP', fill: '#ef4444', fontSize: 10 }}
                                    />
                                )}
                                {/* TAKE PROFIT LINE */}
                                {data[data.length - 1].take_profit && (
                                    <ReferenceLine
                                        y={data[data.length - 1].take_profit}
                                        stroke="#10b981"
                                        label={{ position: 'right', value: 'TARGET', fill: '#10b981', fontSize: 10 }}
                                    />
                                )}
                            </>
                        )}
                    </ComposedChart>
                </ResponsiveContainer>
            </CardContent>
        </Card>
    );
}
