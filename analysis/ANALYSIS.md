# tomlkit 的 Parser → Container 组织模型与编辑/重排边界

对象：tomlkit `0.15.1`（本仓库，`pyproject.toml` 固定），目标 TOML 1.1.0 合规
（`tests/test_toml_tests.py` 使用 `files-toml-1.1.0` 清单）。

本文区分三类结论，并在行文中显式标注：

- **[规范]** TOML 1.1.0 语义约束；任何符合规范的实现都必须如此。
- **[公开行为]** tomlkit 对外 API 的可观察结果，调用方可以依赖。
- **[实现现状]** 当前内部结构/方法/异常形态，未在公开文档承诺，升级可能变。

配套产物：

- `analysis/MINIMAL.toml`：同时含 dotted key、inline table、同项尾注释、空行、
  普通表与 `[[array-of-tables]]` 的最小文档（“a.b=1 后接 `[a]`”的字面组合在
  TOML 下非法，见 §4，故 `a.b = 1` 放在 `[a]` 表体内）。
- `analysis/structure_helper.py`：输出语义路径 / body 索引 / item 类型 /
  trivia 摘要，不输出对象地址。
- `tests/test_analysis_container_model.py`：26 个固定测试。

---

## 1. Container 不是有序字典：双结构 + 三类“无 key”槽

核心类：`tomlkit.container.Container`（`TOMLDocument` 只是它的子类，见
`tomlkit/toml_document.py`）。每个 `Container` 同时维护：

- `self._body: list[tuple[Key | None, Item]]`
  序列化时**逐槽遍历**的物理 token 流（`Container.as_string()`）。
- `self._map: dict[Key, int | tuple[int, ...]]`
  语义 key → body 位置。普通 key 值是一个 `int`；**out-of-order 表**是
  `tuple[int, ...]`，即一个语义 key 对应多个 body 项（§3）。
- `self._table_keys: list[Key]`：所有“真实表”表头 key 的追加顺序。
- `self._out_of_order_keys` / `self._validation_cache`：out-of-order 增量
  校验集合与解析期缓存（[实现现状]）。
- 另外通过 `dict.__setitem__` 维护一个“语义值”镜像，供 `dict` 协议使用；
  它会被同名片段覆盖/合并，**不能**用它还原文档布局。

`body` 里大量槽位的 key 是 `None`，它们不占语义、只占字节：

- `Whitespace`（`tomlkit.items.Whitespace`）：空行、缩进；序列化为原始字符串。
- `Comment`（`tomlkit.items.Comment`）：整行注释，trivia 为
  `Trivia(indent, comment_ws, comment, trail)`。
- `Null`（`tomlkit.items.Null`）：删除/替换后留下的**墓碑槽**，渲染为空串。

**结论**：普通“有序字典”只有 `key → 最后一个值`，既无法表达空行/整行注释/
墓碑槽，也无法表达一个语义 key 占据多个物理位置。tomlkit 的保真序列化依赖的
是 `_body`，`_map` 只是定位索引。

### 1.1 trivia 归属

- 普通叶子的值 item 持有 `Trivia(indent, comment_ws, comment, trail)`
  （字段含义见 `tomlkit/items.py:318`）。
  - `indent`：key 之前的空白（通常空，缩进由外层处理）。
  - `comment_ws` + `comment`：值后面到行尾注释的间距与注释本体。
  - `trail`：该逻辑行之后的换行。
- 整行注释是 body 中独立的 `Comment` 槽，不附着在邻居叶子上。
- 空行是 body 中独立的 `Whitespace("\n")` 槽；相邻两个空白槽在解析时由
  `Parser._merge_ws()` 合并。
- 表的 trivia 在 `Table.trivia`（表头前 `indent`、表头行尾注释、表头后
  `trail`）；AoT 本身 `Trivia(trail="")`，**每个元素 `Table` 各自持有**
  表头 trivia（`AoT.as_string()` 逐个渲染元素表）。
- inline table 内部把 `{ }` 之间的空格、逗号也建成 `Whitespace` 槽；其内
  叶子的 `trail` 解析时被置空（`_parse_key_value(parse_comment=False)`）。

