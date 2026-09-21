"""Tests pinning how the parser organizes items into ``Container`` and how
edits are serialized back.

These tests intentionally reach into ``Container._body`` / ``Container._map``
(through ``tests.structure_helper``) to fix the mapping between semantic keys
and body positions; they are about the library's current internal behavior,
not about the TOML spec alone.
"""

from __future__ import annotations

from typing import Any

import pytest

import tomlkit

from tomlkit.container import OutOfOrderTableProxy
from tomlkit.exceptions import KeyAlreadyPresent
from tomlkit.exceptions import ParseError
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import AoT
from tomlkit.items import Key
from tomlkit.items import Table
from tomlkit.items import Trivia
from tomlkit.parser import Parser

from tests.structure_helper import describe


# Minimal document combining a dotted key (``a.b = 1`` inside ``[server]``), a
# later ``[a]`` header, an array of tables, an inline table, a trailing
# comment on the same line as an item, and blank lines.
#
# Note: ``a.b = 1`` cannot live at the root together with a later root-level
# ``[a]`` header -- the dotted key already defines ``a`` (TOML 1.0, "table"
# section), and tomlkit rejects that input with "Redefinition of an existing
# table".  Nesting the dotted key under ``[server]`` keeps the document valid.
DOC = """\
[server]
a.b = 1  # dotted leaf

[server.opts]
mode = {fast = true, retries = 3}

[[products]]
name = "alpha"

[[products]]
name = "beta"

[a]
value = 42
"""

EXPECTED_STRUCTURE = """\
server | body[0] | key=server | map=0 | Table -
server.a | body[0] | key=a (dotted) | map=0 | Table (super) -
server.a.b | body[0] | key=b  | map=0 | Integer comment_ws='  ' comment='# dotted leaf'
server.<no-key@1> | body[1] | key=- | map=- | Whitespace s='\\n'
server.opts | body[2] | key=opts | map=2 | Table -
server.opts.mode | body[0] | key=mode  | map=0 | InlineTable -
server.opts.mode.fast | body[0] | key=fast  | map=0 | Bool trail=''
server.opts.mode.<no-key@1> | body[1] | key=- | map=- | Whitespace s=','
server.opts.mode.<no-key@2> | body[2] | key=- | map=- | Whitespace s=' '
server.opts.mode.retries | body[3] | key=retries  | map=3 | Integer trail=''
server.opts.<no-key@1> | body[1] | key=- | map=- | Whitespace s='\\n'
products | body[1] | key=products | map=1 | AoT trail=''
products[0] | aot-element | Table (aot-element) -
products[0].name | body[0] | key=name  | map=0 | String -
products[0].<no-key@1> | body[1] | key=- | map=- | Whitespace s='\\n'
products[1] | aot-element | Table (aot-element) -
products[1].name | body[0] | key=name  | map=0 | String -
products[1].<no-key@1> | body[1] | key=- | map=- | Whitespace s='\\n'
a | body[2] | key=a | map=2 | Table -
a.value | body[0] | key=value  | map=0 | Integer -
"""

EXPECTED_TRACE = [
    # (event, key, extra) -- see _tracing_parser below
    ("enter_table", None, 0),
    ("enter_table", "server", 0),  # [server.opts] is a child of [server]
    ("exit_table", "opts", 0),
    ("exit_table", "server", 0),
    ("enter_table", None, 0),  # first [[products]] element
    ("enter_aot", "products", None),
    ("enter_table", "products", 1),  # second element, _aot_stack == ["products"]
    ("exit_table", "products", 1),
    ("exit_aot", "products", 2),  # AoT collected 2 elements
    ("exit_table", "products", 0),
    ("enter_table", None, 0),
    ("exit_table", "a", 0),
]


