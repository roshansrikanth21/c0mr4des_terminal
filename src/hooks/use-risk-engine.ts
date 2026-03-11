import { useState, useEffect } from 'react';
import type { BrokerStatus, Portfolio } from './use-broker';

export interface RiskState {
  dailyLoss: number;
  tradesToday: number;
  consecutiveLosses: number;
  isDailyLimitReached: boolean;
  isLocked: boolean;
  isLoading: boolean;
}

const MAX_DAILY_LOSS = 5000;
const MAX_TRADES = 3;

interface RiskEngineInput {
  status?: BrokerStatus | null;
  portfolio?: Portfolio | null;
}

/**
 * Derives risk lock state from broker snapshots passed by the caller.
 * This avoids creating a second polling stream from inside the risk hook.
 */
export function useRiskEngine(input?: RiskEngineInput) {
  const [state, setState] = useState<RiskState>({
    dailyLoss: 0,
    tradesToday: 0,
    consecutiveLosses: 0,
    isDailyLimitReached: false,
    isLocked: false,
    isLoading: true,
  });

  useEffect(() => {
    const status = input?.status;
    const portfolio = input?.portfolio;

    if (!status) {
      setState(prev => ({ ...prev, isLoading: true }));
      return;
    }

    const currentPnL = status.pnl || 0;
    const dailyLoss = currentPnL < 0 ? Math.abs(currentPnL) : 0;
    const tradesToday = portfolio?.positions?.length || 0;
    const limitReached = dailyLoss > MAX_DAILY_LOSS || tradesToday > MAX_TRADES;

    setState({
      dailyLoss,
      tradesToday,
      consecutiveLosses: 0,
      isDailyLimitReached: limitReached,
      isLocked: limitReached,
      isLoading: false,
    });
  }, [input?.status, input?.portfolio]);

  return {
    ...state,
    refresh: () => { /* no-op: state is derived from hook inputs */ }
  };
}