---

## 2. Parser 如何把内容放进 Container

入口 `Parser.parse()`（`tomlkit/parser.py:175`）分两段：

1. 表外 KV 段：循环 `_parse_item()` 直到遇到第一个 `[`。
   - `_parse_item()` 遇到 `\n` 返回 `(None, Whitespace(...))`；遇到 `#`
     返回 `(None, Comment(...))`；遇到 KV 则 `_parse_key_value(True)`。
   - 多个 key（dotted）在 `_parse_key()` 中用 `Key.concat()` 合成
     `DottedKey`，随后由 `Container.append()` 的
     `_handle_dotted_key()` 物化成嵌套 super-table（见 §5）。
   - 每个 KV 直接 `body.append(key, value)` 到根 `TOMLDocument`。
2. 表段：循环 `_parse_table()`；返回的若是 AoT 首元素，立刻
   `_parse_aot()` 把后续兄弟收进一个 `AoT`，再整体 `body.append`。

解析进行中容器以 `Container(True)` 构造，`_parsed=True` 改变插入策略
（见 §6）；`parse()` 末尾 `body.parsing(False)` 统一翻转并清校验缓存。

### 2.1 `_parse_table()` 的状态（`parser.py:1006`）

进入时读取：

- `indent = self.extract()`：表头前的空白（来自 `_parse_item()` 的 marker）。
- `is_aot`：第二个 `[` 是否存在。
- `full_key = self._parse_key()`：完整表头 key（可能是 `a.b.c`）。
- `parent_name`：递归处理子表头时的前缀 key。

关键中间量：

- `name_parts = tuple(key)`：按 `.` 切出的 `SingleKey` 序列。
- `missing_table`：当 `len(name_parts) > len(parent_parts)+1`，说明
  直接写了 `[a.b.c]` 而当前作用域里没有 `a.b`，需要**补建隐式父表**。
- 补建循环从外层 `name_parts[0]` 开始逐层 `table.get(_name, 新建 Table)`、
  `table.raw_append(_name, child)`；除最深层外都标 `is_super_table=True`，
  最深层 AoT 叶子则 `raw_append(_name, AoT([child], parsed=True))`。
- 最深表的表头 trivia 来自 `(indent, cws, comment, trail)`；补建出的
  super-table 的 `indent=""`（不渲染表头，只在渲染叶子时参与）。

表体内层循环解析 KV；遇到下一个 `[` 时用 `_peek_table()`（克隆
`Source` 状态、非破坏预读）判断后续表头是否仍是 `full_key` 的子表：

- 是子表 → 递归 `_parse_table(full_key, table)` 并
  `table.raw_append(key_next, table_next)`，随后继续“拾取兄弟”直到遇到
  非子表头。
- 不是子表 → `break`，把表头交还 `parse()` 主循环处理。
- 收尾调用 `table.value._validate_out_of_order_table()`（解析期增量校验）。

`Parser` 上唯一的跨调用状态是 `self._aot_stack: list[Key]`：

- `_parse_aot()` 进入先 `self._aot_stack.append(name_first)`，循环用
  `_peek_table()` 收集同名 `[[...]]`，结束 `pop()`。
- 作用：区分“AoT 的下一个元素”与“同名普通表”，并让补建父表时
  `is_aot and name_parts[0] in self._aot_stack` 判断正确。

### 2.2 MINIMAL 的进出表轨迹（实测）

对 `analysis/MINIMAL.toml`（`analysis/scratch` 中脚本可复现）：

- 行 6 `[a]`：`parent_name=None, aot_stack=[]`；`name_parts=(a,)`；
  返回普通 `Table(display_name='a', is_super_table=False)`，内含
  `b`、`sibling` 两个叶子和尾部 `Whitespace('\n')`。
- 行 11 `[[products]]`：进入 `_parse_aot`，压栈
  `_aot_stack=[products]`；行 15 的第二个 `[[products]]` 由
  `_parse_table(parent_name=products)` 递归返回一个
  `is_aot_element=True` 的元素表；`_parse_aot` 弹栈，得到含 2 个元素的
  `AoT`，根 body 仅占 **1 个槽（索引 7）**。

