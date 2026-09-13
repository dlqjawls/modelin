/**
 * Modelin - API 서비스
 * 백엔드 API 통신 모듈
 */
import axios, { AxiosError, type AxiosRequestConfig } from 'axios';
import type { AccountSnapshotResponse, Deployment, DiagnosticsResponse, HealthResponse, LiveDiagnosticsResponse, PaperAccount } from '../contracts/operations';
export type { AccountSnapshotResponse, Deployment, DiagnosticsResponse, HealthResponse, LiveDiagnosticsResponse, PaperAccount } from '../contracts/operations';

const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export function getApiErrorMessage(error: unknown, fallback = 'API 요청에 실패했습니다.'): string {
  if (axios.isCancel(error)) return '요청이 취소되었습니다.';
  if (error instanceof AxiosError) {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string' && detail) return detail;
    if (error.response?.status) return `API 요청 실패 (${error.response.status})`;
    if (error.message) return error.message;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

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
    api.get<AssetInfo[]>('/api/market/search', { params: { q, market } }),

  getOHLCV: (symbol: string, market: string, start: string, end: string, interval: string = '1d') =>
    api.get<OHLCVItem[]>('/api/market/ohlcv', { params: { symbol, market, start, end, interval } }),

  getInfo: (symbol: string, market: string = 'krx') =>
    api.get<AssetInfo>('/api/market/info', { params: { symbol, market } }),

  getFundamental: (symbol: string, market: string = 'krx') =>
    api.get<FundamentalData>('/api/market/fundamental', { params: { symbol, market } }),

  getTickers: (market: string = 'krx') =>
    api.get<AssetInfo[]>('/api/market/tickers', { params: { market } }),
};

// === Screener API ===

export const screenerApi = {
  run: (market: string, conditions: ScreenerCondition[], sortBy: string = 'market_cap', limit: number = 50) =>
    api.post<ScreenerResponse>('/api/screener/run', {
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
    api.post<BacktestResult>('/api/backtest/run', config),
  compare: (config: Omit<BacktestConfig, 'strategy' | 'commission_rate' | 'slippage_rate' | 'rebalance_period'> & { strategies?: Record<string, unknown>[] }) =>
    api.post<StrategyScore[]>('/api/backtest/compare', config),
};

export const portfolioApi = {
  optimize: (body: { symbols: string[]; market: string; start_date: string; end_date: string; method: string }) =>
    api.post<PortfolioOptimizationResult>('/api/portfolio/optimize', body),
};

// === Health Check ===

export const healthCheck = () => api.get<HealthResponse>('/api/health');

export const operationsApi = {
  accounts: () => api.get<PaperAccount[]>('/api/v1/accounts'),
  deployments: () => api.get<Deployment[]>('/api/v1/deployments'),
  createPaperAccount: (body: { name: string; market: string; currency: string; initial_cash: string }) =>
    api.post<PaperAccount>('/api/v1/accounts/paper', body),
  snapshot: (accountId: string, config?: AxiosRequestConfig) => api.get<AccountSnapshotResponse>(`/api/v1/accounts/${accountId}/snapshot`, config),
  deployment: (id: string) => api.get<Deployment>(`/api/v1/deployments/${id}`),
  command: (id: string, type: 'START' | 'PAUSE' | 'CANCEL_OPEN' | 'LIQUIDATE' | 'RESUME' | 'ARCHIVE') =>
    api.post<Deployment>(`/api/v1/deployments/${id}/commands`, { type, reason: `UI:${type}` }),
  diagnostics: () => api.get<DiagnosticsResponse>('/api/v1/diagnostics'),
  liveDiagnostics: () => api.get<LiveDiagnosticsResponse>('/api/v1/diagnostics/live'),
};

export default api;
