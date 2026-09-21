from tomlkit import parse
from tomlkit.items import Table, Trivia
from tomlkit.container import Container

def fresh_extra():
    extra = Table(Container(True), Trivia(), False, is_super_table=True, name="p")
    g = Table(Container(True), Trivia(), False, name="g", display_name="p.g")
    g.value.append("v", 1)
    extra.value.append("g", g)
    bad = Table(Container(True), Trivia(), False, name="id", display_name="p.id")
    bad.value.append("deep", 2)
    extra.value.append("id", bad)
    return extra

doc = parse("[[p]]\nid = 1\n[zz]\nq = 2\n")
before = doc.as_string()
try:
    doc["p"] = fresh_extra()
except Exception as e:
    print("RAISED:", type(e).__name__, repr(str(e)))
print("changed:", doc.as_string()!=before)
