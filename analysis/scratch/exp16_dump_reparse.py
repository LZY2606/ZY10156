from tomlkit import parse, dumps, table

TEXT = "[a]\nx=1\n[zz]\nq=9\n[a.b]\nc=3\n"
for val,label in [(table(),"b=table()"), ({"r":1},"b={dict}")]:
    d = parse(TEXT)
    proxy = d.item("a")
    proxy["b"] = val
    out = d.as_string()
    print(f"--- {label} ---")
    print(out)
    try:
        r = parse(out)
        print("REPARSE OK:", r.unwrap())
    except Exception as e:
        print("REPARSE FAILS:", type(e).__name__, str(e)[:80])
    print()
