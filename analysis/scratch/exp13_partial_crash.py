from tomlkit import parse
from tomlkit.container import OutOfOrderTableProxy
from tomlkit.exceptions import TOMLKitError, KeyAlreadyPresent

# The AoT-split out-of-order case: same path has 2 parts that EACH carry an AoT
# fragment. Proxy merges them via _merge_aot_fragment.
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
hooks = doc["hooks"]
print("type:", type(hooks).__name__)
proxy = doc.item("hooks")
print("parts:", len(proxy._tables), "tables_map keys:", [str(k).strip() for k in proxy._tables_map])

# Attempt: assign a plain value to "state" (exists in part 2) -> writes part 2
before = doc.as_string()
try:
    hooks["state"] = 99   # Table -> plain => del branch then recursion
except Exception as e:
    print("raised:", type(e).__name__, e)
print("changed:", doc.as_string() != before)
print(doc.as_string())
