from tomlkit import parse
from tomlkit.items import AoT, Table, Trivia
from tomlkit.container import Container

# Force the reposition branch where remove(k) happens, then append(new table)
# hits KeyAlreadyPresent because the SAME key survives as a tuple fragment.
# _replace_at iterates idx[1:] -> Null first; idx=idx[0] old slot -> remove(k)
# removes ALL fragments of k from _map/body. Then append of value. For collision
# we need another existing fragment mapped under k AFTER remove -> impossible.
#
# Different angle: Container.append AoT-after-table path mutates current AoT
# (current.append(item)) then returns; no rollback needed.
#
# Most reliable public partial-mutation window: append() ADDS a super-table that
# merges IN PLACE into an existing concrete table (the comment explicitly says
# merge is in-place), and only THEN _validate_out_of_order_table() raises.
# Sequence via public API:
#   doc = parse(valid doc); then build two tables via API and append so that
#   validation detects a collision AFTER current table was mutated.
doc = parse("[a]\nb = 1\n")   # concrete table a with plain leaf b

# Append a NEW out-of-order super-table [a] containing [a.b] (invalid redef of
# leaf b) via raw public append at root:
extra = Table(Container(True), Trivia(), False, is_super_table=True, name="a")
inner = Table(Container(True), Trivia(), False, name="b", display_name="a.b")
inner.value.append("c", 3)
extra.value.append("b", inner)

# doc["a"] returns merged Table (concrete). To append at ROOT container use add:
from tomlkit import key as _key
rootkey = _key("a")
before = doc.as_string()
print("before:\n"+before)
try:
    doc.append(rootkey, extra)
except Exception as e:
    print("RAISED:", type(e).__name__, str(e)[:100])
print("changed:", doc.as_string()!=before)
print("after:\n"+doc.as_string())
print("map:", {str(k).strip():v for k,v in doc._map.items()})