根 `_map`（MINIMAL）：

| 语义 key | body 索引 | dotted |
|---|---:|---|
| root | 1 | False |
| title | 3 | **True** |
| meta | 4 | False |
| a | 6 | False |
| products | 7 | False |

body 索引 0/2/5 是 `Comment`/`Whitespace`，无 key。

### 2.3 inline table 解析

`Parser._parse_inline_table()`（`parser.py:700`）用一个独立的
`Container(True)` 收集：空白/注释照常进 body；KV 走
`_parse_key_value(False)`（不解析行尾注释、`trail=""`）；逗号建成
`Whitespace(",")`。最终 `InlineTable(elems, Trivia())`。因此 inline
table 也是“body + map”模型，只是渲染规则不同（`InlineTable.as_string()`）。

---

## 3. 一个语义 key 为何会对应多个 body 项：out-of-order 表

**[规范]** TOML 允许先写子表、后补父表（“defining a super-table afterwards
is ok”），也允许同一个表在文档中被多个不连续的表头“扩展”，前提是不重复
定义已定义的叶子/表。于是源码层面同一语义路径会出现多个物理片段。

### 3.1 解析落盘：`_raw_append()` 的 tuple 索引

`Container._raw_append()`（`container.py:454`）规则：

- key 首次出现：`self._map[key] = len(self._body)`，再 append body。
- key 已存在且当前是 `Table`：`self._map[key] = (*old_indices, new_index)`，
  并记入 `self._out_of_order_keys`；旧位置和新位置都保留在 body 中。

例（测试 `test_out_of_order_semantic_key_spans_multiple_body_slots`）：

```toml
[a]      # body 0：具体表片段，含 x
x = 1
[zz]     # body 1：无关表
q = 2
[a.b]    # body 2：a 的第二个片段（super-table），解析期把 b、d 都收进这里
c = 3
[a.d]
e = 4
```

根 `_map == {'a': (0, 2), 'zz': 1}`：**语义上一个 `a`，物理上两个 body
项，中间还夹着 `zz`**。第二个片段的内部 body 是 `[b(Table), d(Table)]`
（因为 `[a.b]` 进入时是 `_parse_table(parent_name=None)`，随后 `[a.d]`
被 `_parse_table` 的“拾取兄弟”循环收进同一个片段表）。

### 3.2 读取聚合：`OutOfOrderTableProxy`

`Container.item(key)` 发现 tuple 索引时**不返回单个 item**，而是构造
`tomlkit.container.OutOfOrderTableProxy(container, indices)`（每次访问新建，
[实现现状]）。Proxy 在 `__init__` 里：

- 按 tuple 顺序取每个片段 `Table` 存入 `self._tables`；
- 把片段 body 中各项 `_raw_append` 进一个临时 `self._internal_container`
  （`AoT` 片段用 `_merge_aot_fragment()` 合并，避免在内部容器里撞名）；
- `_tables_map: dict[Key, list[int]]` 记录每个子 key 出现在哪些片段；
- 构造末尾 `_internal_container._validate_out_of_order_table()` 做完整
  合并校验（把各片段 deepcopy 到临时容器试拼），冲突即抛错。

因此 `doc["a"]` 拿到的是聚合视图，`unwrap()` 得到
`{"x":1,"b":{"c":3},"d":{"e":4}}`；`doc.body` 里仍能看到两个片段。
**序列化不走 Proxy**：`Container.as_string()` 逐 body 槽渲染，各片段各自
带自己的表头输出，靠 trivia/super-table 规则还原出与输入一致的字节。

### 3.3 dotted key 的物化

`Container._handle_dotted_key()`（`container.py:135`）把多片段 key 转成
**嵌套 super-table 链**：`a.b.c = 1` 在根 body 中是一个
key=`a`（`SingleKey`，但 `_dotted=True`）的 super-table，里面一层
key=`b`（dotted）的 super-table，叶子 `c` 是普通 `Integer`。
渲染时 `_render_table()` 对“key dotted 的 super-table”内联输出
`a.b.c = 1`，而不是打 `[a]`/`[b]` 表头。

