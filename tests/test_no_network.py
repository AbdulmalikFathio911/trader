"""Fail if any .py file in the repository imports a network or broker module.

The trade desk must work from screenshots and typed numbers only. This test
parses every Python file and rejects imports of the modules listed below.
"""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules"}

FORBIDDEN = (
    "requests",
    "anthropic",
    "openai",
    "MetaTrader5",
    "socket",
    "http.client",
    "urllib.request",
)


def python_files():
    for path in sorted(ROOT.rglob("*.py")):
        if not SKIP_DIRS.intersection(path.relative_to(ROOT).parts):
            yield path


def is_forbidden(module):
    return any(module == name or module.startswith(name + ".") for name in FORBIDDEN)


def imported_modules(tree):
    """Yield (line, module) for every module a file imports, by any route."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            yield node.lineno, base
            for alias in node.names:  # "from urllib import request"
                yield node.lineno, f"{base}.{alias.name}" if base else alias.name
        elif isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name in ("__import__", "import_module") and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    yield node.lineno, first.value


def violations(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        f"{path.relative_to(ROOT)}:{line} imports {module}"
        for line, module in imported_modules(tree)
        if is_forbidden(module)
    ]


class TestNoNetwork(unittest.TestCase):
    def test_repo_has_python_files(self):
        names = {path.name for path in python_files()}
        self.assertIn("calc.py", names)
        self.assertIn("position_sizer.py", names)

    def test_no_forbidden_imports(self):
        found = [item for path in python_files() for item in violations(path)]
        self.assertEqual(found, [], "forbidden imports:\n" + "\n".join(found))

    def test_detector_catches_each_forbidden_module(self):
        samples = (
            "import requests",
            "import anthropic",
            "from openai import OpenAI",
            "import MetaTrader5 as mt5",
            "import socket",
            "import http.client",
            "from http import client",
            "import urllib.request",
            "from urllib import request",
            "from urllib.request import urlopen",
            "__import__('socket')",
            "import importlib\nimportlib.import_module('requests')",
        )
        for source in samples:
            hits = [m for _, m in imported_modules(ast.parse(source)) if is_forbidden(m)]
            self.assertTrue(hits, f"not detected: {source}")

    def test_detector_allows_standard_arithmetic_modules(self):
        source = "import json\nimport decimal\nfrom urllib import parse\nimport http\n"
        hits = [m for _, m in imported_modules(ast.parse(source)) if is_forbidden(m)]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
