"""CLI 入口：管道网络流速计算器

用法: pipe-speed input.json
"""

import argparse
import sys

from .io_handler import load_network, print_results
from .solver import solve


def main():
    parser = argparse.ArgumentParser(
        description="管道网络流速计算器 — 输入元件和管道连接，输出各管道稳态流速"
    )
    parser.add_argument(
        "input_file",
        help="JSON 格式的网络定义文件（nodes + edges）"
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

    args = parser.parse_args()

    try:
        # 加载网络
        net, queries = load_network(args.input_file)
    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
    except (ValueError, KeyError) as e:
        print(f"网络定义错误: {e}", file=sys.stderr)
        sys.exit(1)

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
