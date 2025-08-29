"""CLI 入口：管道网络流速计算器

用法: pipe-speed input.json
"""

import argparse
import sys
from pathlib import Path

from .io_handler import format_echo, load_network, print_results
from .solver import solve
from .validate import validate

SEP = "====== {} ======"


def _read_input(filepath: str) -> str:
    if filepath == "-":
        raw = sys.stdin.read()
    else:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {filepath}")
        raw = path.read_text(encoding="utf-8")
    # 去除 UTF-8 BOM
    return raw.encode("utf-8").decode("utf-8-sig")


def main():
    parser = argparse.ArgumentParser(
        prog="pipe-speed",
        description="流体网络管道流速计算器 — 输入元件和管道连接，输出各管道稳态流速",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
输入文件格式:
  文本格式（自动检测）:
    node : max_flow    节点属性（可选，默认 120）
    source -> target   管道连接
    source -> target : ?  查询过滤
    z : ?              查询所有涉及 z 的管道
    # 注释             以 # 开头的行为注释

  JSON 格式（以 { 开头的文件自动检测）:
    {"nodes": {"n1": {"max_flow": 100}}, "edges": [{"from": "a", "to": "b"}]}

  文件名 "-" 表示从 stdin 读取。

元件类型根据连接关系自动推断:
  0入 ≥1出 → 入口     ≥1入 0出 → 出口
  1入 >1出 → 分流器   >1入 1出 → 汇流器
  1入 1出  → 限流器

示例:
  pipe-speed network.txt
  pipe-speed network.txt --show --echo
  cat network.txt | pipe-speed -
  pipe-speed network.json --json""",
    )
    parser.add_argument(
        "input_file",
        help="网络定义文件路径（- 表示 stdin）"
    )
    parser.add_argument(
        "--show", action="store_true",
        help="显示网络 ASCII 拓扑图（需 mermaidx）"
    )
    parser.add_argument(
        "--echo", action="store_true",
        help="回显解析后的网络内容"
    )
    parser.add_argument(
        "--fraction", action="store_true",
        help="以总入口流量的分数形式输出各管道流速"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="以 JSON 格式输出结果"
    )
    parser.add_argument(
        "--epsilon", type=float, default=1e-9,
        help="收敛阈值（默认 1e-9）"
    )
    parser.add_argument(
        "--max-iter", type=int, default=1000,
        metavar="N",
        help="最大迭代次数（默认 1000）"
    )

    args = parser.parse_args()

    # 读取输入（stdin 只读一次）
    try:
        raw_input = _read_input(args.input_file)
    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        net, queries = load_network(args.input_file, content=raw_input)
    except (ValueError, KeyError) as e:
        print(f"网络定义错误: {e}", file=sys.stderr)
        sys.exit(1)

    # --echo: 回显解析后的内容（管道 + 节点属性）
    if args.echo:
        print(SEP.format("输入"))
        print(format_echo(net, queries))

    # --show: 显示拓扑图（需 mermaidx）
    if args.show:
        print(SEP.format("拓扑"))
        from .io_handler import render_network
        print(render_network(net))

    # 求解
    iterations = solve(net, epsilon=args.epsilon, max_iterations=args.max_iter,
                       use_fraction=args.fraction)

    # 验证
    issues = validate(net)
    if issues:
        print("====== 验证失败 ======", file=sys.stderr)
        for issue in issues:
            print(f"  ✗ {issue}", file=sys.stderr)

    # 输出
    if not args.json:
        print(SEP.format("结果"))
    if args.json:
        import json
        matching = [
            p for p in net.pipes
            if not queries or any(
                q.matches(p.source, p.target) for q in queries
            )
        ]
        result = {
            "iterations": iterations,
            "pipes": [
                {
                    "source": p.source,
                    "target": p.target,
                    "flow": float(p.flow)
                }
                for p in matching
            ]
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_results(net, iterations, queries, fraction=args.fraction)


if __name__ == "__main__":
    main()
