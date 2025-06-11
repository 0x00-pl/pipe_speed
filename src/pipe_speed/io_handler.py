"""JSON 输入解析与结果格式化输出"""

import json
from pathlib import Path

from .network import Network, build_network


def load_network(filepath: str) -> Network:
    """从 JSON 文件加载并构建网络

    Args:
        filepath: JSON 文件路径

    Returns:
        构建好的 Network 对象

    Raises:
        FileNotFoundError: 文件不存在
        json.JSONDecodeError: JSON 格式错误
        ValueError: 网络校验失败
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes_data = data.get("nodes", {})
    edges_data = data.get("edges", [])

    if not nodes_data:
        raise ValueError("输入文件缺少 'nodes' 字段")
    if not edges_data:
        raise ValueError("输入文件缺少 'edges' 字段")

    return build_network(nodes_data, edges_data)


def format_results(net: Network, iterations: int) -> str:
    """格式化输出管道流速结果

    格式: 源节点 → 目标节点  :  流速

    Args:
        net: 已求解的网络
        iterations: 收敛迭代次数

    Returns:
        格式化后的字符串
    """
    lines = []
    for i, pipe in enumerate(net.pipes):
        flow = pipe.flow
        lines.append(f"{pipe.source} → {pipe.target}  :  {flow:.2f}")

    result = "\n".join(lines)

    # 附加迭代信息
    result += f"\n\n(收敛于 {iterations} 次迭代)"

    return result


def print_results(net: Network, iterations: int) -> None:
    """打印结果到控制台"""
    print(format_results(net, iterations))
