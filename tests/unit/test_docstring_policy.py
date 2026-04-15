"""Docstring policy enforcement for runtime modules."""

from __future__ import annotations

import ast
from pathlib import Path


def _python_files() -> list[Path]:
    root = Path(__file__).resolve().parents[2]
    files: list[Path] = []
    for base in (root / "src", root / "apps"):
        files.extend(path for path in base.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(files)


def _missing_docstrings(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    failures: list[str] = []
    if ast.get_docstring(tree, clean=False) is None:
        failures.append("module docstring missing")

    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False) is None:
                node_type = node.__class__.__name__.replace("Def", "").lower()
                failures.append(f"{node_type} '{node.name}' missing docstring")
    return failures


def test_docstring_policy_all_runtime_modules() -> None:
    """Enforce module/class/function docstrings under src and apps."""
    failures: list[str] = []
    for path in _python_files():
        missing = _missing_docstrings(path)
        if missing:
            rel = path.as_posix()
            failures.extend(f"{rel}: {item}" for item in missing)

    assert not failures, "Docstring policy violations:\n" + "\n".join(failures)
