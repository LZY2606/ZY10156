# tomlkit Container 内部机制分析

基于本仓库 vendored 的 tomlkit 0.15.1（fork 自 python-poetry/tomlkit @ 8c959b5）。
文中结论分三层标注：**【规范】** TOML v1.0 约束；**【公开行为】** 通过
`tomlkit.parse` / `dumps` / `Container` 公开方法可观察的行为；**【内部实现】**
当前代码的实现细节（私有属性、私有方法），不保证跨版本稳定。
所有行为均有 `tests/test_container_structure.py` 中的测试固定，
结构转储由 `tests/structure_helper.py` 生成。

## 1. Container 不是有序字典

【内部实现】`tomlkit.container.Container`（`tomlkit/container.py:35`）由两套
互补结构组成：

- `_body: list[tuple[Key | None, Item]]`（`container.py:44`）——**线性序列**，
  保留文档的物理顺序。除键值对外还包含三类无 key 的条目：
  `Whitespace`（空行）、`Comment`（整行注释）、`Null`（删除后留下的占位墓碑，
  `container.py:483`）。序列化 `as_string()`（`container.py:633`）只做一件事：
  按 `_body` 顺序逐项渲染。
- `_map: dict[Key, int | tuple[int, ...]]`（`container.py:43`）——**语义索引**，
  把 `Key` 映射到 body 下标。值为 `int` 表示常规项；值为 `tuple` 表示该语义 key
  对应**多个** body 项（out-of-order table，见第 2 节）。

辅助状态：`_table_keys`（按出现顺序记录 table 型 key，用于判断"上一个 table
是不是同一个 key"）、`_out_of_order_keys` 与 `_validation_cache`
（本 fork 为增量验证引入，见 `container.py:48-56`）。
`dict` 接口（`__getitem__`/`__setitem__`/`__contains__`）只是投影在这两套
结构之上的视图；`Container.parsing(False)`（`container.py:102`）在解析结束时
把 `_parsed` 置 False，之后编辑路径才会启用空白补全等"美化"逻辑。

## 2. 一个语义 key 为何对应多个 body 项

【内部实现】`_raw_append`（`container.py:454`）在 `key` 已存在于 `_map` 且
当前值是 `Table` 时，把 `_map[key]` 从 `int` 升级为 `tuple`，把新 fragment
追加到 `_body` 末尾，并把 key 记入 `_out_of_order_keys`。触发场景：

1. **out-of-order table**：`[a]` … `[b]` … `[a.c]`。`[a.c]` 到达时 `a`
   已是具体 table，新 fragment（包着 `c` 的 super table `a`）不能就地合并，
   只能作为第二个 body 项追加，保持物理顺序不变。
2. **先声明 child 后声明 parent**：`[a.b]` 隐式创建 super table `a`，随后的
   `[a]` header 是合法 TOML【规范】，tomlkit 把它存为 `a` 的第二个 fragment
   （`_map['a'] == (0, 1)`，见 `test_child_table_before_parent_is_also_out_of_order`）。
3. dotted key 产生的 super table 与后续同类 fragment 冲突时同理。

【公开行为】`Container.item()`（`container.py:610`）发现 `_map` 值是 tuple
时返回 `OutOfOrderTableProxy`（`container.py:1011`）而不是 `Table`。proxy 用
`_internal_container` 把所有 fragment 的键聚合到一个命名空间，用
`_tables_map` 记录每个键来自哪些 fragment；读操作透明，写操作
（`__setitem__`，`container.py:1066`）决定落到哪个 fragment——纯值优先写进
"已含纯值的 fragment"，否则优先写进"非 super 的 fragment"（避免把无 header 的
super fragment 变成具体 table 而渲染出重复 header）。删除某个键可能通过
`_remove_table` 把整个 fragment 从 `_body` 移除。

【内部实现】合法性由 `Container._validate_out_of_order_table`
（`container.py:191`）和 `OutOfOrderTableProxy.validate`
（`container.py:1014`）保证：把各 fragment 的条目 **deep-copy** 后重放进一个
临时 `Container`，冲突（如同名键类型不一致）在重放时抛出。本 fork 用
`_validation_cache` 做增量验证；异常路径会 `pop` 掉被污染的缓存项
（`container.py:217-221`），`remove`/`_remove_at`/`_replace_at` 也会清空缓存。

## 3. Parser 如何填充 Container

