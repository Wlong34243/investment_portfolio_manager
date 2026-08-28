import ast
from pathlib import Path


def test_no_sql_execution_path_in_analyst_modules():
    """Structural: analyst modules must not execute SQL from model output."""
    root = Path("core/analyst")
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "execute":
                    raise AssertionError(f"{path} contains execute() call")