def _tracing_parser(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    events: list[tuple[Any, ...]] = []
    original_table = Parser._parse_table
    original_aot = Parser._parse_aot

    def traced_table(
        self: Parser,
        parent_name: Key | None = None,
        parent: Table | None = None,
    ) -> tuple[Key, Table | AoT]:
        events.append(
            (
                "enter_table",
                parent_name.as_string() if parent_name else None,
                len(self._aot_stack),
            )
        )
        key, value = original_table(self, parent_name, parent)
        events.append(("exit_table", key.as_string(), len(self._aot_stack)))
        return key, value

    def traced_aot(self: Parser, first: Table, name_first: Key) -> AoT:
        events.append(("enter_aot", name_first.as_string(), None))
        result = original_aot(self, first, name_first)
        events.append(("exit_aot", name_first.as_string(), len(result.body)))
        return result

    monkeypatch.setattr(Parser, "_parse_table", traced_table)
    monkeypatch.setattr(Parser, "_parse_aot", traced_aot)
    return events


def test_parse_organizes_body_and_map() -> None:
    doc = tomlkit.parse(DOC)

    assert describe(doc) == EXPECTED_STRUCTURE
    # The root container holds exactly three keyed items and no whitespace:
    # blank lines were absorbed into the preceding table's own container.
    assert {k.key: v for k, v in doc._map.items()} == {
        "server": 0,
        "products": 1,
        "a": 2,
    }
    # The dotted key ``a.b = 1`` became a dotted super table ``a`` holding ``b``.
    server = doc["server"]
    dotted_super = server.value.body[0]
    assert dotted_super[0].is_dotted()
    assert isinstance(dotted_super[1], Table) and dotted_super[1].is_super_table()
    # The trailing comment belongs to the Integer's trivia, not a body item.
    leaf = dotted_super[1].value.body[0][1]
    assert leaf.trivia.comment == "# dotted leaf"
    assert leaf.trivia.comment_ws == "  "
    # Round-trip is byte-exact.
    assert tomlkit.dumps(doc) == DOC


def test_parser_table_entry_exit_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    events = _tracing_parser(monkeypatch)

    parser = Parser(DOC)
    parser.parse()

    assert events == EXPECTED_TRACE
    # The AoT stack is balanced once parsing finishes.
    assert parser._aot_stack == []


def test_out_of_order_table_shares_one_semantic_key() -> None:
    doc = tomlkit.parse("[a]\nx = 1\n[b]\ny = 2\n[a.c]\nz = 3\n")

    # One semantic key "a", two body positions: the map holds a tuple.
    assert doc._map[tomlkit.items.SingleKey("a")] == (0, 2)
    proxy = doc.item("a")
    assert isinstance(proxy, OutOfOrderTableProxy)
    # The proxy aggregates both fragments.
    assert proxy["x"] == 1
    assert proxy["c"]["z"] == 3
    assert describe(doc) == (
        "a | body[0] | key=a | map=(0, 2) | Table -\n"
        "a.x | body[0] | key=x  | map=0 | Integer -\n"
        "b | body[1] | key=b | map=1 | Table -\n"
        "b.y | body[0] | key=y  | map=0 | Integer -\n"
        "a | body[2] | key=a | map=(0, 2) | Table (super) -\n"
        "a.c | body[0] | key=c | map=0 | Table -\n"
        "a.c.z | body[0] | key=z  | map=0 | Integer -\n"
    )
    assert tomlkit.dumps(doc) == "[a]\nx = 1\n[b]\ny = 2\n[a.c]\nz = 3\n"


def test_child_table_before_parent_is_also_out_of_order() -> None:
    # Legal TOML: [a.b] implicitly creates super table "a"; the later [a]
    # header becomes a second fragment of the same semantic key.
    doc = tomlkit.parse("[a.b]\nc = 1\n[a]\nd = 2\n")

    assert doc._map[tomlkit.items.SingleKey("a")] == (0, 1)
    assert isinstance(doc.item("a"), OutOfOrderTableProxy)
    assert doc["a"]["b"]["c"] == 1
    assert doc["a"]["d"] == 2
    assert tomlkit.dumps(doc) == "[a.b]\nc = 1\n[a]\nd = 2\n"


def test_edit_leaf_value_preserves_position_and_trivia() -> None:
    doc = tomlkit.parse(DOC)
    doc["server"]["a"]["b"] = 2

    expected = DOC.replace("a.b = 1", "a.b = 2")
    assert tomlkit.dumps(doc) == expected
    # The replacement reused the same body slot and kept the comment.
    leaf = doc["server"].value.body[0][1].value.body[0][1]
    assert leaf.trivia.comment == "# dotted leaf"
    # Unmodified segments are byte-identical.
    assert "[a]\nvalue = 42\n" in tomlkit.dumps(doc)
    assert 'mode = {fast = true, retries = 3}\n' in tomlkit.dumps(doc)


def test_add_sibling_inserts_before_first_table_header() -> None:
    doc = tomlkit.parse(DOC)
    doc["server"]["c"] = "new"

    expected = DOC.replace(
        "a.b = 1  # dotted leaf\n\n[server.opts]",
        'a.b = 1  # dotted leaf\nc = "new"\n\n[server.opts]',
    )
    assert tomlkit.dumps(doc) == expected
    # Inserted at body index 1: after the dotted super table, before the
    # blank-line Whitespace and the [server.opts] header.
    assert doc["server"].value.body[1][0].key == "c"


def test_remove_aot_element_drops_its_trivia() -> None:
    doc = tomlkit.parse(DOC)
    del doc["products"][0]

    expected = DOC.replace(
        '[[products]]\nname = "alpha"\n\n[[products]]\nname = "beta"',
        '[[products]]\nname = "beta"',
    )
    assert tomlkit.dumps(doc) == expected
    # The surviving element keeps its own body (including its trailing blank
    # line); the removed element's whitespace went away with it.
    assert len(doc["products"]) == 1
    assert doc["products"][0]["name"] == "beta"


def test_replace_inline_table_with_inline_table_stays_in_place() -> None:
    doc = tomlkit.parse(DOC)
    replacement = tomlkit.inline_table()
    replacement["fast"] = False
    replacement["slow"] = True
    doc["server"]["opts"]["mode"] = replacement

    expected = DOC.replace(
        "mode = {fast = true, retries = 3}",
        "mode = {fast = false, slow = true}",
    )
    assert tomlkit.dumps(doc) == expected
    # Same body slot, same line: trivia was inherited from the old value.
    mode = doc["server"]["opts"].value.body[0][1]
    assert mode.trivia.trail == "\n"


def test_replace_inline_table_with_plain_dict_becomes_standard_table() -> None:
    # Current behavior: item(dict) builds a *standard* Table (not an
    # InlineTable) when the parent is a table, so the replacement is
    # re-serialized as a [server.opts.mode] section and relocated.
    doc = tomlkit.parse(DOC)
    doc["server"]["opts"]["mode"] = {"fast": False}

    assert tomlkit.dumps(doc) == (
        "[server]\n"
        "a.b = 1  # dotted leaf\n"
        "\n"
        "[server.opts]\n"
        "\n"
        "[server.opts.mode]\n"
        "fast = false\n"
        '[[products]]\nname = "alpha"\n'
        "\n"
        '[[products]]\nname = "beta"\n'
        "\n"
        "[a]\n"
        "value = 42\n"
    )


def test_dump_reparse_round_trip_preserves_semantics() -> None:
    doc = tomlkit.parse(DOC)
    doc["server"]["a"]["b"] = 2
    doc["server"]["c"] = "new"
    del doc["products"][0]
    replacement = tomlkit.inline_table()
    replacement["fast"] = False
    doc["server"]["opts"]["mode"] = replacement

    dumped = tomlkit.dumps(doc)
    reparsed = tomlkit.parse(dumped)

    assert reparsed.unwrap() == doc.unwrap()
    assert tomlkit.dumps(reparsed) == dumped
    # Segments the edits never touched survived byte-identically.
    assert "[a]\nvalue = 42\n" in dumped


def test_duplicate_table_definition_raises_at_second_header() -> None:
    with pytest.raises(ParseError, match='Key "a" already exists') as excinfo:
        tomlkit.parse("[a]\n[a]\n")

    assert "line 2" in str(excinfo.value)


def test_child_before_parent_conflict_raises_in_parent_body() -> None:
    # [a.b] creates super table "a" holding table "b"; the later [a] body
    # redefines "b" as an integer -> KeyAlreadyPresent, wrapped as ParseError
    # by Parser.parse (the error is found while appending [a] at the root).
    with pytest.raises(ParseError, match='Key "b" already exists') as excinfo:
        tomlkit.parse("[a.b]\nc = 1\n[a]\nb = 2\n")

    assert "line 4" in str(excinfo.value)


def test_dotted_key_conflicting_with_table_raises_unwrapped() -> None:
    # [a] b.c = 1 makes "b" a dotted super table inside [a]; the nested
    # [a.b] header is rejected from Table.raw_append inside _parse_table,
    # so the raw TOMLKitError propagates without line/column information.
    with pytest.raises(TOMLKitError, match="Redefinition of an existing table") as e:
        tomlkit.parse("[a]\nb.c = 1\n[a.b]\n")

    assert type(e.value) is TOMLKitError
    assert not isinstance(e.value, ParseError)


def test_root_dotted_key_cannot_be_followed_by_its_table_header() -> None:
    # TOML 1.0: a dotted key already defines its parent tables, so a later
    # [a] header for root-level "a.b = 1" is a redefinition.
    with pytest.raises(ParseError, match="Redefinition of an existing table"):
        tomlkit.parse("a.b = 1\n[a]\n")


def test_failed_edit_leaves_partial_mutation() -> None:
    # Public API is not transactional: Container.append performs
    # _raw_append *before* _validate_out_of_order_table, so a validation
    # failure leaves the conflicting fragment in the body.
    doc = tomlkit.parse("[a.b]\nx = 1\n[c]\ny = 2\n")

    fragment = Table(tomlkit.container.Container(True), Trivia(), False, True)
    inner = Table(tomlkit.container.Container(True), Trivia(), False)
    inner.append("y", 2)
    fragment.append("b", inner)

    with pytest.raises(KeyAlreadyPresent):
        doc.append("a", fragment)

    # The fragment was appended to the body before the error was raised and
    # was not rolled back: "a" is now an out-of-order key ...
    assert doc._map[tomlkit.items.SingleKey("a")] == (0, 2)
    # ... and the document serializes the duplicate [a.b] table, which no
    # longer parses as valid TOML.
    dumped = tomlkit.dumps(doc)
    assert dumped == "[a.b]\nx = 1\n[c]\ny = 2\n\n[a.b]\ny = 2\n"
    with pytest.raises(ParseError):
        tomlkit.parse(dumped)


def test_failed_parse_publishes_no_partial_document() -> None:
    # Parsing is all-or-nothing: the in-progress TOMLDocument is abandoned
    # when the error propagates out of Parser.parse.
    with pytest.raises(ParseError):
        tomlkit.parse("[a]\n[a]\n")
    # A subsequent parse is unaffected by the failed one.
    assert tomlkit.parse("[a]\nx = 1\n")["a"]["x"] == 1
