"""Import-boundary tests for the layered backend structure."""
import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]


def _imports_under(directory: str):
    root = BACKEND / directory
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                yield path, *(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                yield path, node.module.split(".")[0]


def test_core_does_not_depend_on_delivery_layers():
    forbidden = {"api", "application", "workers"}
    violations = [(path, module) for path, module in _imports_under("core") if module in forbidden]
    assert not violations, f"core imports delivery/application modules: {violations}"


def test_core_does_not_construct_market_data_providers():
    violations = [(path, module) for path, module in _imports_under("core") if module in {"data", "adapters"}]
    assert not violations, f"core imports market data infrastructure: {violations}"


def test_core_does_not_own_persistence_implementations():
    violations = [(path, module) for path, module in _imports_under("core") if module == "sqlite3"]
    assert not violations, f"core imports persistence implementation: {violations}"


def test_core_does_not_contain_broker_implementations():
    assert not (BACKEND / "core" / "paper_broker.py").exists()
    assert (BACKEND / "adapters" / "brokers" / "in_memory_paper.py").exists()


def test_adapters_do_not_depend_on_api_or_workers():
    forbidden = {"api", "workers"}
    violations = [(path, module) for path, module in _imports_under("adapters") if module in forbidden]
    assert not violations, f"adapter imports delivery modules: {violations}"


def test_ports_do_not_depend_on_provider_implementations():
    forbidden = {"data", "adapters", "api", "workers"}
    violations = [(path, module) for path, module in _imports_under("ports") if module in forbidden]
    assert not violations, f"ports import infrastructure or delivery modules: {violations}"


def test_application_does_not_depend_on_api_or_frontend():
    forbidden = {"api", "frontend"}
    violations = [(path, module) for path, module in _imports_under("application") if module in forbidden]
    assert not violations, f"application imports delivery modules: {violations}"


def test_paper_context_service_does_not_construct_external_adapters():
    path = BACKEND / "application" / "paper_context.py"
    imports = list(_imports_under("application"))
    violations = [(source, module) for source, module in imports
                  if source == path and module == "adapters"]
    assert not violations, f"paper context service imports adapters directly: {violations}"


def test_runtime_composition_lives_outside_application_layer():
    assert not (BACKEND / "application" / "paper_runtime.py").exists()
    assert (BACKEND / "workers" / "paper_runtime.py").exists()


def test_versioned_api_does_not_construct_external_adapters():
    path = BACKEND / "api" / "v1.py"
    violations = [(source, module) for source, module in _imports_under("api")
                  if source == path and module in {"adapters", "data"}]
    assert not violations, f"versioned API imports infrastructure adapters: {violations}"


def test_trading_api_does_not_construct_paper_repository():
    path = BACKEND / "api" / "trading.py"
    imports = list(_imports_under("api"))
    violations = [(source, module) for source, module in imports
                  if source == path and module == "core"]
    assert not violations, f"trading API imports persistence implementation: {violations}"


def test_market_data_api_does_not_construct_providers():
    path = BACKEND / "api" / "market_data.py"
    imports = list(_imports_under("api"))
    violations = [(source, module) for source, module in imports
                  if source == path and module in {"data", "adapters"}]
    assert not violations, f"market data API constructs providers: {violations}"


def test_backtest_api_does_not_construct_providers_or_engine():
    path = BACKEND / "api" / "backtest.py"
    imports = list(_imports_under("api"))
    violations = [(source, module) for source, module in imports
                  if source == path and module in {"core", "data", "adapters"}]
    assert not violations, f"backtest API constructs infrastructure: {violations}"


def test_portfolio_api_does_not_construct_providers_or_numeric_engine():
    path = BACKEND / "api" / "portfolio.py"
    imports = list(_imports_under("api"))
    violations = [(source, module) for source, module in imports
                  if source == path and module in {"data", "adapters", "numpy", "pandas"}]
    assert not violations, f"portfolio API constructs infrastructure: {violations}"


def test_screener_api_does_not_construct_core_engine():
    path = BACKEND / "api" / "screener.py"
    imports = list(_imports_under("api"))
    violations = [(source, module) for source, module in imports
                  if source == path and module in {"core", "data", "adapters"}]
    assert not violations, f"screener API constructs core engine: {violations}"


def test_api_layer_has_no_direct_domain_or_infrastructure_imports():
    forbidden = {"core", "data", "adapters"}
    violations = [(path, module) for path, module in _imports_under("api") if module in forbidden]
    assert not violations, f"API layer imports domain/infrastructure directly: {violations}"


def test_research_and_trading_apis_do_not_build_services_at_import_time():
    for name in ("market_data.py", "backtest.py", "portfolio.py", "screener.py", "trading.py", "v1.py"):
        tree = ast.parse((BACKEND / "api" / name).read_text(encoding="utf-8"))
        module_calls = [
            node for node in tree.body
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Call)
            and isinstance(node.value.value.func, ast.Name)
            and node.value.value.func.id == "get_container"
        ]
        assert not module_calls, f"{name} creates container services at import time"


