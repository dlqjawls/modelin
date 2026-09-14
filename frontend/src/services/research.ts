import { apiClient } from './client';
export type {
  AssetInfo, OHLCVItem, Quote, FundamentalData, ScreenerCondition, ScreenerResultItem,
  ScreenerResponse, BacktestConfig, BacktestResult, StrategyScore,
  PortfolioOptimizationResult,
} from '../contracts/research';
import type {
  AssetInfo, OHLCVItem, Quote, FundamentalData, ScreenerCondition, ScreenerResponse,
  BacktestConfig, BacktestResult, StrategyScore, PortfolioOptimizationResult,
} from '../contracts/research';

export const marketApi = {
  search: (q: string, market = 'krx') => apiClient.get<AssetInfo[]>('/api/market/search', { params: { q, market } }),
  getOHLCV: (symbol: string, market: string, start: string, end: string, interval = '1d') => apiClient.get<OHLCVItem[]>('/api/market/ohlcv', { params: { symbol, market, start, end, interval } }),
  getQuote: (symbol: string, market = 'krx') => apiClient.get<Quote>('/api/market/quote', { params: { symbol, market } }),
  getInfo: (symbol: string, market = 'krx') => apiClient.get<AssetInfo>('/api/market/info', { params: { symbol, market } }),
  getFundamental: (symbol: string, market = 'krx') => apiClient.get<FundamentalData>('/api/market/fundamental', { params: { symbol, market } }),
  getTickers: (market = 'krx') => apiClient.get<AssetInfo[]>('/api/market/tickers', { params: { market } }),
};

export const screenerApi = {
  run: (market: string, conditions: ScreenerCondition[], sortBy = 'market_cap', limit = 50) => apiClient.post<ScreenerResponse>('/api/screener/run', { market, conditions, sort_by: sortBy, sort_desc: true, limit }),
};

export const backtestApi = {
  run: (config: BacktestConfig) => apiClient.post<BacktestResult>('/api/backtest/run', config),
  compare: (config: Omit<BacktestConfig, 'strategy' | 'commission_rate' | 'slippage_rate' | 'rebalance_period'> & { strategies?: Record<string, unknown>[] }) => apiClient.post<StrategyScore[]>('/api/backtest/compare', config),
};

export const portfolioApi = {
  optimize: (body: { symbols: string[]; market: string; start_date: string; end_date: string; method: string }) => apiClient.post<PortfolioOptimizationResult>('/api/portfolio/optimize', body),
};
