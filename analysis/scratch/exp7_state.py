import traceback
from tomlkit.parser import Parser
from tomlkit.exceptions import ParseError, TOMLKitError

def trace(text, label):
    print(f"===== {label} =====")
    p = Parser(text)
    try:
        p.parse()
        print("  parsed OK")
    except Exception as e:
        print(f"  {type(e).__name__}: {e}")
        tb = traceback.walk_tb(e.__traceback__)
        frames = []
        for f, lineno in tb:
            if "/tomlkit/" in f.f_code.co_filename:
                frames.append((f.f_code.co_name, lineno, f))
        for name, lineno, f in frames[-8:]:
            locals_ = f.f_locals
            extra=[]
            s = locals_.get("self")
            if isinstance(s, Parser):
                extra.append(f"idx={s._idx} aot={[tuple(k) for k in s._aot_stack]}")
            if "key" in locals_ and hasattr(locals_["key"], "__iter__"):
                try: extra.append("key="+repr(tuple(locals_["key"])))
                except Exception: pass
            print("    ", f.f_code.co_name.split(";")[-1], lineno, " ".join(extra))
    print("  after-raise: idx =", p._idx, "| aot_stack =", p._aot_stack, "(empty => balanced)")
    print()

trace("a = 1\na = 2\n", "dup key")
trace("[products]\nid=1\n[[products]]\nid=2\n", "aot after table")
trace("[a]\nb.c = 1\n[a.b]\nd=2\n", "dotted vs table in-order (nested)")
trace("a.b = 1\n[a]\nz=2\n", "root dotted then [a]")
trace("[a.b]\nc=1\n[a]\nd=2\n[a.b]\ne=3\n", "ooo redef child")
