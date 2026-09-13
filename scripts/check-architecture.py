"""Check backend import boundaries without running the application."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "backend"


def imports_under(directory: str):
    for path in (ROOT / directory).rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                yield path, *(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                yield path, node.module.split(".")[0]


def main() -> int:
    rules = {
        "core": {"api", "application", "workers", "data", "adapters"},
        "api": {"core", "data", "adapters"},
        "adapters": {"api", "workers"},
        "application": {"api", "frontend"},
        "ports": {"data", "adapters", "api", "workers"},
    }
    violations = []
    for layer, forbidden in rules.items():
        violations.extend(
            (path.relative_to(ROOT), module)
            for path, module in imports_under(layer)
            if module in forbidden
        )
    context_path = ROOT / "application" / "paper_context.py"
    if any(path == context_path and module == "adapters" for path, module in imports_under("application")):
        violations.append((context_path.relative_to(ROOT), "adapters"))
    if violations:
        for path, module in violations:
            print(f"boundary violation: {path} imports {module}")
        return 1
    print("architecture boundaries: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
