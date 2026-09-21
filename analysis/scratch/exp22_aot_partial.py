from tomlkit import parse, aot, table
from tomlkit.items import AoT, Table, Trivia
from tomlkit.container import Container
from tomlkit.exceptions import KeyAlreadyPresent

# Container.append AoT branch when current is AoT:
#   for table in item.body: current.append(table)
# Build item AoT with 2 tables; make the 2nd append raise by poisoning current
# (current.append is list.append; won't raise). No raise there.
#
# Table-vs-AoT super-table branch after AoT:
#   if item.is_super_table() and len(current.body):
#       last = current[-1]
#       for k,v in item.value.body: last.value.append(k,v)  # may raise mid-loop
# This MUTATES last AoT element incrementally; a later k raises => partial.
# Construct: doc with [[p]] (1 element). Append at ROOT a super-table [p] whose
# body has good key g then a colliding key 'id' (already exists in last elem).
doc = parse("[[p]]\nid = 1\n[zz]\nq = 2\n")
last = doc.body  # just ensure parse
before = doc.as_string()

extra = Table(Container(True), Trivia(), False, is_super_table=True, name="p")
# good new key
g_table = Table(Container(True), Trivia(), False, name="g")
g_val_table = Table(Container(True), Trivia(), False, name="g", display_name="p.g")
g_val_table.value.append("v", 1)
extra.value.append("g", g_val_table)
# colliding: 'id' already a plain int in the last AoT element; adding id as
# subtable -> KeyAlreadyPresent inside last.value.append
id_sub = Table(Container(True), Trivia(), False, name="id", display_name="p.id")
id_sub.value.append("deep", 2)
extra.value.append("id", id_sub)

try:
    doc.append("p", extra)
except Exception as e:
    print("RAISED:", type(e).__name__, str(e)[:100])
print("partial change visible:", doc.as_string()!=before)
print(doc.as_string())
print("AoT last element body now:",
      [(str(k).strip() if k else None, type(v).__name__) for k,v in doc["p"][-1].value.body])
