import { Suspense, lazy, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Shell } from '@/components/layout/Shell';
import { Spinner } from '@/components/ui/spinner';
import { applyPreset } from '@/lib/appearance';

const Dashboard = lazy(() => import('@/pages/Dashboard').then((m) => ({ default: m.Dashboard })));
const NewsRadar = lazy(() => import('@/pages/NewsRadar').then((m) => ({ default: m.NewsRadar })));
const Backtest = lazy(() => import('@/pages/Backtest').then((m) => ({ default: m.Backtest })));
const SignalLog = lazy(() => import('@/pages/SignalLog').then((m) => ({ default: m.SignalLog })));
const Settings = lazy(() => import('@/pages/Settings').then((m) => ({ default: m.Settings })));
const CapitalTest = lazy(() => import('@/pages/CapitalTest').then((m) => ({ default: m.CapitalTest })));

function RouteFallback() {
  return (
    <div className="h-[60vh] w-full flex items-center justify-center bg-background">
      <Spinner className="text-primary w-8 h-8" />
    </div>
  );
}

function App() {
  useEffect(() => { applyPreset(); }, []);

  return (
    <Router>
      <Shell>
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/news" element={<NewsRadar />} />
            <Route path="/backtest" element={<Backtest />} />
            <Route path="/signals" element={<SignalLog />} />
            <Route path="/capital" element={<CapitalTest />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </Shell>
    </Router>
  );
}

export default App;
