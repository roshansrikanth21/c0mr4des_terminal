export type MarketRegion = 'US' | 'IN';

export interface MarketConfig {
    id: string;
    name: string;
    region: MarketRegion;
    ticker: string; // Yahoo Finance Ticker
    currency: string;
    locale: string;
}

export const MARKETS: MarketConfig[] = [
    {
        id: 'nifty',
        name: 'NIFTY 50',
        region: 'IN',
        ticker: '^NSEI',
        currency: 'INR',
        locale: 'en-IN'
    },
    {
        id: 'spx',
        name: 'S&P 500',
        region: 'US',
        ticker: '^GSPC', // Standard S&P 500 ticker
        currency: 'USD',
        locale: 'en-US'
    }
];

export function formatCurrency(value: number, region: MarketRegion = 'US'): string {
    const config = MARKETS.find(m => m.region === region) || MARKETS[1]; // Default to US
    const numValue = typeof value === 'number' ? value : parseFloat(value as any);

    if (isNaN(numValue)) return '₹0.00';

    return new Intl.NumberFormat(config.locale, {
        style: 'currency',
        currency: config.currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(numValue);
}

export function getMarketByRegion(region: MarketRegion): MarketConfig {
    return MARKETS.find(m => m.region === region) || MARKETS[1];
}