【内部实现】`Parser.parse()`（`parser.py:175`）分两段：

1. 第一段循环用 `_parse_item`（`parser.py:250`）收 root 级键值对，遇 `[` 停止。
   `_merge_ws`（`parser.py:215`）把相邻 `Whitespace` 合并，避免 body 里出现
   连续空白项。
2. 第二段循环反复调 `_parse_table`（`parser.py:1006`）。每个 table 的条目进入
   该 table 自己的 `Container(True)`（parsed 模式），而不是 root——所以
   **空行归属于它前面的 table**，root body 里只剩带 key 的项。

关键机制：

- **trivia 归属**：`_parse_key_value`（`parser.py:361`）把行前空白记入
  `value.trivia.indent`；`_parse_comment_trail`（`parser.py:292`）把行尾
  `  # comment` 拆成 `comment_ws`/`comment`，换行记入 `trail`。即
  **同项尾注释挂在值的 `Trivia`（`items.py:318`）上，不占 body 条目**；
  整行注释才是独立的 `Comment` body 项。
- **dotted key**：`Container.append` 发现 `key.is_multi()` 时转入
  `_handle_dotted_key`（`container.py:135`）：`a.b = 1` 被改写成
  `a`（`SingleKey`，`_dotted=True`）→ super `Table` → `b = 1`。
  super table 渲染时不输出自己的 header（`items.py:1945` 的
  `is_super_table` 与 `container.py:661` 的 `_render_table` 共同决定），
  于是仍序列化为 `a.b = 1`。
- **进入/退出 table**：`_parse_table` 内用 `_peek_table`（`parser.py:1165`）
  前瞻下一个 header，用 `_is_child`（`parser.py:237`，严格前缀且不相等）
  判断归属；是子表就递归 `_parse_table(parent_name=full_key)` 并
  `raw_append` 进当前 table，然后继续"捡拾"同级子表。缺少中间层时
  （如直接出现 `[a.b.c]`）创建 `is_super_table=True` 的隐式父表。
  遇到 `[[name]]` 且 `_aot_stack` 顶不是同名 AoT 时，`_parse_aot`
  （`parser.py:1192`）连续收集同名元素打包成 `AoT`。
- 实测事件序列（`test_parser_table_entry_exit_trace` 固定）：对
  `tests/test_container_structure.py` 中的 `DOC`，顺序为
  `enter[server] → enter[server.opts] → exit opts → exit server →
  enter[[products]] → enter_aot → enter[products]#2（_aot_stack 深度 1）
  → exit → exit_aot(2 元素） → exit products → enter[a] → exit a`，
  结束后 `_aot_stack` 为空。

解析后 root `_map` 为 `{server: 0, products: 1, a: 2}`，body 仅 3 个带 key
的条目；完整结构转储见 `EXPECTED_STRUCTURE`（由 `tests/structure_helper.py`
的 `describe()` 生成，不含对象地址）。

## 4. 编辑时谁决定 trivia 与序列化位置

【公开行为 + 内部实现】四次实验（均有字节级断言）：

| 操作 | 决定位置的代码 | 结果 |
| --- | --- | --- |
| 改叶值 `server.a.b = 2` | `Container._replace_at`（`container.py:871`）同类型分支：复制旧值的 `indent/comment_ws/comment/trail` | 原位替换，`# dotted leaf` 保留，其余字节不变 |
| 给 `[server]` 加 sibling `c = "new"` | `Container.append` 检测到 container 已含 table 且新项非 table → `_get_last_index_before_table`（`container.py:153`）跳过 `Null` 与非 fixed `Whitespace`，在第一个"非 dotted 的 Table/AoT"或"会渲染 header 的 dotted super table"（`_renders_table_header`，`container.py:179`）前停下 → `_insert_at`（`container.py:563`） | 插到 body[1]：`a.b = 1` 之后、空行与 `[server.opts]` 之前 |
| 删除 AoT 元素 `del products[0]` | `AoT.__delitem__`（`items.py:2318`）直接删 `_body` 元素 | 该元素的 trivia（含其内部空行）随之消失；剩余元素保留自己的 trivia，位置不动 |
| 替换 inline table | 用 `tomlkit.inline_table()`：同类型替换，继承旧 trivia，原地渲染；用普通 `dict`：`items.item()`（`items.py:138`）在父为 table 时构造**标准 Table**，`_replace_at` 走类型变化分支——先 `remove` 再把新 table 插到"第一个真正 header 之前"（避免吞掉后续行内项，见 `container.py:871` 处 #513/#524/#542 注释） | 前者仍是 `mode = {...}`；后者变成 `[server.opts.mode]` 小节并移位 |

