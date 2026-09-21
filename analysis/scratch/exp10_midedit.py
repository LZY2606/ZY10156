import tomlkit
from tomlkit import parse, table, inline_table
from tomlkit.container import OutOfOrderTableProxy
from tomlkit.exceptions import TOMLKitError, NonExistentKey

def snap(doc):
    return doc.as_string()

# ---- Case A: OutOfOrderTableProxy assignment failing on the 2nd part ----
# [a] with a plain value (concrete part 1), then out-of-order [a.b] (super part 2).
docA = parse("[a]\nx = 1\n[zz]\nq = 2\n[a.b]\nc = 3\n")
proxy = docA["a"]
print("A proxy type:", type(proxy).__name__, "tables:", len(proxy._tables))
before = snap(docA)
print("before:\n" + before)
# Assign a plain value that already exists in part 2 as a table -> write into part1 OK,
# then internal_container[new] at end? We need an error AFTER a mutation.
# Try setting a key that exists in one part as a table but value is plain via proxy.
try:
    proxy["b"] = 5   # b is a subtable; replacing Table with plain value triggers del+set in one part
except Exception as e:
    print("A raised:", type(e).__name__, e)
print("A after (changed?):", snap(docA) != before)
print(snap(docA))
