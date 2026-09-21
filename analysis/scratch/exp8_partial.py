from tomlkit.parser import Parser
from tomlkit.items import Table, AoT, Whitespace, Comment

def inspect_after_error(text, label):
    print(f"===== {label} =====")
    p = Parser(text)
    try:
        doc = p.parse()
    except Exception as e:
        print(f"  raised {type(e).__name__}: {e}")
        # The root Container created inside parse() is local; grab from traceback.
        import traceback
        body = None
        for f, _ in traceback.walk_tb(e.__traceback__):
            loc = f.f_locals
            if "body" in loc and hasattr(loc["body"], "body"):
                body = loc["body"]
            if "values" in loc and hasattr(loc["values"], "body"):
                vals = loc["values"]
                print("  inner table 'values' body at failure:",
                      [(str(k).strip() if k else None, type(v).__name__) for k, v in vals.body])
        if body is not None:
            print("  root body at failure:",
                  [(str(k).strip() if k else None, type(v).__name__) for k, v in body.body])
            print("  root _map at failure:", {str(k).strip(): i for k, i in body._map.items()})
    print()

inspect_after_error("a = 1\na = 2\n", "dup root key (first KV kept)")
inspect_after_error("[a]\nx=1\n[a]\ny=2\n", "dup table (first table + its body kept)")
inspect_after_error("[[p]]\nx=1\n[p]\ny=2\n", "plain table after AoT")
inspect_after_error("[[p]]\nx=1\n[[p]]\ny=2\n[[p]]\n", "third AoT header, missing value (EOF)")
inspect_after_error("a.b = 1\n[a]\nz=2\n", "root dotted then [a]")
