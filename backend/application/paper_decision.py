"""Pure application service for paper strategy decisions and order plans."""
from core.order_planner import OrderPlanner
from core.strategy_runtime import StrategyRuntime


class PaperDecisionService:
    def __init__(self, strategy_runtime=None):
        self.strategy_runtime = strategy_runtime or StrategyRuntime()

    def evaluate(self, close_prices, strategy, current_weights, cash_buffer):
        return self.strategy_runtime.evaluate(
            close_prices, strategy, current_weights, cash_buffer,
        )

    def plan_orders(self, *, cash, target_weights, positions, prices, nav, deployment):
        planner = OrderPlanner(
            cash_buffer=deployment.get("cash_buffer", "0.10"),
            max_asset_weight=deployment.get("max_asset_weight", "1"),
        )
        return planner.plan(
            cash=cash, target_weights=target_weights, positions=positions,
            prices=prices, nav=nav,
        )
