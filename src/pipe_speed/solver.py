"""管道网络流速求解器

每条管道维护 supply（上游推入）和 capacity（下游接受）。
每轮迭代中，每个元件独立：
  1. 求和输入 supply → 施加 max_flow → 得到当前 flow
  2. 根据 flow 和输出 capacity，按输出逻辑更新输出管道的 supply
  3. 根据 flow 和 max_flow，按输入逻辑（剩余均分）更新输入管道的 capacity

采用 Jacobi 风格：所有元件基于上轮快照独立计算，统一写入。
"""

import math
from fractions import Fraction
from typing import Union

from .models import Pipe, Inlet, Outlet, Splitter, Merger, Limiter
from .network import Network, topological_order

Num = Union[float, Fraction]
INF = float('inf')
EPS = 1e-12


# === 公平分配算法 ===

def fair_distribute(total: float, caps: list[float]) -> tuple[list[float], float]:
    """均分 total 到 N 路，受 caps 约束，剩余返回"""
    n = len(caps)
    if n == 0:
        return [], total
    a = [0.0] * n
    remaining = total
    active = list(range(n))
    while remaining > EPS and active:
        per = remaining / len(active)
        capped = sorted(i for i in active if per >= caps[i] - a[i] - EPS)
        if capped:
            for i in capped:
                take = caps[i] - a[i]
                a[i] = caps[i]
                remaining -= take
                active.remove(i)
        else:
            for i in active:
                a[i] += per
            remaining = 0.0
    return a, remaining


def fair_draw(target: float, supplies: list[float]) -> tuple[list[float], float]:
    """均抽 target 从 N 路，受 supplies 约束，缺口返回"""
    n = len(supplies)
    if n == 0:
        return [], target
    d = [0.0] * n
    needed = target
    active = list(range(n))
    while needed > EPS and active:
        per = needed / len(active)
        exhausted = sorted(i for i in active if per >= supplies[i] - d[i] - EPS)
        if exhausted:
            for i in exhausted:
                take = supplies[i] - d[i]
                d[i] = supplies[i]
                needed -= take
                active.remove(i)
        else:
            for i in active:
                d[i] += per
            needed = 0.0
    return d, needed


# === 安全取值 ===

def _val(x: float) -> float:
    return 0.0 if math.isinf(x) else x


def _cap(x: float) -> float:
    """capacity 安全值：inf → 很大数，用于比大小"""
    return 1e30 if math.isinf(x) else x


# === 正向传播（推 supply）===

def _forward(net: Network, name: str) -> None:
    """按用户算法：求和输入 supply → 输出逻辑设下游 supply"""
    comp = net.nodes[name]
    in_p = net.in_edges[name]
    out_p = net.out_edges[name]
    mf = comp.max_flow

    # 求 flow
    total_in = sum(_val(p.supply) for p in in_p)
    if math.isinf(mf):
        flow = total_in
    else:
        flow = min(total_in, mf)

    if isinstance(comp, Inlet):
        flow = mf if not math.isinf(mf) else INF
        if out_p:
            each = flow / len(out_p)
            for p in out_p:
                p.supply = each

    elif isinstance(comp, Outlet):
        pass  # 出口无下游

    elif isinstance(comp, Splitter):
        if in_p:
            flow = min(_val(in_p[0].supply), mf if not math.isinf(mf) else INF)
        if out_p:
            caps = [min(_cap(p.capacity), _cap(p.max_flow)) for p in out_p]
            assigned, _ = fair_distribute(flow, caps)
            for p, a in zip(out_p, assigned):
                p.supply = a

    elif isinstance(comp, Merger):
        if out_p:
            out_p[0].supply = flow

    elif isinstance(comp, Limiter):
        if out_p:
            out_p[0].supply = flow


# === 反向传播（拉 capacity）===

def _backward(net: Network, name: str) -> None:
    """按用户算法：flow → 输入逻辑（剩余均分）设上游 capacity"""
    comp = net.nodes[name]
    in_p = net.in_edges[name]
    out_p = net.out_edges[name]
    mf = comp.max_flow

    # 求 flow
    total_in = sum(_val(p.supply) for p in in_p)
    if math.isinf(mf):
        flow = total_in
    else:
        flow = min(total_in, mf)

    if isinstance(comp, Inlet):
        pass  # 入口无上游

    elif isinstance(comp, Outlet):
        # 出口告知上游自己能接受的最大量（慷慨容量）
        cap = mf if not math.isinf(mf) else INF
        if in_p and cap < INF:
            each = cap / len(in_p)
            for p in in_p:
                p.capacity = each

    elif isinstance(comp, Splitter):
        if in_p and out_p:
            # 实际能输出的总量 = sum(out supplies)（从正向 pass 来）
            total_out = sum(_val(p.supply) for p in out_p)
            cap = total_out if math.isinf(mf) else min(total_out, mf)
            in_p[0].capacity = min(_cap(in_p[0].capacity), cap)

    elif isinstance(comp, Merger):
        if in_p:
            supplies = [_val(p.supply) for p in in_p]
            total_supply = sum(supplies)
            # 瓶颈判断：输出能力 < 总供应？
            downstream_cap = _cap(out_p[0].capacity) if out_p else INF
            total_cap = min(mf if not math.isinf(mf) else INF, downstream_cap)
            if not math.isinf(total_cap) and total_cap < total_supply - EPS:
                # 瓶颈：fair_draw 均抽
                drawn, _ = fair_draw(total_cap, supplies)
                for p, d in zip(in_p, drawn):
                    p.capacity = min(_cap(p.capacity), d)
            else:
                # 非瓶颈：慷慨容量，允许上游分流器溢出
                for p in in_p:
                    p.capacity = min(_cap(p.capacity), total_cap)

    elif isinstance(comp, Limiter):
        if in_p:
            c_out = _cap(out_p[0].capacity) if out_p else INF
            cap = min(mf if not math.isinf(mf) else INF, c_out)
            in_p[0].capacity = min(_cap(in_p[0].capacity), cap)


# === 求解器 ===

def solve(net: Network, epsilon: float = 1e-9, max_iterations: int = 1000,
          use_fraction: bool = False) -> int:
    """Gauss-Seidel 风格迭代求解

    按拓扑序遍历元件，读即时管道状态，写即时管道状态。
    每个元件处理所有相连管道的 supply/capacity 更新。
    """
    order = topological_order(net)
    rev_order = list(reversed(order))

    # 初始化：打破零不动点（用户算法要求初始值为 1）
    for p in net.pipes:
        p.supply = 1.0

    prev_flows = [float(p.flow) for p in net.pipes]

    for iteration in range(max_iterations):
        # 正向 pass：沿流向推 supply
        for name in order:
            _forward(net, name)

        # 反向 pass：逆流向拉 capacity
        for name in rev_order:
            _backward(net, name)

        # 收敛判断
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
