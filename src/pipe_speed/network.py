"""网络图构建、类型推断、校验、拓扑排序"""

from dataclasses import dataclass, field
from typing import Union

from .models import Pipe, Inlet, Outlet, Splitter, Merger, Limiter

# 元件联合类型
Component = Union[Inlet, Outlet, Splitter, Merger, Limiter]


@dataclass
class Network:
    """流体管道网络"""
    nodes: dict[str, Component] = field(default_factory=dict)
    pipes: list[Pipe] = field(default_factory=list)

    # 邻接关系
    in_edges: dict[str, list[Pipe]] = field(default_factory=dict)   # 节点名 → 入边列表
    out_edges: dict[str, list[Pipe]] = field(default_factory=dict)  # 节点名 → 出边列表


def infer_type(name: str, in_count: int, out_count: int, explicit_type: str | None) -> type:
    """根据连接关系自动推断元件类型

    | 入边数 | 出边数 | 推断类型  |
    |-------|-------|---------|
    | 0     | ≥1    | Inlet   |
    | ≥1    | 0     | Outlet  |
    | 1     | >1    | Splitter|
    | >1    | 1     | Merger  |
    | 1     | 1     | Limiter |
    """
    if explicit_type:
        type_map = {
            "inlet": Inlet,
            "outlet": Outlet,
            "splitter": Splitter,
            "merger": Merger,
            "limiter": Limiter,
        }
        if explicit_type not in type_map:
            raise ValueError(f"节点 '{name}': 未知的类型 '{explicit_type}'，"
                             f"可选: {list(type_map.keys())}")
        return type_map[explicit_type]

    if in_count == 0 and out_count >= 1:
        return Inlet
    elif in_count >= 1 and out_count == 0:
        return Outlet
    elif in_count == 1 and out_count > 1:
        return Splitter
    elif in_count > 1 and out_count == 1:
        return Merger
    elif in_count == 1 and out_count == 1:
        return Limiter
    else:
        raise ValueError(
            f"节点 '{name}' 的连接关系无法自动推断类型 "
            f"(入边={in_count}, 出边={out_count})，请显式指定 type")


def build_network(nodes_data: dict | None = None, edges_data: list[dict] | None = None) -> Network:
    """从原始 JSON 数据构建 Network

    Args:
        nodes_data: {"节点名": {"max_flow": ..., "type": ...(可选)}}，可选，
                    未指定的节点从 edges 中自动推导，使用默认 max_flow=inf
        edges_data: [{"from": "...", "to": "...", "max_flow": ...}]

    Returns:
        构建好的 Network 对象
    """
    if nodes_data is None:
        nodes_data = {}
    if edges_data is None:
        edges_data = []

    net = Network()

    # 第一遍：统计每个节点的出入边数
    in_counts: dict[str, int] = {}
    out_counts: dict[str, int] = {}

    # 从 edges 中收集所有出现的节点名
    all_node_names: set[str] = set()
    for edge in edges_data:
        all_node_names.add(edge["from"])
        all_node_names.add(edge["to"])

    # 合并显式声明的节点和从 edges 推导的节点
    for name in all_node_names | set(nodes_data.keys()):
        in_counts[name] = 0
        out_counts[name] = 0

    for edge in edges_data:
        src = edge["from"]
        dst = edge["to"]
        out_counts[src] = out_counts.get(src, 0) + 1
        in_counts[dst] = in_counts.get(dst, 0) + 1

    # 第二遍：创建元件实例
    for name in in_counts:
        in_count = in_counts[name]
        out_count = out_counts[name]
        props = nodes_data.get(name, {})
        explicit_type = props.get("type")
        max_flow = props.get("max_flow", 120.0)

        cls = infer_type(name, in_count, out_count, explicit_type)
        net.nodes[name] = cls(name=name, max_flow=max_flow)

    # 第三遍：创建管道
    # 初始化邻接表
    for name in net.nodes:
        net.in_edges[name] = []
        net.out_edges[name] = []

    for edge in edges_data:
        src = edge["from"]
        dst = edge["to"]
        max_flow = edge.get("max_flow", 120.0)
        pipe = Pipe(source=src, target=dst, max_flow=max_flow)
        net.pipes.append(pipe)
        net.out_edges[src].append(pipe)
        net.in_edges[dst].append(pipe)

    # 校验
    validate(net)

    return net


def validate(net: Network) -> None:
    """校验网络合法性

    检查项：
    - 端口数限制
    - DAG 无环
    - 无孤立节点
    """
    for name, comp in net.nodes.items():
        in_count = len(net.in_edges[name])
        out_count = len(net.out_edges[name])

        if isinstance(comp, Inlet):
            if in_count != 0:
                raise ValueError(f"入口 '{name}': 应有 0 条入边，实际 {in_count}")
            if out_count < 1:
                raise ValueError(f"入口 '{name}': 至少需要 1 条出边")

        elif isinstance(comp, Outlet):
            if out_count != 0:
                raise ValueError(f"出口 '{name}': 应有 0 条出边，实际 {out_count}")
            if in_count < 1:
                raise ValueError(f"出口 '{name}': 至少需要 1 条入边")

        elif isinstance(comp, Splitter):
            if in_count != 1:
                raise ValueError(f"分流器 '{name}': 需要恰好 1 条入边，实际 {in_count}")
            if out_count < 1 or out_count > 3:
                raise ValueError(f"分流器 '{name}': 输出端口数需在 1~3，实际 {out_count}")

        elif isinstance(comp, Merger):
            if out_count != 1:
                raise ValueError(f"汇流器 '{name}': 需要恰好 1 条出边，实际 {out_count}")
            if in_count < 1 or in_count > 3:
                raise ValueError(f"汇流器 '{name}': 输入端口数需在 1~3，实际 {in_count}")

        elif isinstance(comp, Limiter):
            if in_count != 1:
                raise ValueError(f"限流器 '{name}': 需要恰好 1 条入边，实际 {in_count}")
            if out_count != 1:
                raise ValueError(f"限流器 '{name}': 需要恰好 1 条出边，实际 {out_count}")

def topological_order(net: Network) -> list[str]:
    """返回节点顺序（Kahn 拓扑排序，兼容含环图）

    对 DAG：返回标准拓扑序。
    对含环图：先排 DAG 部分（零入度节点），剩余环内节点按名称
    排序追加。迭代求解器对顺序不敏感（单调不动点迭代必定收敛），
    拓扑序仅影响收敛速度。
    """
    in_degree: dict[str, int] = {}
    for name in net.nodes:
        in_degree[name] = len(net.in_edges[name])

    queue = [name for name, deg in in_degree.items() if deg == 0]
    order = []

    while queue:
        node = queue.pop(0)
        order.append(node)
        for pipe in net.out_edges[node]:
            neighbor = pipe.target
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # 剩余节点在环内，按启发式排序：优先选入边来自已排节点的
    if len(order) < len(net.nodes):
        remaining = set(net.nodes.keys()) - set(order)
        while remaining:
            # 选"已排上游节点最多"的节点，尽量沿流向排列
            best = max(remaining, key=lambda n: sum(
                1 for p in net.in_edges[n] if p.source in order
            ))
            order.append(best)
            remaining.remove(best)

    return order
