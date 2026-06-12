"""Build compact Python signature packs for agent code-generation context."""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path
from typing import Iterable, Sequence


def build_context_pack(paths: Iterable[str | Path], include_private: bool = False) -> dict:
    """Return class/function signatures for parseable Python files.

    Files that cannot be read or parsed are listed in ``skipped`` and do not
    abort the pack build.
    """
    files = []
    skipped = []

    for raw_path in paths:
        path_text = str(raw_path)
        path = Path(raw_path)
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=path_text, type_comments=True)
        except (OSError, SyntaxError, UnicodeDecodeError):
            skipped.append(path_text)
            continue

        classes = []
        functions = []
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                if _filtered(node.name, include_private):
                    continue
                classes.append(_class_entry(node, source, include_private))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if _filtered(node.name, include_private):
                    continue
                functions.append(_callable_entry(node, source))

        files.append({
            "path": path_text,
            "classes": classes,
            "functions": functions,
        })

    return {"files": files, "skipped": skipped}


def _class_entry(node: ast.ClassDef, source: str, include_private: bool) -> dict:
    methods = []
    for child in node.body:
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if _filtered(child.name, include_private):
            continue
        methods.append(_callable_entry(child, source))
    return {"name": node.name, "methods": methods}


def _callable_entry(node: ast.FunctionDef | ast.AsyncFunctionDef, source: str) -> dict:
    docstring = ast.get_docstring(node) or ""
    return {
        "name": node.name,
        "signature": _signature_text(node, source),
        "doc_first_line": docstring.splitlines()[0] if docstring else "",
    }


def _filtered(name: str, include_private: bool) -> bool:
    return not include_private and _is_private(name)


def _is_private(name: str) -> bool:
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def _signature_text(node: ast.FunctionDef | ast.AsyncFunctionDef, source: str) -> str:
    segment = ast.get_source_segment(source, node)
    if not segment:
        return ""

    try:
        return _signature_from_segment(segment)
    except (tokenize.TokenError, IndentationError):
        return ""


def _signature_from_segment(segment: str) -> str:
    starts = _line_starts(segment)
    tokens = tokenize.generate_tokens(io.StringIO(segment).readline)

    open_start = None
    close_end = None
    depth = 0
    token_iter = iter(tokens)

    for token in token_iter:
        if token.type != tokenize.OP:
            continue
        if token.string == "(":
            open_start = _index(starts, token.start)
            depth = 1
            break

    if open_start is None:
        return ""

    for token in token_iter:
        if token.type != tokenize.OP:
            continue
        if token.string in "([{":
            depth += 1
        elif token.string in ")]}":
            depth -= 1
            if depth == 0:
                close_end = _index(starts, token.end)
                break

    if close_end is None:
        return ""

    colon_start = None
    tail_depth = 0
    for token in token_iter:
        if token.type != tokenize.OP:
            continue
        if token.string in "([{":
            tail_depth += 1
        elif token.string in ")]}":
            tail_depth -= 1
        elif token.string == ":" and tail_depth == 0:
            colon_start = _index(starts, token.start)
            break

    if colon_start is None:
        return segment[open_start:close_end].rstrip()
    return (segment[open_start:close_end] + segment[close_end:colon_start]).rstrip()


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return starts


def _index(line_starts: Sequence[int], position: tuple[int, int]) -> int:
    row, column = position
    return line_starts[row - 1] + column
