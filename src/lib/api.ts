import { useEffect, useRef, useState } from 'react';

export type Symbol = 'NIFTY' | 'SENSEX';
export type Verdict = 'BUY' | 'SELL' | 'NO TRADE';
export type Signal = 'bullish' | 'bearish' | 'neutral';

export interface Candle { time: number; open: number; high: number; low: number; close: number }
export interface Level { name: string; price: number; weight: number }
export interface Pattern {
  name: string; direction: number; kind: string; bars: number; time: string; price: number;
  strength: number; context_ok: boolean; meaning: string;
}
export interface Reason { factor: string; signal: Signal; text: string }
export interface Session {
  now: string; is_trading_day: boolean; is_open: boolean; phase: string; phase_note: string; can_enter: boolean;
  square_off_by: string; next_open: string; expiry: string; expiry_weekday: string; days_to_expiry: number;
  is_expiry_day: boolean; expiry_note: string; minutes_to_close: number;
}
export interface OptionPlan {
  side: string; symbol_hint: string; strike: number; option_type: 'CE' | 'PE'; expiry: string; premium: number;
  premium_source: string; premium_stop: number; premium_target: number;
  greeks: { price: number; delta: number; gamma: number; theta_per_day: number; vega: number; iv?: number };
  lot_size: number; lots: number; quantity: number; capital_needed: number; max_loss: number;
  charges_round_trip: number; note: string;
}
export interface Cue { symbol: string; label: string; available: boolean; last?: number; change_pct?: number; effect?: number; why?: string }
export interface NewsItem {
  id: string; title: string; url: string; summary: string; source: string; sources: string[]; kind: string;
  published: string; age_minutes: number; direction: number; impact: number; scope: string; keywords: string[];
  why: string; score: number;
}
export interface Analysis {
  instrument: { key: Symbol; name: string; lot_size: number; strike_step: number };
  generated_at: string; data_source: string; data_delayed: boolean; session: Session;
  vix: { value: number; change_pct: number; regime: string; text: string; percentile_1m: number } | null;
  expected_move_rest_of_day: number | null;
  verdict: Verdict; lean: 'BUY' | 'SELL' | 'NEUTRAL'; score: number; confidence: number; headline: string;
  summary: string; gates: string[]; reasons: Reason[]; triggers: string[];
  factors: Record<string, number>; weights: Record<string, number>;
  price: number; atr: number; bar_time: string;
  plan: { direction: number; entry: number; stop: number; target: number; risk_points: number; target_points: number; reward_risk: number };
  indicators: Record<string, number>; patterns: Pattern[];
  anatomy: { color: string; body_pct: number; upper_wick_pct: number; lower_wick_pct: number; range_vs_atr: number; shape: string; text: string };
  structure: { swings: { i: number; type: 'H' | 'L'; price: number; label: string; time: string }[]; trend: number; text: string;
    bos: { direction: number; kind: string; level: number; text: string } | null;
    fvgs: { direction: number; low: number; high: number; time: string }[] };
  levels: Level[]; support: Level | null; resistance: Level | null;
  option: OptionPlan | null; pcr: number | null;
  news: { bias: number; count: number; text: string; drivers: { title: string; direction: number; why: string; source: string }[] };
  global: { bias: number; text: string; cues: Cue[] };
  candles: Candle[]; broker_connected: boolean; spot_live?: number;
  orb?: OrbSignal; first30?: OrbSignal;
  shock?: { active: boolean; reasons: string[]; playbook: string[] } | null;
  paper?: { events: { type: string; reason?: string; trade?: PaperTrade }[]; open: PaperTrade[] };
}

export interface OrbSignal {
  name: string; verdict: Verdict; direction: number; status: string; text: string;
  range_high?: number; range_low?: number; range_points?: number; prev_close?: number | null;
  trigger_time?: string; entry?: number; stop?: number; target?: number; option?: OptionPlan | null;
}

export interface PaperTrade {
  slot?: string; strategy?: string;
  instrument: string; dir: number; side: string; symbol: string; strike: number; option_type: 'CE' | 'PE'; expiry: string;
  quantity: number; lots: number; entry_premium: number; premium_source: string; premium_stop: number; premium_target: number;
  entry_spot: number; index_stop: number; index_target: number | null; opened_at: string; score: number; mark?: number;
  unrealized?: number; closed_at?: string; exit_spot?: number; exit_premium?: number; reason?: string; charges?: number; pnl?: number;
}

export interface PaperSummary {
  open: PaperTrade[]; today: { trades: number; pnl: number; wins: number };
  by_strategy: Record<string, { trades: number; wins: number; pnl: number }>;
  all_time: { trades: number; pnl: number; wins: number; win_rate: number | null }; closed: PaperTrade[];
  live_trading_enabled: boolean; broker_connected: boolean;
}

export async function getJSON<T>(url: string, timeout = 30000, init?: RequestInit): Promise<T> {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeout);
  try {
    const res = await fetch(url, { ...init, signal: ctl.signal });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `${res.status} ${res.statusText}`);
    }
    return (await res.json()) as T;
  } finally {
    clearTimeout(t);
  }
}

/** Live analysis: WebSocket push from the backend, falling back to polling if the socket drops. */
export function useAnalysis(symbol: Symbol) {
  const [data, setData] = useState<Analysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<number>(0);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    let closed = false;
    setData(null);
    setError(null);
    const apply = (a: Analysis) => { if (!closed) { setData(a); setError(null); setUpdatedAt(Date.now()); } };

    const poll = async () => {
      try { apply(await getJSON<Analysis>(`/api/signal?symbol=${symbol}`, 60000)); }
      catch (e) { if (!closed) setError((e as Error).message); }
    };
    poll();

    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    let ws: WebSocket | null = null;
    try {
      ws = new WebSocket(`${proto}://${window.location.host}/ws?symbol=${symbol}`);
      ws.onopen = () => setLive(true);
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'signal') apply(msg.data);
        else if (msg.type === 'error') setError(msg.message);
      };
      ws.onclose = () => {
        setLive(false);
        if (!closed && pollRef.current === null) pollRef.current = window.setInterval(poll, 30000);
      };
    } catch {
      pollRef.current = window.setInterval(poll, 30000);
    }
    return () => {
      closed = true;
      ws?.close();
      if (pollRef.current !== null) window.clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, [symbol]);

  return { data, error, live, updatedAt };
}

export const inr = (v: number, digits = 0) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: digits, minimumFractionDigits: digits }).format(v);

export const num = (v: number | null | undefined, digits = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? '--' : v.toLocaleString('en-IN', { maximumFractionDigits: digits, minimumFractionDigits: digits });

export const signalColor = (s: Signal | number | string) => {
  const v = typeof s === 'number' ? (s > 0 ? 'bullish' : s < 0 ? 'bearish' : 'neutral') : s;
  return v === 'bullish' || v === 'BUY' ? 'text-green-500' : v === 'bearish' || v === 'SELL' ? 'text-red-500' : 'text-muted-foreground';
};

export const ago = (minutes: number) =>
  minutes < 1 ? 'just now' : minutes < 60 ? `${minutes}m ago` : minutes < 1440 ? `${Math.floor(minutes / 60)}h ago` : `${Math.floor(minutes / 1440)}d ago`;
