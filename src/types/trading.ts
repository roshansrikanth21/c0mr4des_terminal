export type MarketRegime = 
  | 'Strong Uptrend'
  | 'Strong Downtrend'
  | 'Range-bound'
  | 'Volatility Expansion'
  | 'Volatility Compression'
  | 'Event-driven';

export interface RegimeStatus {
  regime: MarketRegime;
  confidence: number;
  isTradeAllowed: boolean;
  reason?: string;
}

export interface TradeStrategy {
  name: string;
  description: string;
  type: 'debit_spread' | 'credit_spread' | 'iron_condor' | 'straddle' | 'vol_play' | 'iv_crush';
}

export interface BacktestResult {
  date: string;
  regime: MarketRegime;
  strategy: string;
  outcome: 'Profit' | 'Loss' | 'Filtered';
  pnl: number;
  reason?: string;
}

export const REGIME_STRATEGY_MAP: Record<MarketRegime, TradeStrategy> = {
  'Strong Uptrend': {
    name: 'Call Debit Spreads',
    description: 'Bullish strategy with capped risk and capped profit.',
    type: 'debit_spread'
  },
  'Strong Downtrend': {
    name: 'Put Debit Spreads',
    description: 'Bearish strategy with capped risk and capped profit.',
    type: 'debit_spread'
  },
  'Range-bound': {
    name: 'Iron Condors',
    description: 'Neutral strategy profiting from theta decay in a range.',
    type: 'iron_condor'
  },
  'Volatility Expansion': {
    name: 'Long Straddles',
    description: 'Profits from large moves in either direction.',
    type: 'straddle'
  },
  'Volatility Compression': {
    name: 'Credit Spreads',
    description: 'Selling premium as volatility settles.',
    type: 'credit_spread'
  },
  'Event-driven': {
    name: 'Direction-neutral Vol Plays',
    description: 'Capitalizing on expected volatility around events.',
    type: 'vol_play'
  }
};