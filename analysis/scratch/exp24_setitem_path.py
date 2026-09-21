from tomlkit import parse
from tomlkit.items import Table, Trivia
from tomlkit.container import Container

doc = parse("[[p]]\nid = 1\n[zz]\nq = 2\n")
extra = Table(Container(True), Trivia(), False, is_super_table=True, name="p")
g = Table(Container(True), Trivia(), False, name="g", display_name="p.g")
g.value.append("v", 1)
extra.value.append("g", g)
bad = Table(Container(True), Trivia(), False, name="id", display_name="p.id")
bad.value.append("deep", 2)
extra.value.append("id", bad)
before = doc.as_string()
try:
    doc["p"] = extra
except Exception as e:
    print("RAISED:", type(e).__name__, str(e))
print("changed:", doc.as_string()!=before)
print(doc.as_string())
print("map:", {str(k).strip(): v for k,v in doc._map.items()})
print("body:", [(str(k).strip() if k else None, type(v).__name__) for k,v in doc.body])
