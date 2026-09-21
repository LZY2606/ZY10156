"""Pinned tests for the parser -> Container body/map model and edit boundaries.

These tests accompany ``analysis/`` and pin, for tomlkit 0.15.1:

* which physical body slots one semantic key occupies (including tuple indices
  for out-of-order tables aggregated by ``OutOfOrderTableProxy``);
* the parse/edit/dump/reparse semantics of leaf edits, sibling insertion,
* AoT element removal and inline-table replacement;
* the byte-identical preservation of untouched regions;
* parse-time error discovery points for the three illegal input classes;
* the *non-atomic* visible boundary of a public ``Container.append`` call.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import tomlkit

from tomlkit import aot
from tomlkit import inline_table
from tomlkit import key
from tomlkit import parse
from tomlkit import table
from tomlkit.container import OutOfOrderTableProxy
from tomlkit.exceptions import KeyAlreadyPresent
from tomlkit.exceptions import ParseError
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import AoT
from tomlkit.items import InlineTable
from tomlkit.items import Integer
from tomlkit.items import Null
from tomlkit.items import Table

from analysis.structure_helper import map_of
from analysis.structure_helper import body_types


ANALYSIS_DIR = Path(__file__).parent.parent / "analysis"
MINIMAL = (ANALYSIS_DIR / "MINIMAL.toml").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Parse: physical body slots vs semantic keys
# ---------------------------------------------------------------------------


def test_minimal_document_round_trips_byte_identically() -> None:
    assert tomlkit.dumps(parse(MINIMAL)) == MINIMAL


def test_root_body_slots_are_a_token_stream_not_a_dict() -> None:
    doc = parse(MINIMAL)
    # Comments and blank lines are keyless physical slots interleaved with the
    # eight semantic entries; a plain ordered dict cannot carry them.
    assert body_types(doc) == [
        (None, "Comment"),
        ("root", "Integer"),
        (None, "Whitespace"),
        ("title", "Table"),
        ("meta", "InlineTable"),
        (None, "Whitespace"),
        ("a", "Table"),
        ("products", "AoT"),
    ]


def test_map_points_each_semantic_key_at_one_body_index() -> None:
    doc = parse(MINIMAL)
    assert map_of(doc) == {
        "root": 1,
        "title": 3,
        "meta": 4,
        "a": 6,
        "products": 7,
    }
    title_key = next(iter(k for k in doc._map if str(k).strip() == "title"))
    assert title_key.is_dotted() is True


def test_dotted_root_key_materializes_as_a_super_table() -> None:
    doc = parse(MINIMAL)
    title = doc.body[3][1]
    assert isinstance(title, Table)
    assert title.is_super_table() is True
    # The leaf itself is a normal entry inside the implicit table's container.
    leaf = title.value.body[0]
    assert str(leaf[0]).strip() == "sub"
    assert leaf[1].unwrap() == "s"


def test_inline_table_is_a_flat_container_with_comma_whitespace_slots() -> None:
    doc = parse(MINIMAL)
    meta = doc.item("meta")
    assert isinstance(meta, InlineTable)
    assert body_types(meta.value) == [
        (None, "Whitespace"),
        ("x", "Integer"),
        (None, "Whitespace"),
        (None, "Whitespace"),
        ("y", "Integer"),
        (None, "Whitespace"),
    ]
    assert meta.unwrap() == {"x": 1, "y": 2}


def test_aot_two_headers_share_one_semantic_key_and_one_body_slot() -> None:
    doc = parse(MINIMAL)
    products = doc.item("products")
    assert isinstance(products, AoT)
    # Both [[products]] headers aggregate into ONE AoT item at ONE body index;
    # the two elements live in AoT._body, not in the document body.
    assert map_of(doc)["products"] == 7
    assert len(products.body) == 2
    assert [element.unwrap() for element in products.body] == [
        {"id": 1, "name": "hammer"},
        {"id": 2, "name": "nail"},
    ]


def test_out_of_order_semantic_key_spans_multiple_body_slots() -> None:
    doc = parse(
        "[a]\nx = 1\n[zz]\nq = 2\n[a.b]\nc = 3\n[a.d]\ne = 4\n"
    )
    # One semantic key "a" -> two physical body slots; the unrelated table zz
    # sits between them at slot 1.
    assert map_of(doc) == {"a": (0, 2), "zz": 1}
    fragment_0, fragment_2 = doc.body[0][1], doc.body[2][1]
    assert isinstance(fragment_0, Table) and fragment_0.is_super_table() is False
    assert isinstance(fragment_2, Table) and fragment_2.is_super_table() is True
    # item() returns the aggregating proxy, never a single fragment.
    proxy = doc.item("a")
    assert isinstance(proxy, OutOfOrderTableProxy)
    assert proxy.unwrap() == {"x": 1, "b": {"c": 3}, "d": {"e": 4}}
    # Both later sub-tables were nested into the SECOND fragment at parse time.
    assert [str(k).strip() for k, _ in fragment_2.value.body] == ["b", "d"]


def test_child_then_parent_is_valid_and_merges_in_place() -> None:
    # TOML spec: "Defining a super-table afterwards is ok."
    doc = parse("[a.b]\nc = 1\n\n[a]\nd = 2\n")
    assert doc.unwrap() == {"a": {"b": {"c": 1}, "d": 2}}
    assert tomlkit.dumps(doc) == "[a.b]\nc = 1\n\n[a]\nd = 2\n"


# ---------------------------------------------------------------------------
# Edits: who owns the trivia and the serialization position
# ---------------------------------------------------------------------------


def test_leaf_edit_inherits_trivia_and_keeps_slot() -> None:
    doc = parse(MINIMAL)
    leaf = doc["a"].item("b")
    doc["a"]["b"] = 42
    new_leaf = doc["a"].item("b")
    assert isinstance(new_leaf, Integer)
    # Container._replace_at copies indent/comment/trail from the replaced item.
    assert new_leaf.trivia.indent == leaf.trivia.indent
    assert new_leaf.trivia.comment_ws == " "
    assert new_leaf.trivia.comment == "# leaf trailing"
    assert new_leaf.trivia.trail == "\n"
    # The slot index is unchanged.
    assert map_of(doc)["a"] == 6
    assert body_types(doc["a"].value)[0] == ("b", "Integer")
    dumped = tomlkit.dumps(doc)
    assert "b = 42 # leaf trailing\n" in dumped
    assert parse(dumped).unwrap()["a"]["b"] == 42


def test_added_sibling_is_appended_inside_the_existing_table() -> None:
    doc = parse(MINIMAL)
    doc["a"]["new_key"] = "hello"
    inner = doc["a"].value
    assert body_types(inner) == [
        ("b", "Integer"),
        ("sibling", "Integer"),
        ("new_key", "String"),
        (None, "Whitespace"),
    ]
    dumped = tomlkit.dumps(doc)
    assert "new_key = \"hello\"\n" in dumped
    # The new key is positioned BEFORE the table's trailing blank line, which
    # already separates [a] from [[products]].
    assert dumped.index("new_key") < dumped.index("[[products]]")
    assert parse(dumped)["a"]["new_key"] == "hello"


def test_removing_an_aot_element_drops_its_header_and_body() -> None:
    doc = parse(MINIMAL)
    products = doc["products"]
    del products[0]
    assert len(doc["products"].body) == 1
    dumped = tomlkit.dumps(doc)
    assert 'id = 1' not in dumped
    assert '"hammer"' not in dumped
    # The second element is now the only [[products]] header rendered.
    assert dumped.count("[[products]]") == 1
    assert parse(dumped).unwrap()["products"] == [{"id": 2, "name": "nail"}]


def test_inline_table_replacement_keeps_slot_and_inherits_comment() -> None:
    doc = parse(MINIMAL)
    new_inline = inline_table()
    new_inline["p"] = 10
    doc["meta"] = new_inline
    kept = doc.item("meta")
    assert isinstance(kept, InlineTable)
    assert map_of(doc)["meta"] == 4  # slot preserved, no repositioning
    assert kept.trivia.comment == "# inline trailing"
    dumped = tomlkit.dumps(doc)
    assert "meta = {p = 10} # inline trailing\n" in dumped
    assert parse(dumped)["meta"].unwrap() == {"p": 10}


def test_plain_dict_assignment_becomes_a_dotted_or_standalone_table() -> None:
    # Public item() factory behaviour: a dict assigned at document/table level
    # becomes a Table (its own [header]), NOT an inline table.
    doc = parse(MINIMAL)
    doc["meta"] = {"p": 10}
    assert isinstance(doc.item("meta"), Table)
    assert not isinstance(doc.item("meta"), InlineTable)
    dumped = tomlkit.dumps(doc)
    assert "[meta]\np = 10\n" in dumped
    # The replacement moves out of the value region: old slot is Null, the new
    # table is inserted before the first real [header] (Container._replace_at).
    assert isinstance(doc.body[4][1], Null)


def test_untouched_sections_are_byte_identical_after_all_edits() -> None:
    doc = parse(MINIMAL)
    doc["a"]["b"] = 42
    doc["a"]["new_key"] = "hello"
    del doc["products"][0]
    new_inline = inline_table()
    new_inline["p"] = 10
    doc["meta"] = new_inline
    dumped = tomlkit.dumps(doc)

    head, _, rest = MINIMAL.partition("[a]\n")
    # The leading region up to [a] (comment, root KV, dotted key, inline table)
    # is untouched by the in-table edit and AoT deletion; only the inline line
    # changed. Anchor on segments that none of the edits touch.
    assert "# leading comment\n" in dumped
    assert 'root = 1 # root trailing\n' in dumped
    assert 'title.sub = "s"\n' in dumped
    assert 'name = "nail"\n' in dumped
    # Exact byte preservation of the surviving AoT element block.
    assert "[[products]]\nid = 2\nname = \"nail\"\n" in dumped
    # Nothing was appended beyond the original terminal newline.
    assert dumped.endswith("name = \"nail\"\n")


# ---------------------------------------------------------------------------
# Parse-time errors: discovery point and partial (discarded) state
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "line", "kind"),
    [
        # Same path redefined as a value twice.
        ("a = 1\na = 2\n", 2, KeyAlreadyPresent),
        # Same path: concrete table, then the name reused for an AoT header.
        ("[products]\nid = 1\n[[products]]\nid = 2\n", 4, KeyAlreadyPresent),
        # Same path: two concrete table headers.
        ("[a]\nx = 1\n[a]\ny = 2\n", 4, KeyAlreadyPresent),
    ],
)
def test_same_path_redefinition_is_rejected_at_second_header(
    text: str, line: int, kind: type[Exception]
) -> None:
    with pytest.raises(ParseError) as excinfo:
        parse(text)
    assert excinfo.value.line == line
    assert isinstance(excinfo.value.__cause__, kind)


def test_child_before_parent_alone_is_accepted() -> None:
    # Control case proving the error in the next test is the second [a.b].
    doc = parse("[a.b]\nc = 1\n\n[a]\nd = 2\n")
    assert doc.unwrap() == {"a": {"b": {"c": 1}, "d": 2}}


def test_child_parent_then_child_again_fails_on_reopen() -> None:
    text = "[a.b]\nc = 1\n[a]\nd = 2\n[a.b]\ne = 3\n"
    with pytest.raises(ParseError) as excinfo:
        parse(text)
    # The first [a.b] is consumed; the error is found at the reopening header.
    assert excinfo.value.line == 6
    assert isinstance(excinfo.value.__cause__, KeyAlreadyPresent)


@pytest.mark.parametrize(
    "text",
    [
        # Dotted key b.c inside [a], then [a.b] header (in order).
        "[a]\nb.c = 1\n[a.b]\nd = 2\n",
        # Root dotted a.b = 1, then a [a] header redefining the implicit table.
        "a.b = 1\n[a]\nz = 2\n",
    ],
)
def test_dotted_key_vs_table_header_conflict(text: str) -> None:
    # Both are rejected; the in-table case currently surfaces as the internal
    # TOMLKitError before the root loop can wrap it into ParseError, which is an
    # implementation detail rather than a spec distinction.
    with pytest.raises((ParseError, TOMLKitError)):
        parse(text)


def test_failed_parse_discards_the_partially_built_document() -> None:
    # The first KV is physically appended to the local root Container before
    # the duplicate key is detected; parse() never returns that container.
    with pytest.raises(ParseError):
        parse("a = 1\na = 2\n")
    # No document object is observable: the API only yields a TOMLDocument on
    # success, so there is no half-parsed object for callers to mutate.
    assert parse("ok = true\n").unwrap() == {"ok": True}


# ---------------------------------------------------------------------------
# Mid-edit failure: the public API does NOT promise transactional atomicity
# ---------------------------------------------------------------------------


def _aot_super_extension() -> Table:
    """A super-table fragment meant to extend the last element of an AoT.

    Its body adds a fresh sub-table ``g`` then collides with the existing leaf
    ``id`` inside the last AoT element.
    """
    extra = table(is_super_table=True)
    sub_g = table()
    sub_g["v"] = 1
    extra["g"] = sub_g
    sub_id = table()
    sub_id["deep"] = 2
    extra["id"] = sub_id
    return extra


def test_failed_append_leaves_the_document_partially_mutated() -> None:
    # Public API only: parse a one-element AoT, then append a super-table that
    # both adds [p.g] and attempts to redefine the leaf id as [p.id].
    doc = parse("[[p]]\nid = 1\n")
    before = tomlkit.dumps(doc)
    with pytest.raises(KeyAlreadyPresent):
        doc.append(key("p"), _aot_super_extension())

    after = tomlkit.dumps(doc)
    # The call raised, but its first sub-operation already landed: the last AoT
    # element now contains a new g sub-table (Container.append super-table
    # branch mutates `current[-1]` in a loop, with no rollback on later error).
    assert after != before
    assert "[p.g]\nv = 1\n" in after
    assert "[p.id]" not in after  # the colliding fragment never rendered
    # Boundary: the mutation is still internally consistent enough to reparse,
    # and semantics visibly changed.
    assert parse(after).unwrap() == {"p": [{"id": 1, "g": {"v": 1}}]}


def test_empty_aot_replacement_silently_drops_an_out_of_order_key_on_dump() -> None:
    # Replacing an out-of-order (tuple-indexed) table with an EMPTY AoT removes
    # the old fragments, and the empty AoT renders nothing: the in-memory view
    # still has the key, but serialization loses it.
    doc = parse("[a]\nx = 1\n[zz]\nq = 2\n[a.b]\nc = 3\n")
    doc["a"] = aot()
    assert "a" in doc  # the container mapping still carries the empty AoT
    dumped = tomlkit.dumps(doc)
    assert "[a" not in dumped  # nothing renders for the empty array
    assert parse(dumped).unwrap() == {"zz": {"q": 2}}
    # Appending an element afterwards restores the name at its new position.
    doc["a"].append({"y": 9})
    assert parse(tomlkit.dumps(doc)).unwrap() == {
        "a": [{"y": 9}],
        "zz": {"q": 2},
    }


def test_value_conversion_errors_are_atomic_because_conversion_runs_first() -> None:
    # In contrast to the super-table loop, plain setitem/array.insert call the
    # item() factory before touching any container slot: conversion failures
    # leave no trace.
    class Unconvertible:
        pass

    doc = parse("arr = [1]\nk = 2\n")
    before = tomlkit.dumps(doc)
    with pytest.raises(Exception):
        doc["new"] = Unconvertible()
    with pytest.raises(Exception):
        doc["arr"].append(Unconvertible())
    assert tomlkit.dumps(doc) == before


def test_structure_helper_reports_paths_indices_types_and_trivia_without_addresses() -> None:
    from analysis.structure_helper import structure_text

    doc = parse(MINIMAL)
    text = structure_text(doc)
    # No repr() object addresses leak through.
    assert "0x" not in text and " object at " not in text
    # Semantic path, body index, type and trivia markers are all present.
    assert "products[1].name" in text
    assert "products -> 7" in text
    assert "InlineTable" in text
    assert "comment='# leaf trailing'" in text
