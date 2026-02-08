import { useState, useEffect, useCallback } from 'react';
import { blink } from '@/lib/blink';
import { useAuth } from '@/hooks/use-auth';

export interface RiskState {
  dailyLoss: number;
  tradesToday: number;
  consecutiveLosses: number;
  isDailyLimitReached: boolean;
  isLocked: boolean;
  isLoading: boolean;
}

/**
 * Hook to manage risk rules and daily statistics
 */
export function useRiskEngine() {
  const { user } = useAuth();
  const [state, setState] = useState<RiskState>({
    dailyLoss: 0,
    tradesToday: 0,
    consecutiveLosses: 0,
    isDailyLimitReached: false,
    isLocked: false,
    isLoading: true,
  });

  const fetchStats = useCallback(async () => {
    if (!user) return;

    try {
      const today = new Date().toISOString().split('T')[0];
      
      // Get daily stats
      const stats = await blink.db.dailyStats.list({
        where: { user_id: user.id, trading_date: today },
        limit: 1
      });

      // Get risk settings
      const settingsList = await blink.db.riskSettings.list({
        where: { user_id: user.id },
        limit: 1
      });

      const settings = settingsList[0] || {
        max_trades_per_day: 3,
        stop_trading_after_losses: 2
      };

      if (stats.length > 0) {
        const s = stats[0];
        const tradesToday = Number(s.trades_count);
        const consecutiveLosses = Number(s.consecutive_losses);
        const isLocked = Number(s.is_locked) > 0;
        
        const limitReached = 
          tradesToday >= Number(settings.max_trades_per_day) || 
          consecutiveLosses >= Number(settings.stop_trading_after_losses);

        setState({
          dailyLoss: Number(s.current_drawdown),
          tradesToday,
          consecutiveLosses,
          isDailyLimitReached: limitReached,
          isLocked: isLocked || limitReached,
          isLoading: false
        });
      } else {
        // Create stats for today if none exist
        await blink.db.dailyStats.create({
          user_id: user.id,
          trading_date: today,
          trades_count: 0,
          consecutive_losses: 0,
          current_drawdown: 0,
          is_locked: 0
        });
        
        setState(prev => ({ ...prev, isLoading: false }));
      }
    } catch (error) {
      console.error('Error fetching risk stats:', error);
      setState(prev => ({ ...prev, isLoading: false }));
    }
  }, [user]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  return {
    ...state,
    refresh: fetchStats
  };
}
