export type MarketRegion = 'US' | 'IN' | 'FX' | 'CRYPTO' | 'COMMODITY';

export interface MarketConfig {
    id: string;
    name: string;
    region: MarketRegion;
    ticker: string; // Yahoo Finance Ticker
    currency: string;
    locale: string;
    description?: string;
}

export const MARKET_CATEGORIES = [
    { id: 'indices', name: 'Global Indices', icon: 'Globe' },
    { id: 'crypto', name: 'Digital Assets (24/7)', icon: 'Cpu' },
    { id: 'forex', name: 'Currencies', icon: 'Coins' },
    { id: 'commodities', name: 'Commodities', icon: 'HardHat' }
];

export const MARKETS: MarketConfig[] = [
    // INDICES
    {
        id: 'nifty',
        name: 'NIFTY 50',
        region: 'IN',
        ticker: '^NSEI',
        currency: 'INR',
        locale: 'en-IN',
        description: 'NSE India Benchmark'
    },
    {
        id: 'spx',
        name: 'S&P 500',
        region: 'US',
        ticker: '^GSPC',
        currency: 'USD',
        locale: 'en-US',
        description: 'US Large Cap Index'
    },
    // CRYPTO
    {
        id: 'btc',
        name: 'Bitcoin',
        region: 'CRYPTO',
        ticker: 'BTC-USD',
        currency: 'USD',
        locale: 'en-US',
        description: 'Store of Value'
    },
    {
        id: 'eth',
        name: 'Ethereum',
        region: 'CRYPTO',
        ticker: 'ETH-USD',
        currency: 'USD',
        locale: 'en-US',
        description: 'Smart Contract Platform'
    },
    // FOREX
    {
        id: 'eurusd',
        name: 'EUR/USD',
        region: 'FX',
        ticker: 'EURUSD=X',
        currency: 'USD',
        locale: 'en-US',
        description: 'Euro vs Dollar'
    },
    {
        id: 'usdjpy',
        name: 'USD/JPY',
        region: 'FX',
        ticker: 'USDJPY=X',
        currency: 'JPY',
        locale: 'ja-JP',
        description: 'Dollar vs Yen'
    },
    {
        id: 'gbpusd',
        name: 'GBP/USD',
        region: 'FX',
        ticker: 'GBPUSD=X',
        currency: 'USD',
        locale: 'en-US',
        description: 'Pound vs Dollar'
    },
    // COMMODITIES
    {
        id: 'gold',
        name: 'Gold (XAU/USD)',
        region: 'COMMODITY',
        ticker: 'GC=F',
        currency: 'USD',
        locale: 'en-US',
        description: 'Safe Haven Asset'
    },
    {
        id: 'silver',
        name: 'Silver',
        region: 'COMMODITY',
        ticker: 'SI=F',
        currency: 'USD',
        locale: 'en-US',
        description: 'Industrial Precious Metal'
    }
];

export function formatCurrency(value: number, region: MarketRegion = 'US'): string {
    const config = MARKETS.find(m => m.region === region) || MARKETS.find(m => m.region === 'US')!;
    const numValue = typeof value === 'number' ? value : parseFloat(value as any);

    if (isNaN(numValue)) return region === 'IN' ? '₹0.00' : '$0.00';

    // Forex and Commodities often need more precision
    const precision = (region === 'FX') ? 4 : (region === 'CRYPTO' ? 2 : 2);

    return new Intl.NumberFormat(config.locale, {
        style: 'currency',
        currency: config.currency,
        minimumFractionDigits: precision,
        maximumFractionDigits: precision
    }).format(numValue);
}

export function getMarketByRegion(region: MarketRegion): MarketConfig {
    return MARKETS.find(m => m.region === region) || MARKETS[0];
}
