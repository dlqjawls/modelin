/**
 * Modelin - API 서비스
 * 백엔드 API 통신 모듈
 */
import type { HealthResponse } from '../contracts/operations';
import { apiClient } from './client';
export { getApiErrorMessage } from './client';
export { operationsApi } from './operations';
export type { AccountSnapshotResponse, Deployment, DiagnosticsResponse, HealthResponse, LiveDiagnosticsResponse, PaperAccount } from '../contracts/operations';

// === Types ===

export interface AssetInfo {
  symbol: string;
  name: string;
  market: string;
  sector: string;
  market_cap: number;
  currency: string;
}

export interface OHLCVItem {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface FundamentalData {
  symbol: string;
  per: number | null;
  pbr: number | null;
  psr: number | null;
  eps: number | null;
  bps: number | null;
  roe: number | null;
  roa: number | null;
  dividend_yield: number | null;
  operating_margin: number | null;
  debt_ratio: number | null;
}

export interface ScreenerCondition {
  factor: string;
  operator: string;
  value: number;
}

export interface ScreenerResultItem {
  symbol: string;
  name: string;
  market: string;
  per: number | null;
  pbr: number | null;
  roe: number | null;
  eps: number | null;
  bps: number | null;
  market_cap: number;
  dividend_yield: number | null;
  operating_margin: number | null;
  sector: string;
}

export interface ScreenerResponse {
  results: ScreenerResultItem[];
  total_count: number;
  applied_conditions: ScreenerCondition[];
}

export interface BacktestConfig {
  symbols: string[];
  market: string;
  start_date: string;
  end_date: string;
  strategy: Record<string, unknown>;
  initial_capital: number;
  commission_rate: number;
  slippage_rate: number;
  rebalance_period: string;
}

export interface BacktestResult {
  total_return: number;
  cagr: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  win_rate: number;
  profit_loss_ratio: number;
  total_trades: number;
  equity_curve: { date: string; value: number }[];
  monthly_returns: { date: string; return: number }[];
}

export interface StrategyScore {
  strategy: Record<string, unknown>;
  total_return: number;
  cagr: number;
  sharpe_ratio: number;
  max_drawdown: number;
  total_trades: number;
  score: number;
}

export interface PortfolioOptimizationResult {
  weights: Record<string, number>;
  expected_return: number;
  expected_volatility: number;
  sharpe_ratio: number;
  efficient_frontier: { expected_return: number; volatility: number }[] | null;
}

// === Market Data API ===

export const marketApi = {
  search: (q: string, market: string = 'krx') =>
    apiClient.get<AssetInfo[]>('/api/market/search', { params: { q, market } }),

  getOHLCV: (symbol: string, market: string, start: string, end: string, interval: string = '1d') =>
    apiClient.get<OHLCVItem[]>('/api/market/ohlcv', { params: { symbol, market, start, end, interval } }),

  getInfo: (symbol: string, market: string = 'krx') =>
    apiClient.get<AssetInfo>('/api/market/info', { params: { symbol, market } }),

  getFundamental: (symbol: string, market: string = 'krx') =>
    apiClient.get<FundamentalData>('/api/market/fundamental', { params: { symbol, market } }),

  getTickers: (market: string = 'krx') =>
    apiClient.get<AssetInfo[]>('/api/market/tickers', { params: { market } }),
};

// === Screener API ===

export const screenerApi = {
  run: (market: string, conditions: ScreenerCondition[], sortBy: string = 'market_cap', limit: number = 50) =>
    apiClient.post<ScreenerResponse>('/api/screener/run', {
      market,
      conditions,
      sort_by: sortBy,
      sort_desc: true,
      limit,
    }),
};

// === Backtest API ===

export const backtestApi = {
  run: (config: BacktestConfig) =>
    apiClient.post<BacktestResult>('/api/backtest/run', config),
  compare: (config: Omit<BacktestConfig, 'strategy' | 'commission_rate' | 'slippage_rate' | 'rebalance_period'> & { strategies?: Record<string, unknown>[] }) =>
    apiClient.post<StrategyScore[]>('/api/backtest/compare', config),
};

export const portfolioApi = {
  optimize: (body: { symbols: string[]; market: string; start_date: string; end_date: string; method: string }) =>
    apiClient.post<PortfolioOptimizationResult>('/api/portfolio/optimize', body),
};

// === Health Check ===

export const healthCheck = () => apiClient.get<HealthResponse>('/api/health');

export { apiClient as default };
