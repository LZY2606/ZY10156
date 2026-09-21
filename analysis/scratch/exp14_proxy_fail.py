from tomlkit import parse
from tomlkit.exceptions import TOMLKitError, KeyAlreadyPresent, NonExistentKey

# Construct via edits a proxy whose key lives in BOTH parts as distinct plain
# values? TOML forbids that at parse. Instead: key present in two parts is legal
# only for AoT fragments (Stop in both) or subtree merges.
#
# tables_map[Stop] = [0, 1] because AoT fragment lands in both parts.
TEXT = """\
[hooks]

[[hooks.Stop]]
matcher = "a"

[unrelated]
x = 1

[[hooks.Stop]]
matcher = "b"

[hooks.state]
y = 2
"""
doc = parse(TEXT)
proxy = doc.item("hooks")
print("Stop part indices:", proxy._tables_map)
stop_idx = proxy._tables_map[[k for k in proxy._tables_map if str(k)=='Stop'][0]]
print("Stop in parts:", stop_idx)

before = doc.as_string()
# __setitem__ branch: _key in _tables_map, map_indices len=2.
# replacing AoT with a plain value: old_value is AoT (table-like), value plain
# => "del table[Stop]" on first part, del tables_map, recurse self[Stop]=plain
# _remove_table only invoked in the while-loop for EXTRA tables (pops index 1).
try:
    proxy["Stop"] = 5
except Exception as e:
    print("RAISED:", type(e).__name__, str(e)[:120])
print("changed:", doc.as_string() != before)
print(doc.as_string())
