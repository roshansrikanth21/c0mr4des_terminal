import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from '@/hooks/use-auth';
import { Shell } from '@/components/layout/Shell';
import { LandingPage } from '@/pages/LandingPage';
import { Dashboard } from '@/pages/Dashboard';
import { Backtest } from '@/pages/Backtest';
import { History } from '@/pages/History';
import { Settings } from '@/pages/Settings';
import { Spinner } from '@/components/ui/spinner';

function App() {
  const { isAuthenticated, isLoading, login } = useAuth();

  if (isLoading) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-background">
        <Spinner size="lg" className="text-primary" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LandingPage onLogin={() => login(window.location.origin)} />;
  }

  return (
    <Router>
      <Shell>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/history" element={<History />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Shell>
    </Router>
  );
}

export default App;