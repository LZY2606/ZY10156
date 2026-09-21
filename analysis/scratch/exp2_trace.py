import tomlkit
from tomlkit.parser import Parser
from tomlkit.items import Table, AoT

MAIN = '''\
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

OOO = '''\
[a]
x = 1
[zz]
q = 2
[a.b]
c = 3
[a.d]
e = 4
'''

class TracingParser(Parser):
    def _parse_table(self, parent_name=None, parent=None):
        depth = len(self._aot_stack)
        line = self._src[:self._idx].count("\n") + 1
        print(f"{'  '*depth}>> _parse_table line={line} idx={self._idx} parent_name={tuple(parent_name) if parent_name else None} aot_stack={[tuple(k) for k in self._aot_stack]}")
        key, result = super()._parse_table(parent_name, parent)
        kind = "AoT" if isinstance(result, AoT) else f"Table(super={result.is_super_table()},aotel={result.is_aot_element()},name={result.name!r},display={result.display_name!r})"
        print(f"{'  '*depth}<< return key={tuple(key)!r} dotted={key.is_dotted()} result={kind} aot_stack={[tuple(k) for k in self._aot_stack]}")
        return key, result

    def _parse_aot(self, first, name_first):
        print(f"   _parse_aot first.display={first.display_name!r} name_first={tuple(name_first)} -> push aot_stack")
        res = super()._parse_aot(first, name_first)
        print(f"   _parse_aot done, {len(res.body)} elements, aot_stack popped")
        return res

for label, text in [("MAIN", MAIN), ("OOO", OOO)]:
    print(f"===== {label} =====")
    doc = TracingParser(text).parse()
    print("root _map:")
    for k, idx in doc._map.items():
        print("  ", repr(str(k)), "dotted=", k.is_dotted(), "->", idx)
    print("table_keys:", [str(k) for k in doc._table_keys])
    print()
