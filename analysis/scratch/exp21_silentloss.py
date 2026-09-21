from tomlkit import parse, aot

text = "[a]\nx=1\n[zz]\nq=2\n[a.b]\nc=3\n"
doc = parse(text)
print("before map:", {str(k).strip(): v for k,v in doc._map.items()})
ret = doc["a"] = aot()
print("assigned empty AoT len:", len(doc["a"]))
out = doc.as_string()
print("--- dumped ---")
print(out)
print("'a' in dict view:", "a" in doc, "| len(doc):", len(doc))
print("map after:", {str(k).strip(): v for k,v in doc._map.items()})
print("body after:", [(str(k).strip() if k else None, type(v).__name__) for k,v in doc.body])
reparsed = parse(out)
print("reparsed unwrap:", reparsed.unwrap(), "| 'a' present:", "a" in reparsed)

# Now append an element to that aot AFTER the loss
doc["a"].append({"y": 9})
print("--- after appending element ---")
print(doc.as_string())
print("reparse:", parse(doc.as_string()).unwrap())