---

## 4. 三类非法输入：发现点与暂存清理

错误都由 `Container.append()` / `_validate_table_candidate()` /
`OutOfOrderTableProxy.validate()` 抛出；`Parser.parse()` 根循环用
`try ... except Exception as e: raise self.parse_error(ParseError, str(e))`
包装成带行列号的 `ParseError`。**[实现现状]** 递归子表内部（`_parse_table`
经 `raw_append`）抛出的冲突发生在进入根循环 try 之前，因此会以原始
`TOMLKitError` 冒泡、没有行列号（见
`test_dotted_key_vs_table_header_conflict` 同时接受两种类型）。

### 4.1 同一路径非法重定义

| 输入 | 发现点（行列） | 底层异常 |
|---|---|---|
| `a = 1\na = 2` | 第 2 行 col 0 | `KeyAlreadyPresent` |
| `[products]` 后 `[[products]]` | 第二个表头（第 4 行 col 0） | `KeyAlreadyPresent`（append 中“plain table 与 AoT 同名”分支） |
| `[a]` 后再次 `[a]` | 第二个 `[a]`（第 4 行 col 0） | `KeyAlreadyPresent` |

**[规范]** 同一 key 不能定义两次、表名不能与 AoT 名互换。

### 4.2 先 child 后 parent

- `[a.b]\nc=1` 后 `[a]\nd=2`：**合法**（super-table 后定义）。
  `[a]` 片段 `_parsed=True` 并入已有结构；`_validate_table_candidate()`
  发现只是新增叶子，放行。
- 若后面再跟一个 `[a.b]\ne=3`：**非法**，在第 6 行（重开的 `[a.b]`
  表头，col 0）抛 `KeyAlreadyPresent`。

### 4.3 dotted key 与 table 冲突

- 表内：`[a]\nb.c = 1` 然后 `[a.b]\nd=2` —— dotted 键 `b.c` 已经把 `b`
  隐式建成表，再用 `[a.b]` 表头定义即重复定义。在
  `_validate_table_candidate()` 的 dotted-prefix 检查处抛
  `TOMLKitError("Redefinition of an existing table")`（本版本此路径为
  原始 `TOMLKitError`，无行列号）。
- 根级：`a.b = 1` 然后 `[a]\nz=2` —— 同样在根循环被包装成
  `ParseError`（第 3 行 col 0，cause 为 `TOMLKitError`）。

> 注：本任务最初设想的“同一文档里既有 `a.b = 1` 又有后续 `[a]`”正是
> **[规范] 禁止的重复定义**（dotted 已隐式定义该表）。MINIMAL 文档据此把
> `b = 1` 放在 `[a]` 表体中；根级 dotted 用独立的 `title.sub` 展示
> super-table 物化。

### 4.4 “暂存状态”是什么、如何清理

- Parser 不维护回滚日志。解析结果是 `parse()` 内的局部
  `TOMLDocument body`；出错前已 append 的内容确实存在于该局部容器
  （实测重复 `[a]` 时根 body 已有第一个 `a` 表，重复 KV 时已有第一个
  KV），但异常使 `parse()` 不返回它 → **调用方拿不到半成品**，等价于
  “整份解析丢弃”。
- `Source` 的预读用 `_State` 上下文（`tomlkit/source.py`）在异常时恢复
  `idx/current`；`_peek_table()` 全程 `restore=True`，预读不污染位置。
- **[实现现状] 一个真实的残留**：若 AoT 第二个元素的**表体内部**发生语法
  错误（如 `[[p]]` 后 `x = =`），`_parse_aot()` 已 `append(name_first)`
  但异常跳过了 `pop()`，抛出后 `parser._aot_stack` 残留一个 key
  （实测长度 1）。该 Parser 对象随后即被丢弃，所以不影响成功路径；但
  “出错后 Parser 状态完全复原”并不成立。

---

## 5. 编辑后由谁决定 trivia 与序列化位置

