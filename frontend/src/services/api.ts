/**
 * Modelin - API 서비스
 * 백엔드 API 통신 모듈
 */
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

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
};

// === Health Check ===

export const healthCheck = () => api.get('/api/health');

export interface PaperAccount {
  id: string;
  name: string;
  mode: 'paper';
  market: string;
  currency: string;
  initial_cash: string;
  status: string;
}

export interface Deployment {
  id: string;
  account_id: string;
  mode: 'paper';
  strategy: Record<string, unknown>;
  desired_state: string;
  observed_state: string;
  revision: number;
  pause_epoch: number;
}

export const operationsApi = {
  accounts: () => api.get<PaperAccount[]>('/api/v1/accounts'),
  deployments: () => api.get<Deployment[]>('/api/v1/deployments'),
  createPaperAccount: (body: { name: string; market: string; currency: string; initial_cash: string }) =>
    api.post<PaperAccount>('/api/v1/accounts/paper', body),
  snapshot: (accountId: string) => api.get(`/api/v1/accounts/${accountId}/snapshot`),
  deployment: (id: string) => api.get<Deployment>(`/api/v1/deployments/${id}`),
  command: (id: string, type: 'START' | 'PAUSE' | 'CANCEL_OPEN' | 'LIQUIDATE' | 'RESUME' | 'ARCHIVE') =>
    api.post(`/api/v1/deployments/${id}/commands`, { type, reason: `UI:${type}` }),
  diagnostics: () => api.get('/api/v1/diagnostics'),
};

export default api;
