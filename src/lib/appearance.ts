import { useEffect, useState } from 'react';

export type Theme = 'dark' | 'light';
export type ViewMode = 'full' | 'focus' | 'simple';
export type Preset = 'terminal' | 'terminal-light' | 'ocean' | 'paper' | 'ember' | 'forest' | 'graphite' | 'rose';
const EVT = 'appearance-change';

export const PRESETS: { id: Preset; name: string; blurb: string; mode: Theme; soft: boolean; swatch: string[] }[] = [
  { id: 'terminal', name: 'Terminal', blurb: 'The original: black, mono, high contrast.', mode: 'dark', soft: false, swatch: ['#09090b', '#27272a', '#fafafa'] },
  { id: 'terminal-light', name: 'Terminal Light', blurb: 'The original layout in soft grey, no glare.', mode: 'light', soft: false, swatch: ['#e6e8ec', '#f4f5f8', '#1a1f2b'] },
  { id: 'paper', name: 'Paper', blurb: 'Warm cream, rounded, friendly. Best in a bright room.', mode: 'light', soft: true, swatch: ['#f2ede3', '#fcfaf5', '#2f5fd8'] },
  { id: 'ocean', name: 'Ocean', blurb: 'Vivid deep blue with a bright sky accent.', mode: 'dark', soft: true, swatch: ['#0d1a2f', '#14233d', '#22b8f5'] },
  { id: 'ember', name: 'Ember', blurb: 'Warm espresso charcoal, amber accent. Cosy for long sessions and nights.', mode: 'dark', soft: true, swatch: ['#1a1613', '#221d19', '#f8a832'] },
  { id: 'forest', name: 'Forest', blurb: 'Deep green charcoal, emerald accent. Calm and focused.', mode: 'dark', soft: true, swatch: ['#111a17', '#16211d', '#26d98a'] },
  { id: 'rose', name: 'Rosé', blurb: 'Plum charcoal with a rose-pink accent. Soft, elegant, easy on the eyes.', mode: 'dark', soft: true, swatch: ['#1b1418', '#241a20', '#f17cb6'] },
  { id: 'graphite', name: 'Graphite', blurb: 'Neutral graphite, vivid violet accent. Modern and crisp.', mode: 'dark', soft: true, swatch: ['#16171c', '#1d1f25', '#9d6bff'] },
];

export function getPreset(): Preset {
  let p = localStorage.getItem('preset') as string | null;
  if (p === 'midnight' || p === 'calm') p = 'ocean'; // retired presets
  if (p && PRESETS.some((x) => x.id === p)) return p as Preset;
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

/** Sidebar sun/moon: flip to the paired preset (terminal <-> terminal-light, ocean <-> paper). */
export function setTheme(t: Theme) {
  const cur = getPreset();
  const pair: Record<Preset, Preset> = { terminal: 'terminal-light', 'terminal-light': 'terminal', ocean: 'paper', paper: 'ember', ember: 'paper', forest: 'paper', graphite: 'paper', rose: 'paper' };
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
