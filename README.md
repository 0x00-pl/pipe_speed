# pipe-speed

流体网络管道流速计算器。输入元件和管道连接关系，迭代求解每个管道的稳态流速。

## 安装

```bash
git clone <repo> && cd pipe_speed
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
(收敛于 2 次迭代)
```

## 输入格式

### 文本格式

```
l : 6              # 节点属性（默认 max_flow=120）
s -> a             # 管道连接
a -> l
l -> b
e : ?              # 查询过滤（可选）
```

- `name : value` — 节点 max_flow（默认 120）
- `source -> target` — 管道
- `name : ?` / `a -> b : ?` — 查询过滤
- `#` 注释、空行忽略

### JSON 格式

```json
{"nodes": {"n1": {"max_flow": 100}}, "edges": [{"from": "a", "to": "b"}]}
```

文件以 `{` 开头自动识别为 JSON。

## 元件类型

根据出入边数自动推断：

| 入 | 出 | 类型 |
|----|----|------|
| 0 | ≥1 | 入口 — 提供流体 |
| ≥1 | 0 | 出口 — 消耗流体 |
| 1 | >1 | 分流器 — 最多 3 出，均分 |
| >1 | 1 | 汇流器 — 最多 3 入，均抽 |
| 1 | 1 | 限流器 — 限制流速 |

## 参数

| 参数 | 说明 |
|------|------|
| `--show` | ASCII 拓扑图（需 mermaidx） |
| `--echo` | 回显解析后的网络 |
| `--fraction` | 精确分数 a/b 格式输出 |
| `--json` | JSON 格式输出 |
| `--epsilon N` | 收敛阈值（默认 1e-9） |
| `--max-iter N` | 最大迭代次数（默认 1000） |
| `-` | 文件名，表示 stdin |

## 示例

```bash
pipe-speed network.txt
pipe-speed network.txt --show --echo --fraction
cat network.txt | pipe-speed -
```

## 求解器

双 pass 迭代法：**capacity pass**（逆拓扑序）用 `draw_capacity` 均抽输入设 capacity → **supply pass**（正拓扑序）用 `push_supply` 均推输出设 supply。`flow = min(supply, capacity)` 解决供需。