所有写入最终都汇到 `Container.append()` / `_insert_at()` /
`_insert_after()` / `_replace_at()` / `remove()`（`container.py`）。

### 5.1 改叶值：`__setitem__` → `_replace_at()`

`Container.__setitem__`：key 已存在则 `_replace(old_key, new_key, value)`。
`_replace_at()`（`container.py:871`）：

- 先 `item = _item(value)` 做类型转换（转换失败在此处，未触碰 body）。
- 同类替换（值→值）：**就地拷贝旧 trivia**
  （`indent/comment_ws/comment/trail`），只换 body 槽里的 item，`_map`
  索引不变。这就是 `b = 1 # leaf trailing` 改成 `b = 42` 后注释与位置
  原样保留的原因。
- 异构替换（值 ↔ Table/AoT）或 dotted key 变表头：先 `remove(k)`（旧槽
  变 `Null`、删 map），再把新值插入正确区域。新表/新 AoT 会越过所有
  “内联渲染”的叶子和 dotted super-table，插到第一个真实表头之前
  （`_replace_at` 中扫描 `self._body` 的循环），避免表头吞掉后续兄弟
  （对应 issue #513/#524/#542 的修复逻辑）。

### 5.2 给已有表加 sibling：`Table.__setitem__` → `Container.append`

`Table.append`/`AbstractTable.__setitem__` 最终调用内层
`Container.append`。解析后文档 `_parsed=False`：当容器里已有真实表、而
新 item 不是表（或 key dotted）时，`append()` 调
`_get_last_index_before_table()` 找到“最后一个非表槽”，用
`_insert_at()` 把新叶子插到表区之前；若上一项没有换行，则给
`previous_item.trivia.trail += "\n"` 或给被插项的 `indent` 补 `"\n"`。

- 在已解析的具体表 `[a]` 内加 `new_key`：直接 append 到它内部容器尾部
  （表内尚无“后续真实表头”分隔问题），落在 `sibling` 之后、表尾空行
  `Whitespace` 之前；缩进由 `Table.__setitem__` 按表头 indent 模式套用。
- 在**根**容器给一个已经跟着若干表头的文档加新叶子：新叶子不会出现在
  文件末尾（会被当成最后一个表的成员），而是被提到所有真实表头之前。

### 5.3 dotted key / super-table 如何影响插入位置

- `_get_last_index_before_table()` 对 key `is_dotted()` 的 super-table
  有专门分支：一旦该 dotted super-table 内部有子项会渲染成真实表头
  （`_renders_table_header()`），它就被视为“表区边界”，后续 append 的
  叶子只能插在它之前，否则会被该表头作用域吞掉。
- 两个同名 super-table 合并（`append()` 的大分支）时：若 key dotted 或
  这是一个与已有片段不连续的新 super-table，会选择“新建片段 + tuple
  索引”（`_insert_at` / `_raw_append` 后 `_validate_out_of_order_table`），
  保持表头在文档中的物理顺序；连续补父表则**就地并入**已有表的内部
  container。
- `_table_keys[-1]`、`key.is_dotted()` 决定是“就地合并”还是“追加为新的
  out-of-order 片段”。

### 5.4 删 AoT 元素：`AoT.__delitem__`

`del doc["products"][0]` 直接命中 `AoT.__delitem__`（`items.py`），
从 `AoT._body` 列表删除该元素 `Table`。**根 body 的 AoT 槽、`_map`
索引完全不动**；`AoT.as_string()` 少渲染一个元素表（每个元素表自带
表头 trivia，删元素即删表头与表体）。这与“删语义 key”
（`Container.remove()` 把槽换成 `Null`）是两条路径。

### 5.5 替换 inline table

- 用 `tomlkit.inline_table()` 构造并赋值：新旧同为 InlineTable，走
  `_replace_at()` 的同类分支，**原位保留 body 索引并继承旧尾注释**
  （实测 `meta = {p = 10} # inline trailing`，索引仍是 4）。
