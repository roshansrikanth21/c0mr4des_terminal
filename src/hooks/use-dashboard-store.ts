import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { Layout } from 'react-grid-layout';

export type DashboardTab = 'terminal' | 'context' | 'news';

// lg = 12 columns, rowHeight 100
const defaultLayouts: Record<DashboardTab, Layout> = {
  terminal: [
    { i: 'chart', x: 0, y: 0, w: 8, h: 5 },
    { i: 'verdict', x: 8, y: 0, w: 4, h: 5 },
    { i: 'orb', x: 0, y: 5, w: 4, h: 4 },
    { i: 'option', x: 4, y: 5, w: 4, h: 4 },
    { i: 'paper', x: 8, y: 5, w: 4, h: 4 },
    { i: 'reasons', x: 0, y: 9, w: 6, h: 4 },
    { i: 'timeline', x: 6, y: 9, w: 6, h: 4 },
    { i: 'structure', x: 0, y: 13, w: 6, h: 4 },
    { i: 'news', x: 6, y: 13, w: 6, h: 4 },
  ],
  context: [
    { i: 'global', x: 0, y: 0, w: 4, h: 5 },
    { i: 'structure', x: 4, y: 0, w: 4, h: 5 },
    { i: 'news', x: 8, y: 0, w: 4, h: 5 },
  ],
  news: [{ i: 'news', x: 0, y: 0, w: 12, h: 8 }],
};

interface DashboardState {
  isEditMode: boolean;
  layouts: Record<DashboardTab, Layout>;
  panelScales: Record<DashboardTab, Record<string, number>>;
  toggleEditMode: () => void;
  updateLayout: (tab: DashboardTab, newLayout: Layout) => void;
  setPanelScale: (tab: DashboardTab, panelId: string, scale: number) => void;
  resetPanelScales: (tab?: DashboardTab) => void;
  resetLayout: (tab?: DashboardTab) => void;
}

export const useDashboardStore = create<DashboardState>()(
  persist(
    (set) => ({
      isEditMode: false,
      layouts: defaultLayouts,
      panelScales: { terminal: {}, context: {}, news: {} },
      toggleEditMode: () => set((s) => ({ isEditMode: !s.isEditMode })),
      updateLayout: (tab, newLayout) => set((s) => ({ layouts: { ...s.layouts, [tab]: newLayout } })),
      setPanelScale: (tab, panelId, scale) => set((s) => ({
        panelScales: { ...s.panelScales, [tab]: { ...s.panelScales[tab], [panelId]: Math.max(0.7, Math.min(1.5, Number(scale.toFixed(2)))) } },
      })),
      resetPanelScales: (tab) => set((s) => ({
        panelScales: tab ? { ...s.panelScales, [tab]: {} } : { terminal: {}, context: {}, news: {} },
      })),
      resetLayout: (tab) => set((s) => ({ layouts: tab ? { ...s.layouts, [tab]: defaultLayouts[tab] } : defaultLayouts })),
    }),
    {
      name: 'dashboard-layout-v6',
      partialize: (s) => ({ layouts: s.layouts, panelScales: s.panelScales }),
    },
  ),
);
