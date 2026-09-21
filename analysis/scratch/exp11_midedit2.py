from tomlkit import parse, table, aot
from tomlkit.exceptions import TOMLKitError, NonExistentKey
from tomlkit.items import Table, AoT
import traceback

def attempt(label, text, fn):
    print("="*20, label)
    doc = parse(text)
    before = doc.as_string()
    try:
        fn(doc)
        print("  no error. changed =", doc.as_string() != before)
    except Exception as e:
        print(f"  raised {type(e).__name__}: {str(e)[:100]}")
        print("  changed after raise =", doc.as_string() != before)
        print(doc.as_string())
    print()

# 1) AoT duplicate key INSIDE a newly appended table (raw list append of a Table)
t = table()
t["x"] = 1
t["x"] = 2  # impossible to build at API level
def f1(doc):
    tbl = table()
    tbl["u"] = 1
    # craft a duplicate at the item layer by injecting body directly via public? no.
    # Instead: append an AoT element when existing key is a plain table value.
    doc["products"].append(tbl)

attempt("aot.append table that collides", "[products]\nx = 1\n", f1)

# 2) assign table() under an existing AoT key via Container.setitem (append path)
def f2(doc):
    doc["products"] = table()
attempt("setitem table over aot key", "[[products]]\nx=1\n", f2)

# 3) InlineTable append a Table
def f3(doc):
    from tomlkit.items import Table as T, Trivia
    doc["m"]._value.append("bad", T(__import__("tomlkit").container.Container(True), Trivia(), False))
attempt("direct container append Table inside inline (internal API)", "m = { x = 1 }\n", f3)

# 4) array: insert a value whose conversion raises -- use a custom object
class Boom:
    pass
def f4(doc):
    doc["arr"].append(Boom())
attempt("array.append unconvertible object", "arr = [1, 2]\n", f4)

# 5) public: doc['k'] = Boom()  (item() raises)
def f5(doc):
    doc["new"] = Boom()
attempt("setitem unconvertible at top-level", "x = 1\n", f5)

# 6) Remove nonexistent
def f6(doc):
    doc.remove("nope")
attempt("remove nonexistent", "x = 1\n", f6)
