# pipe-speed

流体网络管道流速计算器。描述元件与管道连接关系，迭代求解稳态流速。

## 安装

```bash
poetry install
```

## 快速开始

```
s -> a
a -> b
b -> c
```

```bash
$ pipe-speed network.txt
====== 结果 ======
s → a  :  120.00
a → b  :  120.00
b → c  :  120.00
```

## 输入格式

### 文本格式（推荐）

```
l : 6              # 节点 max_flow（默认 120）
s -> a             # 管道
a -> l
e : ?              # 查询过滤
```

- `name : value` — 设置节点 max_flow
- `source -> target` — 定义管道
- `name : ?` / `a -> b : ?` — 查询过滤
- `#` 注释、空行忽略
- `-` 作为文件名从 stdin 读取

### JSON 格式

```json
{"nodes": {"n1": {"max_flow": 100}}, "edges": [{"from": "a", "to": "b"}]}
```

以 `{` 开头自动识别。

## 元件

类型根据出入边数自动推断：

| 入 | 出 | 类型 | 行为 |
|----|----|------|------|
| 0 | ≥1 | 入口 | 供流，supply = max_flow |
| ≥1 | 0 | 出口 | 耗流，capacity = max_flow |
| 1 | >1 | 分流器 | 均分输出，受 capacity 约束溢出重分配 |
| >1 | 1 | 汇流器 | 均抽输入，受 supply 约束缺口重分配 |
| 1 | 1 | 限流器 | flow = min(in, max_flow, downstream_cap) |

默认 max_flow = 120。

## 参数

| 参数 | 说明 |
|------|------|
| `--show` | ASCII 拓扑图（mermaidx） |
| `--echo` | 回显解析后的网络 |
| `--fraction` | 精确分数 a/b 输出 |
| `--json` | JSON 输出 |
| `--epsilon N` | 收敛阈值 (1e-9) |
| `--max-iter N` | 最大迭代 (1000) |

## 求解器

双 pass 迭代：

1. **capacity pass**（逆拓扑序）— 出口设慷慨容量 → 各元件用 `_fair_allocate` 均抽设上游 capacity。限制值根据管道状态：输出受限（supply > capacity）用 `pipe.max_flow`，输入受限用 `pipe.supply`。
2. **supply pass**（正拓扑序）— 入口设 supply → 各元件用 `_fair_allocate` 均推下游 supply。限制值：输入受限（supply < capacity）用 `pipe.max_flow`，输出受限用 `pipe.capacity`。

管道 `flow = min(supply, capacity)`。

### `_fair_allocate(total, limits)`

均分 total 到 N 路，受 limits 约束。某路达限后剩余流量重分配。O(N²) 确定性实现。

## 验证

CLI 求解后自动 `validate()`：检查每节点守恒 + 用 `_fair_allocate` 验证容量/供应分配。失败输出到 stderr。

## 文件结构

```
src/pipe_speed/
├── models.py      # Pipe/Inlet/Outlet/Splitter/Merger/Limiter
├── network.py     # 图构建、类型推断、拓扑排序
├── solver.py      # 双 pass 迭代求解
├── validate.py    # _fair_allocate + 守恒/分配验证
├── io_handler.py  # JSON/文本解析、格式化输出
└── main.py        # CLI 入口
```

## 测试

```bash
poetry run pytest tests/ --cov=pipe_speed
# 102 tests, 97% coverage
```
