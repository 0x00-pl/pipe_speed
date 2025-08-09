# pipe-speed

流体网络管道流速计算器。描述元件和管道的连接关系，迭代求解稳态流速。

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
f : ?              # 仅输出 e、f 相关管道
```

### JSON 格式

```json
{"nodes": {"n1": {"max_flow": 100}}, "edges": [{"from": "a", "to": "b"}]}
```

文件以 `{` 开头自动识别。

## 元件

类型根据出入边数自动推断：

| 入边 | 出边 | 类型 | 行为 |
|------|------|------|------|
| 0 | ≥1 | 入口 | 提供流体，supply = max_flow |
| ≥1 | 0 | 出口 | 消耗流体，capacity = max_flow |
| 1 | >1 | 分流器 | 均分到各输出，受 capacity 约束溢出重分配 |
| >1 | 1 | 汇流器 | 均抽各输入，受 supply 约束缺口重分配 |
| 1 | 1 | 限流器 | flow = min(in, max_flow, downstream_cap) |

所有 max_flow 默认值 120。可显式指定：`name : value`。

## 参数

| 参数 | 说明 |
|------|------|
| `input` | 网络文件，`-` = stdin |
| `--show` | ASCII 拓扑图（mermaidx） |
| `--echo` | 回显解析后的网络 |
| `--fraction` | 精确分数 a/b 输出 |
| `--json` | JSON 输出 |
| `--epsilon N` | 收敛阈值 (1e-9) |
| `--max-iter N` | 最大迭代 (1000) |

## 求解器

双 pass 迭代，每轮：

1. **capacity pass**（逆拓扑序）— 出口设慷慨容量 → 限流器/分流器/汇流器用 `_fair_allocate` 均抽输入 supply 反压上游
2. **supply pass**（正拓扑序）— 入口直设 supply → 各元件用 `_fair_allocate` 均推到输出 capacity

管道 `flow = min(supply, capacity)`。对数图和含环图均收敛。

### `_fair_allocate(total, limits)`

核心分配算法：将 `total` 均分到 N 路，受 `limits` 约束。某路达限后，剩余流量在其余路中重分配。O(N²) 确定性实现（sorted list，无 set）。

## 查询过滤

在输入文件中追加，仅输出匹配管道：

| 语法 | 效果 |
|------|------|
| `a -> b : ?` | 仅 a→b |
| `a -> * : ?` | 所有 a 出发 |
| `* -> b : ?` | 所有到 b |
| `z : ?` | 所有涉及 z |

多条 OR 关系。

## 验证

CLI 求解后自动运行 `validate()`：检查每节点守恒性、用 `_fair_allocate` 验证容量/供应分配是否与期望一致。验证失败输出到 stderr。

## 文件结构

```
src/pipe_speed/
├── models.py      # Pipe/Inlet/Outlet/Splitter/Merger/Limiter 数据类
├── network.py     # 图构建、类型推断、拓扑排序
├── solver.py      # 双 pass 迭代求解
├── validate.py    # _fair_allocate + 守恒/分配验证
├── io_handler.py  # JSON/文本解析、格式化输出
└── main.py        # CLI 入口
```

## 示例

```bash
pipe-speed net.txt --show --echo --fraction
cat net.txt | pipe-speed -
pipe-speed net.json --json
```
