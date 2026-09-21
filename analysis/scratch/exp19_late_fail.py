from tomlkit import parse, table
from tomlkit.exceptions import KeyAlreadyPresent, TOMLKitError

# OutOfOrderTableProxy.__setitem__ mutates LIVE parts via table[key]=value,
# and appends to self._internal_container LAST. We can make the live write
# succeed but the internal append RAISE, because the internal container validates
# out-of-order merges while the chosen live part may not (single fragment).
#
# proxy has two parts. Set a brand-new key that is a TABLE: live write goes to
# self._tables[0] (plain table value branch _is_table_or_aot True => tables[0]).
# Internal: _internal_container is a FRESH merge of both fragments at proxy
# build time. If the new table's BODY redefines a key that exists across the
# merge in an incompatible way that single-part write doesn't catch...
TEXT = "[a]\nx=1\n[zz]\nq=9\n[a.b]\nc=3\n"

# Scenario: assign value that raises DURING its own item() conversion while
# proxy already chose a part and mutated it? conversion happens at function
# entry (_is_table_or_aot calls _item_fn(it) TWICE before mutation). So no.
#
# Scenario: OutOfOrderTableProxy.__setitem__ plain-value fallback loops tables
# and picks "first table that allows plain values"; writes one; then internal
# write. All live writes precede the possibly-failing internal validation.
# Trigger: a brand-new plain key when parts exist BUT internal container has a
# key colliding (key also exists in internal but not in _tables_map? impossible:
# tables_map is populated for every non-None key).
#
# What about __delitem__: it does `del table[key]` for each part and may remove
# whole tables, THEN del internal_container[key] which raises NonExistentKey if
# internal map lacks it. Force internal/table desync?
doc = parse(TEXT)
proxy = doc.item("a")
# Desync: directly delete from one LIVE table's container without telling proxy
live_part1 = doc.body[0][1]
print("internal keys before:", list(proxy._internal_container))
# remove 'x' from part1 only
del live_part1["x"]
print("after direct live delete, internal still has x:", "x" in proxy._internal_container)
before = doc.as_string()
try:
    del doc["a"]["x"]   # rebuild proxy then delete
except Exception as e:
    print("RAISED:", type(e).__name__, str(e)[:100])
print("changed:", doc.as_string()!=before)
print(doc.as_string())
