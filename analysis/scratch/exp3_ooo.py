import tomlkit
from tomlkit.container import OutOfOrderTableProxy
from tomlkit.items import Table, AoT, Whitespace, Null

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

doc = tomlkit.parse(OOO)
print("body len:", len(doc.body))
for i,(k,v) in enumerate(doc.body):
    if isinstance(v, Table):
        print(i, repr(str(k)), f"Table super={v.is_super_table()} display={v.display_name!r} inner:")
        for j,(kk,vv) in enumerate(v.value.body):
            print("   ", j, repr(str(kk)) if kk else None, type(vv).__name__,
                  (f"super={vv.is_super_table()} display={vv.display_name!r}" if isinstance(vv,Table) else ""))
    else:
        print(i, repr(str(k)) if k else None, type(v).__name__)
print("map:", {str(k): idx for k,idx in doc._map.items()})
print("out_of_order_keys:", {str(k) for k in doc._out_of_order_keys})

proxy = doc.item("a")
print("proxy type:", type(proxy).__name__)
print("proxy tables count:", len(proxy._tables), "tables_map:", {str(k):v for k,v in proxy._tables_map.items()})
print("proxy unwrap:", proxy.unwrap())
print("proxy dict keys:", list(proxy))
print("internal container body:")
ic = proxy._internal_container
for i,(k,v) in enumerate(ic.body):
    print("  ", i, repr(str(k)) if k else None, type(v).__name__)
print("internal map:", {str(k): idx for k,idx in ic._map.items()})
print(doc.as_string() == OOO, "exact roundtrip")