def test_application_container_shares_market_data_service_with_research_services():
    from application.container import get_container

    container = get_container()
    assert container.backtests.market_data is container.market_data
    assert container.portfolio.market_data is container.market_data
    assert container.screener.market_data is container.market_data


def test_application_uses_domain_market_contract():
    for name in ("container.py", "market_data_service.py"):
        source = (BACKEND / "application" / name).read_text(encoding="utf-8")
        assert "data.providers.base" not in source


def test_provider_value_objects_live_in_domain_contracts():
    source = (BACKEND / "data" / "providers" / "base.py").read_text(encoding="utf-8")
    assert "class AssetInfo" not in source
    assert "class FundamentalData" not in source


def test_market_data_application_uses_port_contract():
    source = (BACKEND / "application" / "market_data_service.py").read_text(encoding="utf-8")
    assert "from ports.market_data import ResearchMarketDataProvider" in source
    assert "data.providers" not in source
    assert "Mapping[Market, ResearchMarketDataProvider]" in source


def test_account_application_services_do_not_construct_persistent_brokers():
    for name in ("account_query_service.py", "broker_query_service.py", "paper_trade_service.py"):
        source = (BACKEND / "application" / name).read_text(encoding="utf-8")
        assert "data.persistence" not in source


def test_legacy_paper_service_does_not_construct_storage_at_container_creation():
    source = (BACKEND / "application" / "container.py").read_text(encoding="utf-8")
    assert "PaperTradeService(paper_broker_factory)" in source
    assert "PaperTradeService(paper_broker_factory(" not in source


def test_paper_application_services_use_broker_port():
    for name in ("paper_execution.py", "paper_cycle.py"):
        source = (BACKEND / "application" / name).read_text(encoding="utf-8")
        assert "from ports.broker import" in source
        assert "broker: BrokerAdapter" in source


def test_paper_snapshot_uses_market_data_port():
    source = (BACKEND / "application" / "market_snapshot.py").read_text(encoding="utf-8")
    assert "from ports.market_data import PaperMarketDataAdapter" in source
    assert "data_adapter: PaperMarketDataAdapter" in source


def test_provider_contract_is_owned_by_ports():
    source = (BACKEND / "data" / "providers" / "base.py").read_text(encoding="utf-8")
    assert "class BaseProvider" not in source
    for name in ("krx_provider.py", "us_provider.py", "crypto_provider.py"):
        provider = (BACKEND / "data" / "providers" / name).read_text(encoding="utf-8")
        assert "from ports.research_provider import BaseProvider" in provider


def test_strategy_runtime_does_not_depend_on_backtest_engine():
    source = (BACKEND / "core" / "strategy_runtime.py").read_text(encoding="utf-8")
    assert "BacktestEngine" not in source
    assert "_generate_signals" not in source
