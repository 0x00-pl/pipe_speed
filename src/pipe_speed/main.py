"""CLI 入口：管道网络流速计算器

用法: pipe-speed input.json
"""

import argparse
import sys
from pathlib import Path

from .io_handler import load_network, print_results, render_network, format_echo
from .solver import solve

SEP = "===="


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
        description="管道网络流速计算器 — 输入元件和管道连接，输出各管道稳态流速"
    )
    parser.add_argument(
        "input_file",
        help="网络定义文件，- 表示 stdin（支持 JSON 或文本格式）"
    )
    parser.add_argument(
        "--epsilon", type=float, default=1e-9,
        help="收敛阈值（默认 1e-9）"
    )
    parser.add_argument(
        "--max-iter", type=int, default=1000,
        help="最大迭代次数（默认 1000）"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="以 JSON 格式输出结果"
    )
    parser.add_argument(
        "--show", action="store_true",
        help="显示网络拓扑图（之后继续求解）"
    )
    parser.add_argument(
        "--echo", action="store_true",
        help="回显输入内容"
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
        print(format_echo(net, queries))
        print(SEP)

    # --show: 显示拓扑图后继续求解
    if args.show:
        print(render_network(net))
        print(SEP)

    # 求解
    iterations = solve(net, epsilon=args.epsilon, max_iterations=args.max_iter)

    # 输出
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
                    "flow": round(p.flow, 6)
                }
                for p in matching
            ]
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_results(net, iterations, queries)


if __name__ == "__main__":
    main()
