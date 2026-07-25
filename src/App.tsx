import React, { Suspense, lazy, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from '@/hooks/use-auth';
import { Shell } from '@/components/layout/Shell';
import { Spinner } from '@/components/ui/spinner';
import { BlinkRemover } from '@/components/BlinkRemover';

const LandingPage = lazy(() => import('@/pages/LandingPage').then((m) => ({ default: m.LandingPage })));
const Dashboard = lazy(() => import('@/pages/Dashboard').then((m) => ({ default: m.Dashboard })));
const Backtest = lazy(() => import('@/pages/Backtest').then((m) => ({ default: m.Backtest })));
const LiveOps = lazy(() => import('@/pages/LiveOps').then((m) => ({ default: m.LiveOps })));
const MemoryLab = lazy(() => import('@/pages/MemoryLab').then((m) => ({ default: m.MemoryLab })));
const History = lazy(() => import('@/pages/History').then((m) => ({ default: m.History })));
const Settings = lazy(() => import('@/pages/Settings').then((m) => ({ default: m.Settings })));
const SocialIntel = lazy(() => import('@/pages/SocialIntel').then((m) => ({ default: m.SocialIntel })));

function RouteFallback() {
  return (
    <div className="h-[60vh] w-full flex items-center justify-center bg-background">
      <Spinner className="text-primary w-8 h-8" />
    </div>
  );
}

function App() {
  const { isAuthenticated, isLoading, login, register, authMode } = useAuth();

  useEffect(() => {
    const theme = localStorage.getItem('theme') || 'dark';
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, []);

  if (isLoading) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-background">
        <Spinner className="text-primary w-8 h-8" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <>
        <BlinkRemover />
        <Suspense fallback={<RouteFallback />}>
          <LandingPage authMode={authMode} onLogin={login} onRegister={register} />
        </Suspense>
      </>
    );
  }

  return (
    <Router>
      <BlinkRemover />
      <Shell>
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/backtest" element={<Backtest />} />
            <Route path="/live-ops" element={<LiveOps />} />
            <Route path="/social-radar" element={<SocialIntel />} />
            <Route path="/memory-lab" element={<MemoryLab />} />
            <Route path="/history" element={<History />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </Shell>
    </Router>
  );
}

export default App;
