import tomlkit
from tomlkit.items import *

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

doc = tomlkit.parse(DOC)
print("exact roundtrip:", tomlkit.dumps(doc) == DOC)

def show(cont, indent=0):
    pad = "  " * indent
    for i, (k, v) in enumerate(cont.body):
        ks = str(k) if k is not None else None
        dotted = k.is_dotted() if k is not None else None
        extra = ""
        if isinstance(v, Table):
            extra = f" super={v.is_super_table()} aotel={v.is_aot_element()} name={v.name!r} display={v.display_name!r}"
        print(f"{pad}[{i}] key={ks!r} dotted={dotted} type={type(v).__name__}{extra}")
        if isinstance(v, Whitespace):
            print(f"{pad}     whitespace={v.s!r} fixed={v.is_fixed()}")
            continue
        t = v.trivia
        print(f"{pad}     trivia(indent={t.indent!r},cws={t.comment_ws!r},cmt={t.comment!r},trail={t.trail!r})")
        if isinstance(v, (Table, InlineTable)):
            show(v.value, indent+1)
        if isinstance(v, AoT):
            for j, t2 in enumerate(v.body):
                print(f"{pad}  AoT elem{j} trivia(indent={t2.trivia.indent!r},trail={t2.trivia.trail!r})")
                show(t2.value, indent+2)

show(doc)
print("--- root _map ---")
for k, idx in doc._map.items():
    print(repr(str(k)), "dotted=", k.is_dotted(), "->", idx)