- **[公开行为] 易错点**：`doc["meta"] = {"p": 10}`（普通 dict）经
  `tomlkit.items.item()` 工厂转换；在 document/table 层级 `_parent` 不是
  `Array/InlineTable`，dict 默认变成**普通 `Table`**（只有在 array 或
  inline table 内部才会造 `InlineTable`）。于是走异构替换：旧 inline
  槽变 `Null`，新 `[meta]` 表头被移到表区（`_replace_at` 重定位），
  原来的尾注释也随之不再附着在原位置。要保持 inline 必须显式
  `inline_table()`（或在 array/inline 里赋 dict）。

---

## 6. 修改中途抛错：公开 API 不承诺事务性

文档与 docstring（`docs/`、`Container`/`Table`/`AoT`）**没有任何**
atomic/transaction/rollback 承诺。实测边界如下（最小实验，
`tests/test_analysis_container_model.py` 固定）。

### 6.1 能观察到“部分改变”的公开调用

`Container.append()` 在“同名 key 当前是 `AoT`、新 item 是 super-table
且该 AoT 非空”分支里，直接扩展最后一个元素：

```python
last = current[-1]
for k, v in item.value.body:
    last.value.append(k, v)   # 逐个写进活的 AoT 元素，无回滚
```

构造：文档含 `[[p]] id=1`，append 一个 `is_super_table=True` 的 `p`
片段，其 body 先加新子表 `g`（合法）、再加 `id` 子表（与最后一个元素
已有的叶子 `id` 冲突）。纯公开 API 复现：

```python
doc = parse("[[p]]\nid = 1\n")
extra = table(is_super_table=True)
g = table(); g["v"] = 1; extra["g"] = g
bad = table(); bad["deep"] = 2; extra["id"] = bad
doc.append(key("p"), extra)   # 抛 KeyAlreadyPresent
```

实测：异常抛出后 `doc` **已被部分修改**——`[p.g] v=1` 已经进入最后一个
AoT 元素，冲突的 `[p.id]` 未写入；序列化结果与改前不同（本例仍可
reparse，但语义已变）。**结论：不能把一次失败的公开编辑推断为原子
“无变化”；可见边界是“循环中冲突点之前的兄弟已提交”。**

### 6.2 另一处静默边界：空 AoT 替换 out-of-order key

把 tuple 索引的 out-of-order 表替换成**空 `aot()`**：`_replace_at()`
先 `remove(k)` 清掉全部旧片段，随后 `append()` 命中空 AoT 的早返回
（空 AoT 渲染为空串）。结果：

- 内存 dict 视图仍含该 key（`"a" in doc` 为真，`_map` 指向新 AoT 槽）；
- `dumps(doc)` 完全不输出它，reparse 后该 key 消失；
- 之后 `doc["a"].append({...})` 又会以 `[[a]]` 在新位置出现。

### 6.3 天然原子的常见路径（对照）

- 值转换类错误（`ConvertError`，如给 setitem/`array.append` 传不可转换
  对象）：`item(value)` 在任何 body 改动之前执行，失败不留痕。
- 解析期 append：super-table 合并前先跑 `_validate_table_candidate()`，
  冲突在就地合并之前抛出（实测先冲突后不改动）。
- 同类叶子替换：trivia 拷贝在单次槽位赋值内完成。

即：原子性是“碰巧因为顺序”而非 API 契约；涉及多片段、循环合并、
AoT 扩展或空容器的操作必须自行在副本上试改（如先 `copy()`/在独立
`parse` 上演练）再落回。

---

## 7. 结构检查 helper

`analysis/structure_helper.py`（无第三方依赖、不打印对象地址）：

- `describe_document(doc)` / `structure_text(doc)`：递归遍历每个
  Container，按 body 物理顺序输出 `语义路径 :: item 类型 :: dotted ::
  trivia 摘要`，并单独打印该容器的 `_map`（int 或 tuple 索引）。
  AoT 元素路径形如 `products[1].name`；无 key 槽形如 `a#body2`。
