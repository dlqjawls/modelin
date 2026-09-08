"""
Modelin - 백테스팅 API 라우터
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.backtester import BacktestEngine, BacktestConfig, BacktestResult

router = APIRouter(prefix="/api/backtest", tags=["Backtest"])

_engine = BacktestEngine()


class BacktestRequest(BaseModel):
    """백테스팅 요청"""
    symbols: list[str]
    market: str = "krx"
    start_date: str
    end_date: str
    strategy: dict  # 전략 설정
    initial_capital: float = 10_000_000
    commission_rate: float = 0.00015  # 0.015%
    slippage_rate: float = 0.001     # 0.1%
    rebalance_period: str = "1M"     # 리밸런싱 주기


class BacktestResponse(BaseModel):
    """백테스팅 결과"""
    total_return: float
    cagr: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    profit_loss_ratio: float
    total_trades: int
    equity_curve: list[dict]
    monthly_returns: list[dict]
    benchmark_comparison: dict | None = None


@router.post("/run", response_model=BacktestResponse)
async def run_backtest(request: BacktestRequest):
    """백테스팅 실행"""
    try:
        config = BacktestConfig(
            symbols=request.symbols,
            market=request.market,
            start_date=request.start_date,
            end_date=request.end_date,
            strategy=request.strategy,
            initial_capital=request.initial_capital,
            commission_rate=request.commission_rate,
            slippage_rate=request.slippage_rate,
            rebalance_period=request.rebalance_period,
        )

        result = await _engine.run(config)

        return BacktestResponse(
            total_return=result.total_return,
            cagr=result.cagr,
            sharpe_ratio=result.sharpe_ratio,
            sortino_ratio=result.sortino_ratio,
            max_drawdown=result.max_drawdown,
            win_rate=result.win_rate,
            profit_loss_ratio=result.profit_loss_ratio,
            total_trades=result.total_trades,
            equity_curve=result.equity_curve,
            monthly_returns=result.monthly_returns,
            benchmark_comparison=result.benchmark_comparison,
        )
    except Exception as e:
        raise HTTPException(500, f"백테스팅 실패: {str(e)}")
