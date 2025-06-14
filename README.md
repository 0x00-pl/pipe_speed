# pipe-speed

流体网络管道流速计算器。输入元件与管道的连接关系，迭代求解每个管道的稳态流速。

## 安装

```bash
# 开发环境
git clone <repo>
cd pipe_speed
poetry install

# 含拓扑图渲染（可选）
poetry install --with visualize
```

## 快速开始

```
s -> a
a -> b
b -> c
```

```bash
pipe-speed network.txt
```

输出：

```
====== 结果 ======
s → a  :  120.00
a → b  :  120.00
b → c  :  120.00
(收敛于 2 次迭代)
```

## 输入文件格式

### 文本格式（推荐）

```
# 节点属性（可选，默认 max_flow=120）
l : 90

# 管道连接
s -> a
a -> l
l -> b
b -> c
c -> a
c -> d
d -> b
d -> e
d -> f

# 查询过滤（可选）
e : ?
f : ?
```

- `name : value` — 设置节点最大流速（默认 120）
- `source -> target` — 定义管道连接
- `#` 开头 — 注释行
- `-` 作为文件名 — 从 stdin 读取

### JSON 格式

```json
{
  "nodes": {
    "入口1": {"max_flow": 100},
    "分流1": {"max_flow": 80}
  },
  "edges": [
    {"from": "入口1", "to": "分流1"},
    {"from": "分流1", "to": "出口A", "max_flow": 40}
  ]
}
```

文件以 `{` 开头时自动检测为 JSON 格式。

## 元件类型

类型根据连接关系自动推断，无需手动指定：

| 入边 | 出边 | 类型 |
|------|------|------|
| 0 | ≥1 | 入口（Inlet）— 提供流体 |
| ≥1 | 0 | 出口（Outlet）— 消耗流体 |
| 1 | >1 | 分流器（Splitter）— 最多 3 输出 |
| >1 | 1 | 汇流器（Merger）— 最多 3 输入 |
| 1 | 1 | 限流器（Limiter） |

## CLI 参数

```
pipe-speed <input> [options]
```

| 参数 | 说明 |
|------|------|
| `input` | 网络定义文件，`-` 表示 stdin |
| `--show` | 显示网络 ASCII 拓扑图（需 `mermaidx`） |
| `--echo` | 回显解析后的网络内容 |
| `--json` | 以 JSON 格式输出结果 |
| `--epsilon N` | 收敛阈值（默认 1e-9） |
| `--max-iter N` | 最大迭代次数（默认 1000） |

## 查询过滤

在输入文件中添加查询行，仅输出匹配的管道流速：

| 语法 | 效果 |
|------|------|
| `x -> y : ?` | 仅显示管道 x→y |
| `x -> * : ?` | 显示所有从 x 出发的管道 |
| `* -> y : ?` | 显示所有到 y 的管道 |
| `z : ?` | 显示所有涉及 z 的管道 |
| 无查询行 | 显示全部管道 |

多条查询之间为 OR 关系。

## 示例

```bash
# 求解并显示拓扑图
pipe-speed network.txt --show

# 回显解析内容 + 拓扑图 + 结果
pipe-speed network.txt --echo --show

# 管道输入
cat network.txt | pipe-speed -

# JSON 输出
pipe-speed network.txt --json

# 仅显示拓扑（不装 mermaidx 时输出 Mermaid 源码）
pipe-speed network.txt --show
```

## 拓扑图渲染

`--show` 使用 [mermaidx](https://pypi.org/project/mermaidx/) 将网络渲染为 ASCII 盒图：

```
====== 拓扑 ======
┌─────┐
│  s  │
└──┬──┘
   ▼
┌─────┐
│  a  │◄─╮
└──┬──┘  │
   ▼     │
┌───────┐│
│ l : 6 ││
└──┬────┘│
   ▼     │
┌─────┐  │
│  c  ├──╯
└──┬──┘
   ▼
┌─────┐
│  d  │
└──┬──┘
   ├──────╮
   ▼      ▼
┌─────┐ ┌─────┐
│  e  │ │  f  │
└─────┘ └─────┘
```

安装 mermaidx：

```bash
poetry install --with visualize   # Poetry 开发环境
pip install mermaidx              # 已打包安装后
```

## 求解器

供需分离迭代法：管道维护 `supply`（上游想推）和 `capacity`（下游能接）两个独立变量，正向传播推 supply，反向传播拉 capacity，`flow = min(supply, capacity)`。对 DAG 和含环图均单调收敛。
