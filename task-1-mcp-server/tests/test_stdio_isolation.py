"""Static safeguard: fail the suite if any source file calls print().

stdout is reserved exclusively for JSON-RPC traffic (see server.py's module
docstring). A stray print() anywhere in the server's import graph would leak
into stdout and corrupt the protocol stream, so this is checked statically
in addition to the runtime check in test_server_stdio.py.
"""

import ast
from pathlib import Path

import pytest

SOURCE_DIR = Path(__file__).resolve().parent.parent
SOURCE_FILES = [
    p for p in SOURCE_DIR.glob("*.py") if p.is_file() and p.name != "conftest.py"
]


def _print_call_lines(source_path: Path) -> list[int]:
    tree = ast.parse(source_path.read_text(), filename=str(source_path))
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            is_print = isinstance(func, ast.Name) and func.id == "print"
            if is_print:
                lines.append(node.lineno)
    return lines


@pytest.mark.parametrize("source_path", SOURCE_FILES, ids=lambda p: p.name)
def test_no_print_calls(source_path):
    offending_lines = _print_call_lines(source_path)
    assert not offending_lines, (
        f"{source_path.name} calls print() at line(s) {offending_lines}; "
        "use the `logger` (stderr) instead, stdout must stay pure JSON-RPC"
    )
