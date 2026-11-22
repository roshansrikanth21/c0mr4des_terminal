import React from 'react';
import { Button } from '@/components/ui/button';
import {
  LayoutDashboard,
  History,
  Settings,
  ShieldCheck,
  Menu,
  X,
  PlaySquare,
  Radio,
  FlaskConical,
  Sun,
  Moon
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Link, useLocation } from 'react-router-dom';
import { setTheme, useAppearance } from '@/lib/appearance';
import { ReplayBar } from '@/components/ReplayBar';

interface ShellProps {
  children: React.ReactNode;
}

export function Shell({ children }: ShellProps) {
  const location = useLocation();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = React.useState(false);
  const { theme } = useAppearance();
  const toggleTheme = () => setTheme(theme === 'light' ? 'dark' : 'light');

  const navItems = [
    { label: 'Dashboard', icon: LayoutDashboard, path: '/' },
    { label: 'News Radar', icon: Radio, path: '/news' },
    { label: 'Backtest', icon: PlaySquare, path: '/backtest' },
    { label: 'Trade Journal', icon: History, path: '/signals' },
    { label: 'Capital Test', icon: FlaskConical, path: '/capital' },
    { label: 'Settings', icon: Settings, path: '/settings' },
  ];

  return (
    <div className="flex h-screen bg-background text-foreground font-sans selection:bg-primary/30">
      {/* Desktop Sidebar */}
      <aside className="hidden lg:flex w-64 flex-col border-r border-border bg-card shadow-sm">
        <div className="h-20 flex items-center justify-between px-8 border-b border-border">
          <div className="flex items-center">
            <ShieldCheck className="w-6 h-6 mr-3 text-primary" />
            <span className="font-mono font-black text-xl tracking-tighter">C0MR4DE TERMINAL</span>
          </div>
          <Button variant="ghost" size="icon" onClick={toggleTheme} className="rounded-md">
            {theme === 'light' ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
          </Button>
        </div>

        <nav className="flex-1 p-6 space-y-3">
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={cn(
                "flex items-center px-4 py-3 rounded-md transition-all duration-200 group relative",
                location.pathname === item.path
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "hover:bg-accent text-muted-foreground hover:text-foreground"
              )}
            >
              <item.icon className={cn("w-4 h-4 mr-3 transition-transform group-hover:scale-110", location.pathname === item.path ? "animate-pulse" : "")} />
              <span className="text-xs font-bold tracking-tight uppercase font-mono">{item.label}</span>
            </Link>
          ))}
        </nav>

        <div className="p-6 border-t border-border">
          <div className="border border-border p-3 rounded-md bg-accent/30">
            <p className="text-[10px] font-mono font-bold uppercase tracking-widest">Decision support</p>
            <p className="text-[9px] text-muted-foreground leading-relaxed mt-1">
              Signals are probabilities, not promises. You place every order yourself. Not financial advice.
            </p>
          </div>
        </div>
      </aside>

      {/* Mobile Header */}
      <div className="lg:hidden fixed top-0 left-0 right-0 h-16 bg-card border-b border-border flex items-center justify-between px-6 z-50">
        <div className="flex items-center">
          <ShieldCheck className="w-5 h-5 mr-2 text-primary" />
          <span className="font-mono font-bold text-lg tracking-tight">C0MR4DE TERMINAL</span>
        </div>
        <Button variant="ghost" size="icon" onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)} className="rounded-md border border-border">
          {isMobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </Button>
      </div>

      {isMobileMenuOpen && (
        <div className="lg:hidden fixed inset-x-0 top-16 z-40 border-b border-border bg-card/95 backdrop-blur">
          <nav className="p-4 space-y-2">
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => setIsMobileMenuOpen(false)}
                className={cn(
                  "flex items-center px-4 py-3 rounded-md transition-all duration-200",
                  location.pathname === item.path
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "hover:bg-accent text-muted-foreground hover:text-foreground"
                )}
              >
                <item.icon className="w-4 h-4 mr-3" />
                <span className="text-xs font-bold tracking-tight uppercase font-mono">{item.label}</span>
              </Link>
            ))}
          </nav>
        </div>
      )}

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto pt-16 lg:pt-0">
        <div className="p-6 lg:p-12 w-full animate-fade-in">
          <ReplayBar />
          {children}
        </div>
      </main>
    </div>
  );
}
