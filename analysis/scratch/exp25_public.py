import tomlkit
from tomlkit import parse, table, key

# Pure public API reproduction of non-atomic append:
# Build a super-table that EXTENDS the last AoT element (spec semantics),
# containing a valid new subtree then a colliding one.
doc = parse("[[p]]\nid = 1\n")

extra = table(is_super_table=True)
sub_g = table()
sub_g["v"] = 1
extra["g"] = sub_g
sub_id = table()
sub_id["deep"] = 2
extra["id"] = sub_id

before = doc.as_string()
try:
    doc.append(key("p"), extra)
except Exception as e:
    print("RAISED:", type(e).__name__, str(e))
print("partial:", doc.as_string() != before)
print(doc.as_string())
