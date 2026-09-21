from tomlkit import parse
from tomlkit.items import Table, Trivia
from tomlkit.container import Container
from tomlkit.exceptions import KeyAlreadyPresent, ParseError

def build():
    doc = parse("[[p]]\nid = 1\n[zz]\nq = 2\n")
    extra = Table(Container(True), Trivia(), False, is_super_table=True, name="p")
    g = Table(Container(True), Trivia(), False, name="g", display_name="p.g")
    g.value.append("v", 1)
    extra.value.append("g", g)
    bad = Table(Container(True), Trivia(), False, name="id", display_name="p.id")
    bad.value.append("deep", 2)
    extra.value.append("id", bad)
    return doc, extra

# 1) raised mid-call, document mutated, dumped doc is itself invalid TOML
doc, extra = build()
try:
    doc.append("p", extra)
except KeyAlreadyPresent:
    pass
s = doc.as_string()
print("dumped after failed append:\n"+s)
try:
    parse(s)
    print("dumped doc reparses (unexpected)")
except ParseError as e:
    print("dumped doc is INVALID TOML on reparse:", e)

# 2) also reachable through __setitem__? key 'p' exists, so __setitem__ -> _replace
doc2, extra2 = build()
try:
    doc2["p"] = extra2
except Exception as e:
    print("via __setitem__:", type(e).__name__, str(e)[:80])
print("changed via setitem:", doc2.as_string() != "[[p]]\nid = 1\n[zz]\nq = 2\n")

# 3) Is append a public method? Container.append is documented?
import tomlkit
print("TOMLDocument.append is public:", hasattr(tomlkit.TOMLDocument, "append"))
# Table.append also delegates to container.append; simulate nested equivalent
doc3 = parse("[outer]\n[[outer.p]]\nid = 1\n")
outer = doc3["outer"]
extra3 = Table(Container(True), Trivia(), False, is_super_table=True, name="p")
g3 = Table(Container(True), Trivia(), False, name="g", display_name="p.g")
g3.value.append("v", 1)
extra3.value.append("g", g3)
bad3 = Table(Container(True), Trivia(), False, name="id", display_name="p.id")
bad3.value.append("deep", 2)
extra3.value.append("id", bad3)
before3 = doc3.as_string()
try:
    outer.append("p", extra3)
except Exception as e:
    print("nested Table.append RAISED:", type(e).__name__, str(e)[:60])
print("nested changed:", doc3.as_string()!=before3)
print(doc3.as_string())

print("reparse semantics:", parse(s).unwrap())
