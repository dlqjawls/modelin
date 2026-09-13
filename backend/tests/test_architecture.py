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


def test_application_container_shares_market_data_service_with_research_services():
    from application.container import get_container

    container = get_container()
    assert container.backtests.market_data is container.market_data
    assert container.portfolio.market_data is container.market_data
    assert container.screener.market_data is container.market_data
