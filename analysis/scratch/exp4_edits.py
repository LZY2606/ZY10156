import tomlkit
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
    out=[]
    for i,(k,v) in enumerate(doc.body):
        t=type(v).__name__
        if isinstance(v, Whitespace):
            out.append(f"{i}: WS{sorted(v.s)}")
        elif isinstance(v, Null):
            out.append(f"{i}: Null")
        elif isinstance(v, Table):
            out.append(f"{i}: T/{str(k).strip()} super={v.is_super_table()}")
        elif isinstance(v, AoT):
            out.append(f"{i}: AoT/{str(k).strip()} n={len(v)}")
        else:
            out.append(f"{i}: {t}/{str(k).strip()}={v!r}")
    print("   map:", {str(k).strip(): idx for k,idx in doc._map.items()})
    print("   body:", out)

doc = tomlkit.parse(DOC)
print("INITIAL"); brief(doc)

# Edit 1: change leaf value (a.b 1 -> 42)
old = doc["a"].item("b")
print("\nE1 set doc['a']['b']=42  old trivia:", old.trivia)
doc["a"]["b"] = 42
it = doc["a"].item("b")
print("   new type:", type(it).__name__, "raw:", it.as_string(), "trivia:", it.trivia)
print(doc.as_string())

# Edit 2: add sibling to existing table [a]
print("\nE2 doc['a']['new_key'] = 'hello'")
doc["a"]["new_key"] = "hello"
brief(doc)
print(doc.as_string())

# Edit 3: delete an AoT element (remove first product)
print("\nE3 del doc['products'][0]")
prods = doc["products"]
print("   before len:", len(prods))
del prods[0]
print("   after len:", len(prods))
brief(doc)
print(doc.as_string())

# Edit 4: replace inline table
print("\nE4 doc['meta'] = {'p': 10}  (inline)")
doc["meta"] = {"p": 10}
it = doc.item("meta")
print("   new type:", type(it).__name__, "new flag:", getattr(it,'_new',None), "trivia:", it.trivia)
brief(doc)
print(doc.as_string())
print("reparse equal:", tomlkit.parse(doc.as_string()).unwrap() == doc.unwrap())