一般规则：未修改项的 trivia 原样保留（序列化就是按 body 重放 trivia）；
新项的换行/缩进由 `Container.append`/`_insert_at`/`Table.append`
（`items.py:1894`）的补 `\n` 与缩进复制逻辑现场决定；解析期
（`_parsed=True`）这些美化逻辑全部关闭。

## 5. 错误路径与暂存状态清理

三类非法输入（均有测试）：

| 输入 | 发现位置 | 异常 |
| --- | --- | --- |
| `[a]` 后再 `[a]`（同路径重定义） | 第二个 header 解析完、`Parser.parse` 调 `body.append` 时：`Container.append` 的 `current` 非 super 且 `item` 非 super → `KeyAlreadyPresent`（`container.py:306` 附近） | 被 `parse()` 包装成 `ParseError`，带 `line 2` 行号 |
| `[a.b]` 后 `[a]` 且 `[a]` 内 `b = 2`（先 child 后 parent 且冲突） | root append `[a]` 时 `_validate_table_candidate`（`container.py:420`）发现既有 `b` 是 Table 而新 `b` 是 Integer → `KeyAlreadyPresent` | `ParseError`，`line 4` |
| `[a]` 内 `b.c = 1` 后接 `[a.b]`（dotted key 与 table 冲突） | 嵌套 `_parse_table` 内 `Table.raw_append` → `Container.append` 发现现存 key 是 dotted super table（`container.py:332-335`）→ 直接 `raise TOMLKitError` | **裸 `TOMLKitError`**，不经过 `parse()` 包装，无行号——错误类型取决于发现位置，这是当前实现的不对称点 |

暂存状态的清理：

- **解析失败**：在建的 `TOMLDocument` 随异常传播被整体丢弃，没有任何部分
  结果发布；`Parser` 实例本身不可复用但也不会污染后续解析
  （`test_failed_parse_publishes_no_partial_document`）。
- **解析期增量验证**：`_validate_out_of_order_table` 捕获异常时
  `pop` 掉该 key 的 `_validation_cache` 项，避免带毒缓存被重试复用。
- **编辑失败**：见下节。

## 6. 事务性：公开 API 不承诺原子性

【公开行为】`Container.append` 的执行顺序是**先 `_raw_append` 修改
`_body`/`_map`，后 `_validate_out_of_order_table` 校验**
（`container.py:417-419`）。实验
（`test_failed_edit_leaves_partial_mutation`）：对
`[a.b]\nx = 1\n[c]\ny = 2\n` 的文档 `doc.append("a", 冲突 fragment)`，
抛出 `KeyAlreadyPresent` 后：

- `_map['a']` 已变成 `(0, 2)`——fragment 留在 body 里，没有回滚；
- `dumps(doc)` 输出含两个 `[a.b]` 的**非法 TOML**，再 parse 会失败。

可见边界：**异常抛出点之前已完成的 mutation 全部保留**，单次公开调用
也可能部分生效。需要原子性的调用方必须自己在编辑前 `copy.deepcopy`
文档。注意解析（`tomlkit.parse`）是全部或没有——失败时拿不到任何文档；
部分突变只发生在**编辑**路径。

## 7. 规范 / 公开行为 / 内部实现对照

- 【规范】TOML v1.0：table 不可重复定义；dotted key 会定义其全部父级
  table，因此 root 级 `a.b = 1` 之后不允许再出现 `[a]`（tomlkit 以
  "Redefinition of an existing table" 拒绝，`test_root_dotted_key_cannot_be_followed_by_its_table_header`）；
  `[a.b]` 后再写 `[a]` 合法；AoT 同名元素必须连续。
- 【公开行为】round-trip 字节保持；编辑后 trivia 的保留/补全规则（第 4 节）；
  out-of-order key 读出为 `OutOfOrderTableProxy`；编辑 API 非事务。
- 【内部实现】`_body`/`_map` 双结构、tuple 索引、`_validation_cache`、
  错误是否被包装成 `ParseError` 取决于抛出位置等，均为当前版本细节，
  本文与测试只用于固定现状，不构成兼容承诺。
