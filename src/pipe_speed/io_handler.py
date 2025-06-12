"""输入解析与结果格式化输出

支持两种输入格式：
1. JSON: {"nodes": {...}, "edges": [...]}
2. 文本格式（自动检测）:
   node_name : max_flow    # 节点属性（可选）
   source -> target        # 管道连接
   source -> target : ?    # 查询：过滤输出
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .network import Network, build_network


@dataclass
class Query:
    """输出过滤器"""
    source: str | None = None   # 指定源节点（"*" = 通配）
    target: str | None = None   # 指定目标节点（"*" = 通配）
    node: str | None = None     # 指定节点（所有涉及该节点的管道）

    def matches(self, src: str, dst: str) -> bool:
        """判断一条管道是否匹配此查询"""
        if self.node is not None:
            return src == self.node or dst == self.node
        if self.source is not None and self.target is not None:
            s_ok = self.source == "*" or self.source == src
            t_ok = self.target == "*" or self.target == dst
            return s_ok and t_ok
        return True


def _match_any(queries: list[Query], src: str, dst: str) -> bool:
    """管道是否匹配任一查询；无查询时显示全部"""
    if not queries:
        return True
    return any(q.matches(src, dst) for q in queries)


def load_network(filepath: str) -> tuple[Network, list[Query]]:
    """从文件加载并构建网络（自动检测 JSON 或文本格式）

    Args:
        filepath: 输入文件路径，"-" 表示 stdin

    Returns:
        (Network, queries): 构建好的网络和输出过滤查询列表
    """
    if filepath == "-":
        content = sys.stdin.read()
    else:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {filepath}")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

    stripped = content.strip()
    if stripped.startswith("{"):
        net = _load_json(stripped)
        queries: list[Query] = []
    else:
        net, queries = _load_text(stripped)

    return net, queries


def _load_json(text: str) -> Network:
    """从 JSON 字符串加载网络"""
    data = json.loads(text)
    nodes_data = data.get("nodes", {})
    edges_data = data.get("edges", [])
    if not edges_data:
        raise ValueError("输入缺少 'edges' 字段")
    return build_network(nodes_data, edges_data)


def _is_query(line: str) -> bool:
    """判断一行是否为查询（以 : ? 结尾）"""
    return line.rstrip().endswith(": ?") or line.rstrip().endswith(":?")


def _parse_query(line: str) -> Query:
    """解析查询行，返回 Query 对象

    支持格式：
        x -> y : ?     → 精确匹配管道 x→y
        x -> * : ?     → 所有从 x 出发的管道
        * -> y : ?     → 所有到 y 的管道
        z : ?          → 所有涉及 z 的管道
    """
    # 去掉 : ? 后缀
    body = line.rsplit(":", 1)[0].strip()

    if "->" in body:
        parts = body.split("->")
        src = parts[0].strip()
        dst = parts[1].strip()
        return Query(source=src, target=dst)
    else:
        return Query(node=body)


def _load_text(text: str) -> tuple[Network, list[Query]]:
    """从文本格式加载网络

    格式:
        # 注释行
        node_name : max_flow    # 节点属性
        source -> target        # 管道
        x -> y : ?              # 查询（过滤输出）
        z : ?                   # 查询（节点相关所有管道）
    """
    nodes_data: dict[str, dict] = {}
    edges_data: list[dict] = []
    queries: list[Query] = []

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # 查询行（以 : ? 结尾）
        if _is_query(line):
            queries.append(_parse_query(line))
            continue

        if "->" in line:
            # 管道: source -> target
            parts = line.split("->")
            if len(parts) != 2:
                raise ValueError(f"无效的管道定义: '{line}'")
            src = parts[0].strip()
            dst = parts[1].strip()
            if not src or not dst:
                raise ValueError(f"无效的管道定义 (节点名为空): '{line}'")
            edges_data.append({"from": src, "to": dst})

        elif ":" in line:
            # 节点属性: name : max_flow
            parts = line.split(":", 1)
            if len(parts) != 2:
                raise ValueError(f"无效的节点定义: '{line}'")
            name = parts[0].strip()
            value_str = parts[1].strip()
            if not name:
                raise ValueError(f"无效的节点定义 (名称为空): '{line}'")
            try:
                max_flow = float(value_str)
            except ValueError:
                raise ValueError(f"无效的流速值: '{value_str}' (行: '{line}')")
            nodes_data[name] = {"max_flow": max_flow}

        else:
            raise ValueError(
                f"无法识别的行: '{line}'。"
                f"支持的格式: '节点 : 流速' / '源 -> 目标' / 'x -> y : ?'"
            )

    if not edges_data:
        raise ValueError("未找到任何管道定义（source -> target）")

    return build_network(nodes_data, edges_data), queries


def format_results(net: Network, iterations: int,
                   queries: list[Query] | None = None) -> str:
    """格式化输出管道流速结果

    格式: 源节点 → 目标节点  :  流速

    Args:
        net: 已求解的网络
        iterations: 收敛迭代次数
        queries: 可选的输出过滤器列表
    """
    if queries is None:
        queries = []

    lines = []
    for pipe in net.pipes:
        if _match_any(queries, pipe.source, pipe.target):
            flow = pipe.flow
            lines.append(f"{pipe.source} → {pipe.target}  :  {flow:.2f}")

    result = "\n".join(lines) if lines else "(无匹配结果)"

    if iterations > 1:
        result += f"\n\n(收敛于 {iterations} 次迭代)"
    else:
        result += f"\n\n(收敛于 {iterations} 次迭代)"

    return result


def print_results(net: Network, iterations: int,
                  queries: list[Query] | None = None) -> None:
    """打印结果到控制台"""
    print(format_results(net, iterations, queries))
