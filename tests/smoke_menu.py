import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / "bot.py"


def callback_literals(tree):
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "callback_data":
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                found.add(value.value)
    return found


def callback_branches(tree):
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            values = [node.left, *node.comparators]
            for value in values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    found.add(value.value)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            if text in {"home", "dashboard", "analysis", "markets", "signal", "timeframes", "leverage", "review", "stats", "paper", "risk", "health", "reports", "settings", "refresh", "help"}:
                found.add(text)
    return found


def main():
    source = BOT.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(BOT))
    assert any(isinstance(n, ast.FunctionDef) and n.name == "callback" for n in tree.body), "callback handler missing"
    assert any(isinstance(n, ast.FunctionDef) and n.name == "home_kb" for n in tree.body), "home keyboard missing"

    literals = callback_literals(tree)
    required = {"home", "analysis", "markets", "signal", "timeframes", "leverage", "review", "stats", "paper", "risk", "health", "reports", "settings", "refresh", "help"}
    missing = sorted(required - literals)
    assert not missing, f"home menu callbacks missing: {missing}"

    branches = callback_branches(tree)
    missing_branches = sorted(required - branches)
    assert not missing_branches, f"callback branches missing: {missing_branches}"

    # These must remain demonstrational only. The source must explicitly advertise
    # that real execution is disabled; no live order endpoint is allowed in this build.
    assert "Live execution: DISABLED" in source
    forbidden_markers = ("/order", "create_order", "place_order", "submit_order")
    for marker in forbidden_markers:
        assert marker not in source, f"live execution marker found: {marker}"

    print("Trading Guardian menu smoke test: PASS")


if __name__ == "__main__":
    main()
