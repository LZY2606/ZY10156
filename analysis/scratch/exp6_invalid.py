import tomlkit
from tomlkit.parser import Parser
from tomlkit.exceptions import ParseError, TOMLKitError

CASES = {
"same_path_redef_aot_after_table": '''\
[products]
id = 1
[[products]]
id = 2
''',
"same_path_redef_table_twice": '''\
[a]
x = 1
[a]
y = 2
''',
"same_path_redef_key_twice": '''\
a = 1
a = 2
''',
"child_before_parent_ok": '''\
[a.b]
c = 1

[a]
d = 2
''',
"child_before_parent_then_parent_redef_child": '''\
[a.b]
c = 1
[a]
d = 2
[a.b]
e = 3
''',
"dotted_vs_table_inorder": '''\
[a]
b.c = 1
[a.b]
d = 2
''',
"dotted_vs_table_root": '''\
a.b = 1
[a]
z = 2
''',
"super_after_sub_valid_spec": '''\
[x.y]
z = 1

[x]
w = 2
''',
}

for name, text in CASES.items():
    print(f"===== {name} =====")
    try:
        doc = tomlkit.parse(text)
    except (ParseError, TOMLKitError) as e:
        print(f"  RAISE {type(e).__name__}: {e}")
    else:
        print("  OK:", doc.unwrap())
