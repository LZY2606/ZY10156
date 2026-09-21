"""Structural inspection helper for tomlkit documents.

Reports, for every container reached from a parsed document:

* the semantic path of each body entry (``a.b.c`` / ``products[1].name``),
* the physical body index the entry occupies,
* the concrete item class name,
* a compact trivia summary (indentation / comment spacing / comment / trail),

and the container's ``_map`` index mapping (an ``int`` for an ordinary key,
a tuple for an out-of-order table aggregated by
``tomlkit.container.OutOfOrderTableProxy``).

No object identity / address is ever printed, so the output is stable enough
to pin in tests.
"""

from __future__ import annotations

from dataclasses import dataclass

from tomlkit.container import Container
from tomlkit.container import OutOfOrderTableProxy
from tomlkit.items import AoT
from tomlkit.items import InlineTable
from tomlkit.items import Item
from tomlkit.items import Table
from tomlkit.items import Whitespace
from tomlkit.toml_document import TOMLDocument


def _escape(raw: str) -> str:
    """Render a whitespace/trivia string as an unambiguous, single-line token."""
    return raw.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def trivia_summary(item: Item) -> str:
    """Return a single-line ``key=value`` summary of an item's trivia.

    ``Whitespace`` has no :class:`~tomlkit.items.Trivia`; it renders its raw
    string plus its ``fixed`` flag instead.
    """
    if isinstance(item, Whitespace):
        return f"whitespace={_escape(item.s)!r} fixed={item.is_fixed()}"
    t = item.trivia
    return (
        f"indent={_escape(t.indent)!r} cws={_escape(t.comment_ws)!r} "
        f"comment={_escape(t.comment)!r} trail={_escape(t.trail)!r}"
    )


@dataclass(frozen=True)
class BodyRow:
    """One physical ``(key, item)`` slot of a :class:`Container` body."""

    index: int
    path: str
    key: str | None
    dotted: bool | None
    item_type: str
    trivia: str

    def as_line(self) -> str:
        return (
            f"[{self.index}] {self.path} :: {self.item_type} "
            f"dotted={self.dotted} :: {self.trivia}"
        )


@dataclass(frozen=True)
class ContainerView:
    """Flat description of one container and its map index."""

    path: str
    kind: str
    rows: tuple[BodyRow, ...]
    map_index: tuple[tuple[str, str, bool], ...]

    def render(self) -> str:
        lines = [f"{self.kind} {self.path or '<root>'}"]
        lines.append(
            "  map: "
            + (
                ", ".join(
                    f"{name} -> {index} (dotted={dotted})"
                    for name, index, dotted in self.map_index
                )
                or "{}"
            )
        )
        lines.extend("  " + row.as_line() for row in self.rows)
        return "\n".join(lines)


def _join(path: str, segment: str) -> str:
    return f"{path}.{segment}" if path else segment


def describe_container(
    container: Container, path: str = "", kind: str = "Container"
) -> list[ContainerView]:
    """Recursively describe ``container`` and every nested table/AoT container.

    The traversal follows the physical ``body`` order, which is exactly the
    serialization order.  Out-of-order fragments therefore appear more than
    once (one row per physical slot); the ``_map`` tuple records all of them.
    """
    rows: list[BodyRow] = []
    views: list[ContainerView] = []
    for index, (key, item) in enumerate(container.body):
        key_str = str(key).strip() if key is not None else None
        dotted = key.is_dotted() if key is not None else None
        if key_str is None:
            row_path = f"{path}#body{index}"
        else:
            row_path = _join(path, key_str)
        rows.append(
            BodyRow(
                index=index,
                path=row_path,
                key=key_str,
                dotted=dotted,
                item_type=type(item).__name__,
                trivia=trivia_summary(item),
            )
        )
        if isinstance(item, Table):
            views.extend(
                describe_container(
                    item.value,
                    row_path,
                    f"Table(super={item.is_super_table()},aot_element={item.is_aot_element()})",
                )
            )
        elif isinstance(item, InlineTable):
            views.extend(
                describe_container(item.value, row_path, "InlineTable")
            )
        elif isinstance(item, AoT):
            for element_index, element in enumerate(item.body):
                views.extend(
                    describe_container(
                        element.value,
                        f"{row_path}[{element_index}]",
                        "AoTElement",
                    )
                )

    map_index = tuple(
        (
            str(k).strip(),
            repr(v) if isinstance(v, tuple) else str(v),
            k.is_dotted(),
        )
        for k, v in container._map.items()
    )
    views.insert(0, ContainerView(path=path, kind=kind, rows=tuple(rows), map_index=map_index))
    return views


def describe_document(document: TOMLDocument) -> list[ContainerView]:
    """Describe a parsed :class:`TOMLDocument` from its root container."""
    return describe_container(document, path="", kind="TOMLDocument")


def structure_text(document: TOMLDocument) -> str:
    """Human-readable dump used both for debugging and for byte-stable tests."""
    return "\n".join(view.render() for view in describe_document(document))


def map_of(container: Container) -> dict[str, int | tuple[int, ...]]:
    """Plain ``{semantic key: body index(s)}`` copy of a container's ``_map``."""
    return {str(k).strip(): v for k, v in container._map.items()}


def body_index(container: Container, semantic_key: str) -> int | tuple[int, ...]:
    """Return the body index (or tuple for out-of-order tables) for one key."""
    return map_of(container)[semantic_key]


def body_types(container: Container) -> list[tuple[str | None, str]]:
    """``[(key-or-None, item class name), ...]`` in physical body order."""
    return [
        (str(k).strip() if k is not None else None, type(v).__name__)
        for k, v in container.body
    ]


def out_of_order_proxy(document: TOMLDocument, semantic_key: str) -> OutOfOrderTableProxy:
    """Fetch the aggregating proxy for an out-of-order semantic key."""
    proxy = document.item(semantic_key)
    if not isinstance(proxy, OutOfOrderTableProxy):
        raise TypeError(f"{semantic_key!r} is not an out-of-order table")
    return proxy


__all__ = [
    "BodyRow",
    "ContainerView",
    "body_index",
    "body_types",
    "describe_container",
    "describe_document",
    "map_of",
    "out_of_order_proxy",
    "structure_text",
    "trivia_summary",
]
