import React from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ShieldCheck, ArrowRight, ShieldAlert, BarChart3, Zap } from 'lucide-react';
import type { LocalLoginInput } from '@/hooks/use-auth';

interface LandingPageProps {
  authMode: 'blink' | 'local';
  onLogin: (input?: string | LocalLoginInput) => Promise<unknown> | unknown;
  onRegister: (input: LocalLoginInput) => Promise<unknown> | unknown;
}

export function LandingPage({ authMode, onLogin, onRegister }: LandingPageProps) {
  const [username, setUsername] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [error, setError] = React.useState('');
  const [isBusy, setIsBusy] = React.useState(false);

  const credentials = { username: username.trim(), password };

  const runLocalAuth = async (mode: 'login' | 'register') => {
    setError('');
    if (!credentials.username || !credentials.password) {
      setError('Username and password are required.');
      return;
    }
    setIsBusy(true);
    try {
      if (mode === 'register') {
        await onRegister(credentials);
      } else {
        await onLogin(credentials);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authentication failed.');
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground font-sans flex flex-col">
      <header className="h-20 flex items-center justify-between px-6 lg:px-12 border-b border-border bg-card/50 backdrop-blur-sm fixed top-0 w-full z-50">
        <div className="flex items-center">
          <ShieldCheck className="w-8 h-8 mr-3 text-primary" />
          <span className="font-mono font-bold text-xl tracking-tight">C0MR4DE TERMINAL</span>
        </div>
        {authMode === 'blink' ? (
          <Button onClick={() => onLogin(window.location.origin)} variant="outline" className="font-mono uppercase tracking-widest text-xs px-8">
            Access Terminal
          </Button>
        ) : (
          <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Local Auth Mode
          </span>
        )}
      </header>

      <main className="flex-1 pt-20">
        {/* Hero Section */}
        <section className="py-20 lg:py-32 px-6 lg:px-12 max-w-7xl mx-auto">
          <div className="max-w-3xl">
            <div className="inline-flex items-center px-3 py-1 rounded-full bg-secondary text-primary text-xs font-mono mb-6 animate-fade-in">
              <span className="w-2 h-2 rounded-full bg-primary mr-2 animate-pulse" />
              SYSTEM STATUS: OPERATIONAL
            </div>
            <h1 className="text-5xl lg:text-7xl font-bold tracking-tighter mb-8 leading-tight">
              Capital preservation is the <span className="text-muted-foreground italic">only</span> strategy.
            </h1>
            <p className="text-xl text-muted-foreground mb-10 leading-relaxed max-w-2xl">
              C0MR4DE TERMINAL is an AI-assisted options trading system designed to increase trader edge by matching strategies to market regimes and managing risk ruthlessly.
            </p>
            {authMode === 'blink' ? (
              <div className="flex flex-col sm:flex-row gap-4">
                <Button onClick={() => onLogin(window.location.origin)} size="lg" className="h-16 px-10 text-lg group">
                  Enter Dashboard
                  <ArrowRight className="ml-2 w-5 h-5 group-hover:translate-x-1 transition-transform" />
                </Button>
                <Button variant="ghost" size="lg" className="h-16 px-10 text-lg border border-transparent hover:border-border">
                  Read Philosophy
                </Button>
              </div>
            ) : (
              <div className="max-w-xl rounded-xl border border-border bg-card/60 p-6 backdrop-blur-sm space-y-5">
                <div className="space-y-1">
                  <div className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Operator Authentication</div>
                  <div className="text-sm text-muted-foreground">
                    Local JWT auth is active. Create an operator account once, then sign in normally.
                  </div>
                </div>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Username</div>
                    <Input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="operator" />
                  </div>
                  <div className="space-y-2">
                    <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Password</div>
                    <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
                  </div>
                </div>
                {error && (
                  <div className="text-xs font-mono uppercase tracking-wider text-destructive">
                    {error}
                  </div>
                )}
                <div className="flex flex-col sm:flex-row gap-4">
                  <Button onClick={() => runLocalAuth('login')} disabled={isBusy} size="lg" className="h-14 px-8 text-sm group">
                    Sign In
                    <ArrowRight className="ml-2 w-4 h-4 group-hover:translate-x-1 transition-transform" />
                  </Button>
                  <Button onClick={() => runLocalAuth('register')} disabled={isBusy} variant="outline" size="lg" className="h-14 px-8 text-sm">
                    Create Operator
                  </Button>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Philosophy Section */}
        <section className="py-24 bg-secondary/30 border-y border-border px-6 lg:px-12">
          <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-12 lg:gap-24">
            <div className="space-y-4">
              <ShieldAlert className="w-10 h-10 text-primary mb-4" />
              <h3 className="text-xl font-bold font-mono uppercase tracking-tighter">Ruthless Risk</h3>
              <p className="text-muted-foreground leading-relaxed">
                We prioritize capital survival over growth. The system enforces strict daily limits and forced cooldowns after losses.
              </p>
            </div>
            <div className="space-y-4">
              <BarChart3 className="w-10 h-10 text-primary mb-4" />
              <h3 className="text-xl font-bold font-mono uppercase tracking-tighter">Regime Detection</h3>
              <p className="text-muted-foreground leading-relaxed">
                Strategies are mapped to volatility and price structure. If the regime doesn't match, the system says NO TRADE.
              </p>
            </div>
            <div className="space-y-4">
              <Zap className="w-10 h-10 text-primary mb-4" />
              <h3 className="text-xl font-bold font-mono uppercase tracking-tighter">Discipline First</h3>
              <p className="text-muted-foreground leading-relaxed">
                No dopamine UI. No revenge trading. No prediction guessing. Just rule-based execution for consistent edge.
              </p>
            </div>
          </div>
        </section>

        {/* Disclaimer */}
        <section className="py-20 px-6 lg:px-12 max-w-7xl mx-auto text-center">
          <p className="text-xs font-mono text-muted-foreground uppercase tracking-widest max-w-2xl mx-auto">
            C0MR4DE TERMINAL DOES NOT PROMISE PROFITS. TRADING OPTIONS INVOLVES SUBSTANTIAL RISK. ONLY TRADE WITH CAPITAL YOU CAN AFFORD TO LOSE.
          </p>
        </section>
      </main>

      <footer className="py-12 px-6 lg:px-12 border-t border-border flex flex-col md:flex-row items-center justify-between gap-6">
        <div className="flex items-center text-muted-foreground">
          <ShieldCheck className="w-5 h-5 mr-2 opacity-50" />
          <span className="font-mono text-xs">© 2026 C0MR4DE TERMINAL</span>
        </div>
        <div className="flex gap-8 text-xs font-mono text-muted-foreground uppercase tracking-widest">
          <a href="#" className="hover:text-primary transition-colors">Twitter</a>
          <a href="#" className="hover:text-primary transition-colors">Documentation</a>
          <a href="#" className="hover:text-primary transition-colors">Status</a>
        </div>
      </footer>
    </div>
  );
}
