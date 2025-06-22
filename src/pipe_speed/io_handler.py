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


def load_network(filepath: str, content: str | None = None) -> tuple[Network, list[Query]]:
    """从文件加载并构建网络（自动检测 JSON 或文本格式）

    Args:
        filepath: 输入文件路径，"-" 表示 stdin
        content: 可选，预读取的内容（避免重复读取 stdin）

    Returns:
        (Network, queries): 构建好的网络和输出过滤查询列表
    """
    if content is not None:
        pass  # 使用传入的内容
    elif filepath == "-":
        content = sys.stdin.read()
    else:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {filepath}")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

    # 去除 UTF-8 BOM
    content = content.encode("utf-8").decode("utf-8-sig")
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
                   queries: list[Query] | None = None,
                   fraction: bool = False) -> str:
    """格式化输出管道流速结果

    格式: 源节点 → 目标节点  :  流速

    Args:
        net: 已求解的网络
        iterations: 收敛迭代次数
        queries: 可选的输出过滤器列表
        fraction: True 时使用精确分数格式 a/b
    """
    if queries is None:
        queries = []

    from fractions import Fraction

    lines = []
    for pipe in net.pipes:
        if _match_any(queries, pipe.source, pipe.target):
            flow = pipe.flow
            if fraction:
                if isinstance(flow, Fraction):
                    f_str = f"{flow.numerator}/{flow.denominator}"
                else:
                    f_str = str(Fraction(flow).limit_denominator(10**8))
                # 相对于满速（管道 max_flow）的比例
                max_f = Fraction(pipe.max_flow).limit_denominator(10**8) if not isinstance(pipe.max_flow, Fraction) else pipe.max_flow
                if max_f > 0:
                    f_val = flow if isinstance(flow, Fraction) else Fraction(flow).limit_denominator(10**8)
                    ratio = f_val / max_f
                    r_str = f"{ratio.numerator}/{ratio.denominator}"
                    lines.append(f"{pipe.source} → {pipe.target}  :  {f_str}  ({r_str})")
                else:
                    lines.append(f"{pipe.source} → {pipe.target}  :  {f_str}")
            else:
                lines.append(f"{pipe.source} → {pipe.target}  :  {float(flow):.2f}")

    result = "\n".join(lines) if lines else "(无匹配结果)"

    if iterations > 1:
        result += f"\n\n(收敛于 {iterations} 次迭代)"
    else:
        result += f"\n\n(收敛于 {iterations} 次迭代)"

    return result


def print_results(net: Network, iterations: int,
                  queries: list[Query] | None = None,
                  fraction: bool = False) -> None:
    """打印结果到控制台"""
    print(format_results(net, iterations, queries, fraction=fraction))


def format_echo(net: Network, queries: list[Query] | None = None) -> str:
    """将解析后的网络回显为规范文本格式

    输出节点属性（max_flow ≠ 120 时）和管道连接，
    末尾附查询行（如有）。
    """
    lines = []

    # 节点属性（仅非默认值）
    for name, comp in sorted(net.nodes.items()):
        mf = getattr(comp, 'max_flow', 120)
        if mf != 120:
            lines.append(f"{name} : {mf:.0f}")

    # 管道
    for pipe in net.pipes:
        lines.append(f"{pipe.source} -> {pipe.target}")

    # 查询
    if queries:
        for q in queries:
            if q.node:
                lines.append(f"{q.node} : ?")
            elif q.source and q.target:
                lines.append(f"{q.source} -> {q.target} : ?")

    return "\n".join(lines)


def render_network(net: Network) -> str:
    """以文字形式绘制网络拓扑图

    生成 Mermaid 语法，由 mermaidx 渲染为 ASCII 盒图。
    mermaidx 为可选依赖。
    """
    if not net.nodes:
        return "(空网络)"

    # 生成 Mermaid 语法
    mermaid = _to_mermaid(net)

    try:
        import mermaidx
        d = mermaidx.render(mermaid)
        return d.ascii()
    except ImportError:
        return (
            "mermaidx 未安装，无法渲染。请运行：\n"
            "  poetry install --with visualize   # Poetry 开发环境\n"
            "  pip install mermaidx             # 已打包安装后\n\n"
            f"Mermaid 源码:\n{mermaid}"
        )
    except Exception as e:
        # mermaidx 渲染失败时回退到 Mermaid 源码
        return f"(渲染失败: {e})\n\nMermaid 源码:\n{mermaid}"


def _to_mermaid(net: Network) -> str:
    """将网络转为 Mermaid 流程图语法"""
    lines = ["graph TD"]

    # 定义节点（仅非默认 max_flow 时附加标签）
    for name, comp in net.nodes.items():
        mf = getattr(comp, 'max_flow', 120)
        if mf != 120:
            lines.append(f"    {name}[{name} : {mf:.0f}]")

    for pipe in net.pipes:
        src = pipe.source
        dst = pipe.target
        lines.append(f"    {src} --> {dst}")
    return "\n".join(lines)
