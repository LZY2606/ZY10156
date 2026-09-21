from tomlkit import parse, table, inline_table
from tomlkit.exceptions import TOMLKitError, KeyAlreadyPresent

def trial(label, text, fn):
    print("="*12, label)
    try:
        doc = parse(text)
    except Exception as e:
        print("  (parse rejected input:", type(e).__name__, str(e)[:60], ")")
        return
    before = doc.as_string()
    try:
        fn(doc)
        print("  no error; changed =", doc.as_string()!=before)
    except Exception as e:
        print(f"  RAISED {type(e).__name__}: {str(e)[:90]}")
        print("  changed after raise =", doc.as_string()!=before)
        print(doc.as_string())

# VALID out-of-order: [a] x=1 ; [zz]; [a.b] c=3
TEXT = "[a]\nx=1\n[zz]\nq=9\n[a.b]\nc=3\n"

def fn1(d):
    proxy = d.item("a")
    proxy["b"] = table()      # b currently a subtable living in part 2
trial("proxy: b=table over subtable", TEXT, fn1)

def fn2(d):
    proxy = d.item("a")
    proxy["b"] = {"r": 1}     # plain dict -> Table same path
trial("proxy: b=dict over subtable", TEXT, fn2)

# Root container: set an existing KEY to a value whose item() conversion itself
# raises: happens before mutation (atomic). Try AoT element append of table
# carrying dotted key conflict with existing body of last element:
TEXT2 = "[[p]]\nx=1\n[[p]]\ny=2\n"
def fn3(d):
    t = table(); t["x"] = 5
    d["p"].append(t)   # duplicate x within AoT element? elements are separate tables
trial("aot append normal", TEXT2, fn3)

# InlineTable: replacing a value then triggering validation failure on append
# within same call is not reachable. But Array.insert with group machinery:
# conversion happens first; internal mutation is pure list ops, no TOML
# semantics errors. Check: insert into array at an index.
def fn4(d):
    d["arr"].insert(0, object())
trial("array insert unconvertible", "arr=[1]\n", fn4)
