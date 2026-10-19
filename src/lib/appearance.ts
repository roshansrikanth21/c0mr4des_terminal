import { useEffect, useState } from 'react';

export type Theme = 'dark' | 'light';
export type ViewMode = 'full' | 'focus';
export type Preset = 'terminal' | 'terminal-light' | 'calm' | 'midnight' | 'paper';
const EVT = 'appearance-change';

export const PRESETS: { id: Preset; name: string; blurb: string; mode: Theme; soft: boolean; swatch: string[] }[] = [
  { id: 'terminal', name: 'Terminal', blurb: 'The original: black, mono, high contrast.', mode: 'dark', soft: false, swatch: ['#09090b', '#27272a', '#fafafa'] },
  { id: 'terminal-light', name: 'Terminal Light', blurb: 'The original layout on white.', mode: 'light', soft: false, swatch: ['#f4f4f5', '#ffffff', '#18181b'] },
  { id: 'calm', name: 'Calm', blurb: 'Soft slate, rounded, mint accent. Easy on the eyes all day.', mode: 'dark', soft: true, swatch: ['#161b26', '#1d2330', '#4fcf98'] },
  { id: 'midnight', name: 'Midnight', blurb: 'Deep navy with blue accents, like a broker terminal.', mode: 'dark', soft: true, swatch: ['#0a1020', '#0f1729', '#3b82f6'] },
  { id: 'paper', name: 'Paper', blurb: 'Warm light, rounded, friendly. Best in a bright room.', mode: 'light', soft: true, swatch: ['#f7f4ee', '#ffffff', '#2f62d4'] },
];

export function getPreset(): Preset {
  const p = localStorage.getItem('preset') as Preset | null;
  if (p && PRESETS.some((x) => x.id === p)) return p;
  return localStorage.getItem('theme') === 'light' ? 'terminal-light' : 'terminal';
}

export function applyPreset(p: Preset = getPreset()) {
  const def = PRESETS.find((x) => x.id === p) ?? PRESETS[0];
  const root = document.documentElement;
  root.classList.toggle('dark', def.mode === 'dark');
  if (def.soft) root.setAttribute('data-soft', '');
  else root.removeAttribute('data-soft');
  if (p === 'terminal' || p === 'terminal-light') root.removeAttribute('data-preset');
  else root.setAttribute('data-preset', p);
}

export function setPreset(p: Preset) {
  localStorage.setItem('preset', p);
  localStorage.setItem('theme', PRESETS.find((x) => x.id === p)?.mode ?? 'dark');
  applyPreset(p);
  window.dispatchEvent(new Event(EVT));
}

export function getTheme(): Theme {
  return PRESETS.find((x) => x.id === getPreset())?.mode ?? 'dark';
}

/** Sidebar sun/moon: flip to the paired preset (terminal <-> terminal-light, calm/midnight <-> paper). */
export function setTheme(t: Theme) {
  const cur = getPreset();
  const pair: Record<Preset, Preset> = { terminal: 'terminal-light', 'terminal-light': 'terminal', calm: 'paper', midnight: 'paper', paper: 'calm' };
  const next = PRESETS.find((x) => x.id === cur)?.mode === t ? cur : pair[cur];
  setPreset(next);
}

export function getViewMode(): ViewMode {
  return (localStorage.getItem('view-mode') as ViewMode) || 'full';
}

export function setViewMode(m: ViewMode) {
  localStorage.setItem('view-mode', m);
  window.dispatchEvent(new Event(EVT));
}

/** Re-renders when the look or view mode changes anywhere in the app. */
export function useAppearance() {
  const [state, setState] = useState({ theme: getTheme(), view: getViewMode(), preset: getPreset() });
  useEffect(() => {
    const on = () => setState({ theme: getTheme(), view: getViewMode(), preset: getPreset() });
    window.addEventListener(EVT, on);
    return () => window.removeEventListener(EVT, on);
  }, []);
  return state;
}

/** Resolve a CSS variable (HSL triplet) to a hex color the chart library accepts. */
export function cssColor(varName: string, alpha = 1): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
  const ctx = document.createElement('canvas').getContext('2d');
  if (!ctx || !v) return '#888888';
  ctx.fillStyle = `hsl(${v.replace(/ /g, ', ').replace(/,\s*,/g, ',')})`;
  const hex = ctx.fillStyle as string;
  if (alpha >= 1 || !hex.startsWith('#')) return hex;
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}
