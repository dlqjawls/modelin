export interface AssetInfo { symbol: string; name: string; market: string; sector: string; market_cap: number; currency: string; }
export interface OHLCVItem { date: string; open: number; high: number; low: number; close: number; volume: number; }
export interface Quote { symbol: string; market: string; source: string; price: number | null; change: number | null; change_rate: number | null; }
export interface FundamentalData { symbol: string; per: number | null; pbr: number | null; psr: number | null; eps: number | null; bps: number | null; roe: number | null; roa: number | null; dividend_yield: number | null; operating_margin: number | null; debt_ratio: number | null; }
export interface ScreenerCondition { factor: string; operator: string; value: number; }
export interface ScreenerResultItem { symbol: string; name: string; market: string; per: number | null; pbr: number | null; roe: number | null; eps: number | null; bps: number | null; market_cap: number; dividend_yield: number | null; operating_margin: number | null; sector: string; }
export interface ScreenerResponse { results: ScreenerResultItem[]; total_count: number; applied_conditions: ScreenerCondition[]; }
export interface BacktestConfig { symbols: string[]; market: string; start_date: string; end_date: string; strategy: Record<string, unknown>; initial_capital: number; commission_rate: number; slippage_rate: number; rebalance_period: string; }
export interface BacktestResult { total_return: number; cagr: number; sharpe_ratio: number; sortino_ratio: number; max_drawdown: number; win_rate: number; profit_loss_ratio: number; total_trades: number; equity_curve: { date: string; value: number }[]; monthly_returns: { date: string; return: number }[]; }
export interface StrategyScore { strategy: Record<string, unknown>; total_return: number; cagr: number; sharpe_ratio: number; max_drawdown: number; total_trades: number; score: number; }
export interface PortfolioOptimizationResult { weights: Record<string, number>; expected_return: number; expected_volatility: number; sharpe_ratio: number; efficient_frontier: { expected_return: number; volatility: number }[] | null; }
