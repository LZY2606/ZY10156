from tomlkit import parse, aot, table
from tomlkit.exceptions import KeyAlreadyPresent, TOMLKitError

def try_case(label, text, mutate):
    print("="*14, label)
    doc = parse(text)
    before = doc.as_string()
    try:
        mutate(doc)
    except Exception as e:
        print(f"  RAISED {type(e).__name__}: {str(e)[:100]}")
        print("  partial change visible:", doc.as_string() != before)
        print(doc.as_string())
        return
    print("  no error; changed:", doc.as_string()!=before)
    print(doc.as_string())

# out-of-order tuple for key 't' with two table fragments; replace one leaf
# inside then conflict? Instead: replace root 't' (tuple) entirely with an AoT.
# _replace_at(tuple): nulls idx[1:], keeps first slot, sees type change,
# remove(k) -> removes ALL tuple fragments, then append AoT (fresh key t) -> OK.
text = "[a]\nx=1\n[zz]\nq=2\n[a.b]\nc=3\n"
def m1(doc):
    doc["a"] = aot()
try_case("replace out-of-order table key with empty AoT", text, m1)

# Dotted key -> header reposition where another sibling exists (issue #542)
def m2(doc):
    # title.sub dotted super-table; replace with AoT
    doc["title"] = aot()
try_case("replace dotted super with AoT", 'title.sub = 1\nother = 2\n', m2)

# InlineTable -> AoT? inline tables live as items; replacing with AoT
def m3(doc):
    doc["m"] = aot()
try_case("replace inline table with AoT", 'm = { x = 1 }\nother = 2\n', m3)

# replace an AoT with a plain value (reverse reposition)
def m4(doc):
    doc["p"] = 5
try_case("replace AoT key with plain int", "[[p]]\nx=1\n[zz]\nq=2\n", m4)

# replace AoT with inline table value (non-table) -> goes append plain path
from tomlkit import inline_table
def m5(doc):
    it = inline_table(); it["r"]=1
    doc["p"] = it
try_case("replace AoT key with inline table", "[[p]]\nx=1\n[zz]\nq=2\n", m5)
