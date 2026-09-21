"""Structural inspection helper for tomlkit containers.

Renders the internal ``Container._body`` / ``Container._map`` layout of a
parsed (or edited) document as deterministic text lines: semantic path, body
index, item type and a trivia summary.  No object addresses or default
``repr()`` output are included, so the output is stable across runs and
suitable for golden assertions in tests.
"""

from __future__ import annotations

from collections.abc import Iterator

from tomlkit.container import Container
from tomlkit.items import AoT
from tomlkit.items import InlineTable
from tomlkit.items import Item
from tomlkit.items import Key
from tomlkit.items import Table
from tomlkit.items import Whitespace


def _key_summary(key: Key | None) -> str:
    if key is None:
        return "-"
    flags = []
    if key.is_multi():
        flags.append("multi")
    if key.is_dotted():
        flags.append("dotted")
    suffix = f" ({', '.join(flags)})" if flags else ""
    return f"{key.as_string()}{suffix}"


def _trivia_summary(item: Item) -> str:
    trivia = item.trivia
    parts = []
    if trivia.indent:
        parts.append(f"indent={trivia.indent!r}")
    if trivia.comment_ws or trivia.comment:
        parts.append(f"comment_ws={trivia.comment_ws!r}")
        parts.append(f"comment={trivia.comment!r}")
    if trivia.trail != "\n":
        parts.append(f"trail={trivia.trail!r}")
    return " ".join(parts) if parts else "-"


def _item_summary(key: Key | None, item: Item) -> str:
    if isinstance(item, Whitespace):
        fixed = " fixed" if item.is_fixed() else ""
        return f"Whitespace{fixed} s={item.s!r}"
    name = type(item).__name__
    flags = []
    if isinstance(item, Table):
        if item.is_super_table():
            flags.append("super")
        if item.is_aot_element():
            flags.append("aot-element")
    suffix = f" ({', '.join(flags)})" if flags else ""
    return f"{name}{suffix} {_trivia_summary(item)}"


def _map_summary(container: Container, key: Key | None) -> str:
    if key is None:
        return "-"
    idx = container._map.get(key)
    if idx is None:
        return "-"
    if isinstance(idx, tuple):
        return "(" + ", ".join(str(i) for i in idx) + ")"
    return str(idx)


def iter_structure(container: Container, path: str = "") -> Iterator[str]:
    """Yield one line per body entry of ``container``, recursing into tables.

    Line format::

        <semantic path> | body[<idx>] | key=<key> | map=<idx|tuple|-> | <type and trivia>

    ``map`` is the entry's index in ``Container._map``; a tuple means the
    semantic key is shared by several body items and resolves through
    ``OutOfOrderTableProxy``.
    """
    for idx, (key, item) in enumerate(container.body):
        if key is None:
            entry_path = f"{path}." if path else ""
            entry_path += f"<no-key@{idx}>"
        else:
            entry_path = f"{path}.{key.key}" if path else key.key
        line = (
            f"{entry_path} | body[{idx}]"
            f" | key={_key_summary(key)}"
            f" | map={_map_summary(container, key)}"
            f" | {_item_summary(key, item)}"
        )
        yield line
        if isinstance(item, (Table, InlineTable)):
            yield from iter_structure(item.value, entry_path)
        elif isinstance(item, AoT):
            for elem_idx, elem in enumerate(item.body):
                elem_path = f"{entry_path}[{elem_idx}]"
                yield f"{elem_path} | aot-element | {_item_summary(None, elem)}"
                yield from iter_structure(elem.value, elem_path)


def describe(node: Container | Table) -> str:
    """Return the structural description of a document or table as text."""
    container = node.value if isinstance(node, Table) else node
    return "\n".join(iter_structure(container)) + "\n"
