from tomlkit import parse
from tomlkit.exceptions import TOMLKitError

# Two out-of-order parts of "a". Part 1 concrete [a] has plain u.
# Part 2 super extends with [a.b].
TEXT = "[a]\nu = 1\n[zz]\nq = 9\n[a.b]\nc = 3\n"

def run(value, label):
    doc = parse(TEXT)
    proxy = doc["a"]
    print("="*15, label, "proxy tables:", len(proxy._tables), "tables_map:", dict(proxy._tables_map))
    before = doc.as_string()
    try:
        proxy["u"] = value
    except Exception as e:
        print("  raised:", type(e).__name__, str(e)[:80])
    print("  partial change:", doc.as_string() != before)
    print(doc.as_string())

run(5, "set existing plain key u = 5")

# Now a scenario: adding a brand-new plain key to a proxy whose only part is a super table
TEXT2 = "[x.y]\nz = 1\n"
doc = parse(TEXT2)
proxy = doc["x"]
print("="*15, "new plain key on pure-super proxy; tables:", len(proxy._tables),
      [t.is_super_table() for t in proxy._tables])
before = doc.as_string()
proxy["k"] = 7
print(doc.as_string())

# Force failure mid-proxy-setitem: new key, parts exist, table[key]=value for a
# table where append raises (e.g. append a Table into an InlineTable fragment).
# Build via API: out-of-order parts can't be inline. Instead use AoT branch:
# proxy new key with table value to parts[0] — fine. Try assigning Table under
# a key that exists as AoT-merged in internal map but not _tables_map.
