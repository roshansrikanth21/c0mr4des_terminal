import { useEffect, useState } from 'react';

export type Theme = 'dark' | 'light';
export type ViewMode = 'full' | 'focus';
const EVT = 'appearance-change';

export function getTheme(): Theme {
  return (localStorage.getItem('theme') as Theme) || 'dark';
}

export function setTheme(t: Theme) {
  localStorage.setItem('theme', t);
  document.documentElement.classList.toggle('dark', t === 'dark');
  window.dispatchEvent(new Event(EVT));
}

export function getViewMode(): ViewMode {
  return (localStorage.getItem('view-mode') as ViewMode) || 'full';
}

export function setViewMode(m: ViewMode) {
  localStorage.setItem('view-mode', m);
  window.dispatchEvent(new Event(EVT));
}

/** Re-renders when theme or view mode changes anywhere in the app. */
export function useAppearance() {
  const [state, setState] = useState({ theme: getTheme(), view: getViewMode() });
  useEffect(() => {
    const on = () => setState({ theme: getTheme(), view: getViewMode() });
    window.addEventListener(EVT, on);
    return () => window.removeEventListener(EVT, on);
  }, []);
  return state;
}
