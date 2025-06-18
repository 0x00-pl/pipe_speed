"""管道网络流速求解器

迭代算法（按用户伪代码）:
  1. flow = min(sum(input.supply), max_flow)
  2. capacity: 从 max_flow 出发，均抽输入 supply → 反压上游
  3. supply:  从 current_flow 出发，均分到输出 capacity → 推流下游

每次迭代: 反向 pass 算 capacity, 正向 pass 算 supply
"""

import math
from fractions import Fraction

from .models import Pipe, Inlet, Outlet, Splitter, Merger, Limiter
from .network import Network, topological_order

INF = float('inf')
EPS = 1e-12


def _val(x: float) -> float:
    """安全值: inf → 0"""
    return 0.0 if math.isinf(x) else x


def _cap(x: float) -> float:
    """安全 capacity: inf → 大数"""
    return 1e30 if math.isinf(x) else x


# === 核心算法：均抽 (capacity) 和 均推 (supply) ===

def _draw_capacity(max_flow: float, supplies: list[float]) -> list[float]:
    """从 max_flow 出发，均抽各输入的 supply，返回各输入分配的 capacity

    算法（用户伪代码）:
      flow = max_flow
      caps = [0, 0, ...]
      s = [copy of supplies]
      loop:
        e = min(s)                    # 最小剩余 supply
        f = min(e * len(active), flow) # 本轮能抽的总量
        flow -= f
        每个 active 输入: cap += f / len(active), s -= f / len(active)
        删除 s == 0 的输入
      until flow == 0 or no active
    """
    n = len(supplies)
    if n == 0:
        return []

    caps = [0.0] * n
    remaining = [max(s, 0.0) for s in supplies]
    flow = max_flow if not math.isinf(max_flow) else INF
    active = list(range(n))

    while flow > EPS and active:
        e = min(remaining[i] for i in active)
        if e <= EPS:
            # 跳过已耗尽的
            active = [i for i in active if remaining[i] > EPS]
            continue
        f = min(e * len(active), flow)
        flow -= f
        per = f / len(active)
        for i in list(active):
            caps[i] += per
            remaining[i] -= per
            if remaining[i] <= EPS:
                active.remove(i)

    return caps


def _push_supply(current_flow: float, capacities: list[float]) -> list[float]:
    """从 current_flow 出发，均推到各输出的 capacity，返回各输出分配的 supply

    算法（用户伪代码）:
      flow = current_flow
      supplies = [0, 0, ...]
      c = [copy of capacities]
      loop:
        e = min(c)                    # 最小剩余 capacity
        f = min(e * len(active), flow) # 本轮能推的总量
        flow -= f
        每个 active 输出: supply += f / len(active), c -= f / len(active)
        删除 c == 0 的输出
      until flow == 0 or no active
    """
    n = len(capacities)
    if n == 0:
        return []

    out_supplies = [0.0] * n
    remaining = [max(c, 0.0) for c in capacities]
    flow = current_flow if not math.isinf(current_flow) else INF
    active = list(range(n))

    while flow > EPS and active:
        e = min(remaining[i] for i in active)
        if e <= EPS:
            active = [i for i in active if remaining[i] > EPS]
            continue
        f = min(e * len(active), flow)
        flow -= f
        per = f / len(active)
        for i in list(active):
            out_supplies[i] += per
            remaining[i] -= per
            if remaining[i] <= EPS:
                active.remove(i)

    return out_supplies


# === 求解器 ===

def solve(net: Network, epsilon: float = 1e-9, max_iterations: int = 1000,
          use_fraction: bool = False) -> int:
    """迭代求解管道网络流速"""
    order = topological_order(net)
    rev_order = list(reversed(order))

    # 初始化 supply=1（打破零不动点）
    for p in net.pipes:
        p.supply = 1.0

    prev_flows = [float(p.flow) for p in net.pipes]

    for iteration in range(max_iterations):
        # === 正向 pass: 计算 supply ===
        for name in order:
            comp = net.nodes[name]
            in_p = net.in_edges[name]
            out_p = net.out_edges[name]
            mf = comp.max_flow

            # 1. flow = min(sum(input_supply), max_flow)
            total_in = sum(_val(p.supply) for p in in_p)
            if math.isinf(mf):
                flow = total_in
            else:
                flow = min(total_in, mf)

            # 无输出 → 跳过
            if not out_p:
                continue

            # 各元件共享的输出逻辑：flow → 均推到各输出 capacity
            def _push_out(flow_val):
                caps = [min(_cap(p.capacity), _cap(p.max_flow)) for p in out_p]
                supplies = _push_supply(flow_val, caps)
                for p, s in zip(out_p, supplies):
                    p.supply = s

            if isinstance(comp, Inlet):
                f = mf if not math.isinf(mf) else INF
                _push_out(f)

            elif isinstance(comp, Outlet):
                pass

            elif isinstance(comp, Splitter):
                _push_out(flow)

            elif isinstance(comp, Merger):
                _push_out(flow)

            elif isinstance(comp, Limiter):
                _push_out(flow)

        # === 反向 pass: 计算 capacity ===
        for name in rev_order:
            comp = net.nodes[name]
            in_p = net.in_edges[name]
            out_p = net.out_edges[name]
            mf = comp.max_flow

            # 无输入：跳过 capacity 计算
            if not in_p:
                continue

            if isinstance(comp, Inlet):
                # 入口无上游
                pass

            elif isinstance(comp, Outlet):
                # 出口：慷慨容量 = max_flow
                cap = mf if not math.isinf(mf) else INF
                if cap < INF:
                    each = cap / len(in_p)
                    for p in in_p:
                        p.capacity = each

            elif isinstance(comp, Splitter):
                # 分流器：capacity = 实际能输出的量
                total_out = sum(_val(p.supply) for p in out_p)
                f = total_out if math.isinf(mf) else min(total_out, mf)
                in_p[0].capacity = f

            elif isinstance(comp, Merger):
                # 汇流器：瓶颈时均抽，非瓶颈时慷慨
                supplies = [_val(p.supply) for p in in_p]
                total_supply = sum(supplies)
                downstream_cap = _cap(out_p[0].capacity) if out_p else INF
                total_cap = mf if math.isinf(mf) else min(mf, downstream_cap)
                if not math.isinf(total_cap) and total_cap < total_supply - EPS:
                    # 瓶颈：均抽
                    caps = _draw_capacity(total_cap, supplies)
                else:
                    # 非瓶颈：慷慨（超额供给不破坏守恒，因 forward pass 限制输出）
                    caps = [total_cap] * len(in_p)
                for p, c in zip(in_p, caps):
                    p.capacity = c

            elif isinstance(comp, Limiter):
                # 限流器：容量 = min(max_flow, 下游 capacity)
                c_out = _cap(out_p[0].capacity) if out_p else INF
                cap = mf if math.isinf(mf) else min(mf, c_out)
                in_p[0].capacity = cap

        # === 收敛判断 ===
        max_delta = 0.0
        for i, p in enumerate(net.pipes):
            new_flow = float(p.flow)
            delta = abs(new_flow - prev_flows[i])
            if delta > max_delta:
                max_delta = delta
            prev_flows[i] = new_flow

        if max_delta < epsilon:
            break

    if use_fraction:
        for p in net.pipes:
            p.supply = Fraction(float(p.supply)).limit_denominator(10**8)
            p.capacity = Fraction(float(p.capacity)).limit_denominator(10**8)

    return iteration + 1
