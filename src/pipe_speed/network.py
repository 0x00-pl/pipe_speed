"""网络图构建、类型推断、校验、拓扑排序"""

from dataclasses import dataclass, field

from .models import Inlet, Limiter, Merger, Outlet, Pipe, Splitter

# 元件联合类型
Component = Inlet | Outlet | Splitter | Merger | Limiter


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

    # 第一遍：统计每个节点的出入边数（使用 dict 保证确定性顺序）
    in_counts: dict[str, int] = {}
    out_counts: dict[str, int] = {}

    # 从 edges 中收集所有出现的节点名（用 dict 保持出现顺序，避免 set 不确定）
    all_node_names: dict[str, None] = {}
    for edge in edges_data:
        all_node_names[edge["from"]] = None
        all_node_names[edge["to"]] = None
    for name in nodes_data:
        all_node_names[name] = None

    for name in all_node_names:
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

    return net


def topological_order(net: Network, reverse: bool = False) -> list[str]:
    """返回节点顺序（Kahn 拓扑排序，兼容含环图）

    reverse=False: 标准拓扑序（入度零优先）
    reverse=True:  反向拓扑序（出度零优先）
    """
    if not reverse:
        degree = {name: len(net.in_edges[name]) for name in net.nodes}
        queue = [n for n, d in degree.items() if d == 0]
        def neighbours(n):
            return [p.target for p in net.out_edges[n]]
        upstream_attr = 'source'
    else:
        degree = {name: len(net.out_edges[name]) for name in net.nodes}
        queue = [n for n, d in degree.items() if d == 0]
        def neighbours(n):
            return [p.source for p in net.in_edges[n]]
        upstream_attr = 'target'

    order = []
    while queue:
        node = queue.pop(0)
        order.append(node)
        for neighbor in neighbours(node):
            degree[neighbor] -= 1
            if degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) < len(net.nodes):
        remaining = [n for n in net.nodes if n not in order]
        while remaining:
            best = max(remaining, key=lambda n: sum(
                1 for p in net.in_edges[n]
                if getattr(p, upstream_attr) in order
            ))
            order.append(best)
            remaining.remove(best)

    return order
