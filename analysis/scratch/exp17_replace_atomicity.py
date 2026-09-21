from tomlkit import parse, aot, table
from tomlkit.exceptions import KeyAlreadyPresent, TOMLKitError

# _replace_at reposition branch: replacing an INLINE/value with a Table/AoT.
# remove(k) happens BEFORE insertion. If insertion append raises -> partial.
#
# Reach a raise in the append of the NEW table: the new table key collides with
# an out-of-order fragment of the SAME key chain.
#
# Setup: root has 'k' as a plain VALUE and out-of-order super-table fragments
# with a different name won't collide. We need the reposition append to find
# current AoT/Table. But remove(k) just removed 'k'. Collision requires another
# body slot already mapped to 'k' — impossible for plain keys. So root path is
# effectively atomic for a single replace.
#
# But InlineTable replacement INSIDE a dotted super table's internal structure:
# try replacing one value with a table in a container where an out-of-order
# tuple index for the NEW key already exists with incompatible type.
TEXT = "[a]\nx=1\n[zz]\nq=9\n[a.b]\nc=3\n"
d = parse(TEXT)
# proxy['a'] internal has: x(plain), b(table).
# Replace 'x' (plain) with a TABLE named 'x' -> live part1 [a] x=1 becomes [a.x];
# then proxy bookkeeping? proxy is ephemeral; __setitem__ delegates to tables[0].
part1 = d.body[0][1]
print("part1 type:", type(part1).__name__, "body before:",
      [(str(k).strip() if k else None, type(v).__name__) for k,v in part1.value.body])
try:
    d["a"]["x"] = table()   # plain value -> table
except Exception as e:
    print("RAISED:", type(e).__name__, e)
print("changed serialization:\n"+d.as_string())
print("part1 body after:",
      [(str(k).strip() if k else None, type(v).__name__) for k,v in part1.value.body])
print("part2 ([a.b] fragment) body:",
      [(str(k).strip() if k else None, type(v).__name__) for k,v in d.body[2][1].value.body])
