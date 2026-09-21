import tomlkit
from tomlkit import inline_table, parse
from tomlkit.items import AoT, Table, InlineTable, Whitespace, Null

DOC = '''\
# lead comment
root = 1 # root trailing

title.sub = "s"
meta = { x = 1, y = 2 } # inline cmt

[a]
b = 1 # leaf cmt
sibling = 0

[[products]]
id = 1
name = "hammer" # hammer cmt

[[products]]
id = 2
name = "nail"
'''

def brief(doc):
    for i,(k,v) in enumerate(doc.body):
        t=type(v).__name__
        if isinstance(v, Whitespace): print(f"  {i}: WS {v.s!r}")
        elif isinstance(v, Null): print(f"  {i}: Null")
        elif isinstance(v, Table): print(f"  {i}: T/{str(k).strip()} super={v.is_super_table()}")
        elif isinstance(v, AoT): print(f"  {i}: AoT/{str(k).strip()} n={len(v)}")
        else: print(f"  {i}: {t}/{str(k).strip()}")
    print("  map:", {str(k).strip(): idx for k,idx in doc._map.items()})

# E4a: true inline replacement
doc = parse(DOC)
new = inline_table(); new["p"] = 10
doc["meta"] = new
it = doc.item("meta")
print("E4a inline replace -> type:", type(it).__name__, "_new:", it._new)
print("   trivia:", it.trivia)
brief(doc)
print(doc.as_string())
print("exact unmodified bytes check on untouched regions:")
s = doc.as_string()
assert '# lead comment\nroot = 1 # root trailing\n' in s
assert 'b = 1 # leaf cmt' in s  # E4 only
print("OK\n")

# E4b: plain dict replacement (document-root parent) => becomes [meta]
doc2 = parse(DOC)
doc2["meta"] = {"p": 10}
print("E4b plain-dict replace -> type:", type(doc2.item("meta")).__name__)
print(doc2.as_string())
