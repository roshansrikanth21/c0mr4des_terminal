import React from 'react';
import { useAuth } from '@/hooks/use-auth';
import { Button } from '@/components/ui/button';
import { 
  LayoutDashboard, 
  History, 
  Settings, 
  LogOut, 
  ShieldCheck,
  Menu,
  X,
  PlaySquare
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Link, useLocation } from 'react-router-dom';

interface ShellProps {
  children: React.ReactNode;
}

export function Shell({ children }: ShellProps) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = React.useState(false);

  const navItems = [
    { label: 'Dashboard', icon: LayoutDashboard, path: '/' },
    { label: 'Backtest', icon: PlaySquare, path: '/backtest' },
    { label: 'History', icon: History, path: '/history' },
    { label: 'Risk Settings', icon: Settings, path: '/settings' },
  ];

  return (
    <div className="flex h-screen bg-background text-foreground font-sans">
      {/* Desktop Sidebar */}
      <aside className="hidden lg:flex w-64 flex-col border-r border-border bg-card">
        <div className="h-16 flex items-center px-6 border-b border-border">
          <ShieldCheck className="w-6 h-6 mr-2 text-primary" />
          <span className="font-mono font-bold text-lg tracking-tight">EDGE-OPS</span>
        </div>
        
        <nav className="flex-1 p-4 space-y-2">
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={cn(
                "flex items-center px-4 py-3 rounded-sm transition-all duration-200 group",
                location.pathname === item.path 
                  ? "bg-primary text-primary-foreground" 
                  : "hover:bg-secondary text-muted-foreground hover:text-foreground"
              )}
            >
              <item.icon className="w-5 h-5 mr-3" />
              <span className="text-sm font-medium">{item.label}</span>
            </Link>
          ))}
        </nav>

        <div className="p-4 border-t border-border bg-secondary/50">
          <div className="flex items-center px-4 py-2 mb-4">
            <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-primary-foreground font-bold text-xs">
              {user?.email?.charAt(0).toUpperCase()}
            </div>
            <div className="ml-3 overflow-hidden">
              <p className="text-xs font-medium truncate">{user?.email}</p>
            </div>
          </div>
          <Button 
            variant="ghost" 
            className="w-full justify-start text-muted-foreground hover:text-destructive transition-colors"
            onClick={logout}
          >
            <LogOut className="w-4 h-4 mr-2" />
            <span className="text-sm">Logout</span>
          </Button>
        </div>
      </aside>

      {/* Mobile Header */}
      <div className="lg:hidden fixed top-0 left-0 right-0 h-16 bg-card border-b border-border flex items-center justify-between px-6 z-50">
        <div className="flex items-center">
          <ShieldCheck className="w-6 h-6 mr-2 text-primary" />
          <span className="font-mono font-bold text-lg tracking-tight">EDGE-OPS</span>
        </div>
        <Button variant="ghost" size="icon" onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}>
          {isMobileMenuOpen ? <X /> : <Menu />}
        </Button>
      </div>

      {/* Mobile Menu */}
      {isMobileMenuOpen && (
        <div className="lg:hidden fixed inset-0 top-16 bg-background z-40 p-6 flex flex-col">
          <nav className="space-y-4 mb-auto">
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => setIsMobileMenuOpen(false)}
                className={cn(
                  "flex items-center px-4 py-4 rounded-sm border",
                  location.pathname === item.path 
                    ? "bg-primary border-primary text-primary-foreground" 
                    : "border-border text-muted-foreground"
                )}
              >
                <item.icon className="w-6 h-6 mr-4" />
                <span className="text-lg font-medium">{item.label}</span>
              </Link>
            ))}
          </nav>
          <Button variant="destructive" className="w-full h-14 text-lg" onClick={logout}>
            <LogOut className="w-6 h-6 mr-4" />
            Logout
          </Button>
        </div>
      )}

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto pt-16 lg:pt-0 bg-background">
        <div className="max-w-6xl mx-auto p-6 lg:p-10 animate-fade-in">
          {children}
        </div>
      </main>
    </div>
  );
}
