from tomlkit.parser import Parser

# AoT stack push happens in _parse_aot BEFORE siblings are parsed.
# Force a syntax error while parsing the 2nd sibling element.
cases = {
  "syntax error inside 2nd aot element": "[[p]]\nx=1\n[[p]]\nx = =\n",
  "plain header inside aot (child collision)": "[[p]]\nx=1\n[[p]]\ny=2\n[p]\nz=3\n",
  "unclosed aot header": "[[p\n",
  "unclosed table header": "[a.b\n",
}
for label, text in cases.items():
    print("=====", label, "=====")
    orig = Parser._parse_aot
    events=[]
    def spy(self, first, name_first):
        events.append(("push", tuple(name_first), list(self._aot_stack)))
        try:
            r = orig(self, first, name_first)
        except Exception as e:
            events.append(("raise-in-aot", type(e).__name__, str(e)[:40], list(self._aot_stack)))
            raise
        events.append(("pop", list(self._aot_stack)))
        return r
    Parser._parse_aot = spy
    p = Parser(text)
    try:
        d = p.parse()
        print("  OK")
    except Exception as e:
        print(f"  {type(e).__name__}: {str(e)[:80]}")
    finally:
        Parser._parse_aot = orig
    for ev in events: print("   ", ev)
    print("   post-error _aot_stack:", p._aot_stack, "len:", len(p._aot_stack))
    # Is the parser reusable after a failure? idx is left at error site.
    print()