- `map_of(c)`：`{语义 key: int | tuple}`。
- `body_index(c, k)`：单个语义 key 的 body 位置。
- `body_types(c)`：`[(key|None, item 类名), ...]`，适合在测试里固定。
- `out_of_order_proxy(doc, k)`：取聚合用 `OutOfOrderTableProxy`。
- `trivia_summary(item)`：把 `\n/\r/\t` 转义成单行文本。

示例（MINIMAL 节选）：

```
TOMLDocument <root>
  map: root -> 1 (dotted=False), title -> 3 (dotted=True),
       meta -> 4 (dotted=False), a -> 6 (dotted=False), products -> 7 ...
  [3] title :: Table dotted=True :: indent='' ... trail='\n'
  [7] products :: AoT dotted=False :: indent='' ... trail=''
AoTElement products[1]
  [1] products[1].name :: String dotted=False :: ... comment='' trail='\n'
```

## 8. 关键类与方法索引（供复核）

- 解析：`Parser.parse`、`Parser._parse_item`、`Parser._parse_key_value`、
  `Parser._parse_key`/`concat`、`Parser._parse_table`、
  `Parser._parse_aot`、`Parser._peek_table`、`Parser._parse_inline_table`、
  `Parser._merge_ws`；`Source` / `_State`（位置快照与恢复）。
- 容器：`Container._body/_map/_table_keys/_out_of_order_keys`、
  `append`、`_handle_dotted_key`、`_get_last_index_before_table`、
  `_renders_table_header`、`_validate_out_of_order_table`、
  `_validate_table_candidate`、`_raw_append`、`_insert_at`、
  `_insert_after`、`_replace`/`_replace_at`、`remove`/`_remove_at`、
  `item`、`as_string`/`_render_table`/`_render_aot`/`_render_simple_item`。
- 聚合：`OutOfOrderTableProxy.validate`（deepcopy 试拼）、`__init__`、
  `_merge_aot_fragment`、`__setitem__`、`__delitem__`、`_remove_table`。
- 条目：`Key/SingleKey/DottedKey`（`is_dotted/is_multi/concat`）、
  `Trivia`、`Whitespace/Comment/Null`、`AbstractTable/Table`（
  `append/raw_append/is_super_table/is_aot_element`）、`InlineTable`、
  `AoT`（`_body/insert/__delitem__/as_string`）、`item()` 工厂。
- 异常：`ParseError`（带 line/col）、`TOMLKitError`、`KeyAlreadyPresent`、
  `NonExistentKey`，以及 `ConvertError`（值转换，`api.items` 路径）。

## 9. 规范 / 公开行为 / 实现现状 小结

- **[规范]**：dotted key 隐式定义 super-table，禁止再用同名表头重复定义；
  表/AoT 同名互换非法；key 不可重复定义；先子后父（super-table 后补）
  合法；AoT 之后出现的子表表头扩展最后一个元素。
- **[公开行为]**：解析保真（`dumps(parse(x)) == x`，MINIMAL 已固定）；
  同类叶子替换继承 trivia 与槽位；删 AoT 元素只动 `AoT._body`；
  `inline_table()` 原位替换，裸 dict 在表/文档层变 `[table]` 并重定位；
  `doc.item(out_of_order_key)` 返回聚合视图；失败的多片段 append 可能
  已部分生效（无事务承诺）；空 AoT 替换会在 dump 中静默丢键。
- **[实现现状]**：`_map` 用 tuple 标记多片段、`body` 保留 `Null` 墓碑；
  Proxy 每次访问新建、靠 deepcopy 做校验；嵌套子表冲突可能以无行列号的
  `TOMLKitError` 冒泡；AoT 元素体内语法错误会残留 `_aot_stack`；
  `_parsed` 标志切换解析期/编辑期插入策略。这些内部形态升级时可能调整，
  不应作为外部依赖。

## 10. 复现实验

一次性追踪脚本（临时、非交付测试的一部分）在 `analysis/scratch/`：
body/map 打印、进出表 trace、out-of-order proxy、四类编辑、非法输入与
行列号、`_aot_stack` 残留、非原子 append、空 AoT 丢键均可直接
`poetry run python analysis/scratch/<name>.py` 复现。
