import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { Layout } from 'react-grid-layout';

// Define the default layout for the dashboard
// lg = 12 columns
const defaultTerminalLayout: Layout = [
  { i: 'chart', x: 0, y: 0, w: 8, h: 5 },
  { i: 'signals', x: 8, y: 0, w: 4, h: 3 },
  { i: 'heatmap', x: 8, y: 3, w: 4, h: 2 },
  { i: 'technical', x: 8, y: 5, w: 4, h: 4 },
  { i: 'setup', x: 0, y: 5, w: 4, h: 2 },
  { i: 'risk', x: 4, y: 5, w: 4, h: 2 },
  { i: 'broker', x: 0, y: 7, w: 8, h: 2 },
  { i: 'alpha', x: 0, y: 9, w: 12, h: 2 },
];

const defaultAnalyticsLayout: Layout = [
  { i: 'institutional', x: 0, y: 0, w: 12, h: 4 },
  { i: 'regime-detail', x: 0, y: 4, w: 7, h: 4 },
  { i: 'system-monitor', x: 7, y: 4, w: 5, h: 4 },
];

const defaultNewsLayout: Layout = [
  { i: 'news-feed', x: 0, y: 0, w: 12, h: 8 },
];

interface DashboardState {
  isEditMode: boolean;
  terminalLayout: Layout;
  analyticsLayout: Layout;
  newsLayout: Layout;
  panelScales: {
    terminal: Record<string, number>;
    analytics: Record<string, number>;
    news: Record<string, number>;
  };
  toggleEditMode: () => void;
  updateLayout: (tab: 'terminal' | 'analytics' | 'news', newLayout: Layout) => void;
  setPanelScale: (tab: 'terminal' | 'analytics' | 'news', panelId: string, scale: number) => void;
  resetPanelScales: (tab?: 'terminal' | 'analytics' | 'news') => void;
  resetLayout: (tab?: 'terminal' | 'analytics' | 'news') => void;
}

export const useDashboardStore = create<DashboardState>()(
  persist(
    (set) => ({
      isEditMode: false,
      terminalLayout: defaultTerminalLayout,
      analyticsLayout: defaultAnalyticsLayout,
      newsLayout: defaultNewsLayout,
      panelScales: {
        terminal: {},
        analytics: {},
        news: {}
      },
      toggleEditMode: () => set((state) => ({ isEditMode: !state.isEditMode })),
      updateLayout: (tab, newLayout) => set((state) => ({
        [tab === 'terminal' ? 'terminalLayout' : tab === 'analytics' ? 'analyticsLayout' : 'newsLayout']: newLayout
      })),
      setPanelScale: (tab, panelId, scale) => set((state) => ({
        panelScales: {
          ...state.panelScales,
          [tab]: {
            ...state.panelScales[tab],
            [panelId]: Math.max(0.7, Math.min(1.5, Number(scale.toFixed(2))))
          }
        }
      })),
      resetPanelScales: (tab) => set((state) => {
        if (tab === 'terminal') {
          return { panelScales: { ...state.panelScales, terminal: {} } };
        }
        if (tab === 'analytics') {
          return { panelScales: { ...state.panelScales, analytics: {} } };
        }
        if (tab === 'news') {
          return { panelScales: { ...state.panelScales, news: {} } };
        }
        return { panelScales: { terminal: {}, analytics: {}, news: {} } };
      }),
      resetLayout: (tab) => set((state) => {
        if (tab === 'terminal') return { terminalLayout: defaultTerminalLayout };
        if (tab === 'analytics') return { analyticsLayout: defaultAnalyticsLayout };
        if (tab === 'news') return { newsLayout: defaultNewsLayout };
        return { terminalLayout: defaultTerminalLayout, analyticsLayout: defaultAnalyticsLayout, newsLayout: defaultNewsLayout };
      }),
    }),
    {
      name: 'dashboard-layout-storage',
      partialize: (state) => ({
        terminalLayout: state.terminalLayout,
        analyticsLayout: state.analyticsLayout,
        newsLayout: state.newsLayout,
        panelScales: state.panelScales
      }),
    }
  )
);
