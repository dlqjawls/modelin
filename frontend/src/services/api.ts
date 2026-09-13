/** Backward-compatible facade for the frontend API services. */
import { apiClient } from './client';
import { operationsApi } from './operations';

export { getApiErrorMessage } from './errors';
export { operationsApi } from './operations';
export { marketApi, screenerApi, backtestApi, portfolioApi } from './research';
export type {
  AssetInfo, OHLCVItem, FundamentalData, ScreenerCondition, ScreenerResultItem,
  ScreenerResponse, BacktestConfig, BacktestResult, StrategyScore, PortfolioOptimizationResult,
} from './research';
export type { AccountSnapshotResponse, Deployment, DiagnosticsResponse, HealthResponse, LiveDiagnosticsResponse, PaperAccount } from '../contracts/operations';

export const healthCheck = operationsApi.health;
export { apiClient as default };
