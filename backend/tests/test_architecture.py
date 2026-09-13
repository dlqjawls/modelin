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


def test_adapters_do_not_depend_on_api_or_workers():
    forbidden = {"api", "workers"}
    violations = [(path, module) for path, module in _imports_under("adapters") if module in forbidden]
    assert not violations, f"adapter imports delivery modules: {violations}"


def test_application_does_not_depend_on_api_or_frontend():
    forbidden = {"api", "frontend"}
    violations = [(path, module) for path, module in _imports_under("application") if module in forbidden]
    assert not violations, f"application imports delivery modules: {violations}"
