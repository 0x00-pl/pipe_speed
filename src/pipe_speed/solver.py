"""供需分离迭代求解器

每条管道维护 supply（上游想推）和 capacity（下游能接）两个独立变量。
正向传播按拓扑序设置 supply，反向传播按逆拓扑序设置 capacity。
所有内部集合使用确定性排序，消除迭代不稳定。

对于含环网络：通过流入比例归一化解决多解问题。
"""

import math
from fractions import Fraction
from typing import Union

from .models import Pipe, Inlet, Outlet, Splitter, Merger, Limiter
from .network import Network, topological_order

Num = Union[float, Fraction]


class _NumCtx:
    def __init__(self):
        self.ZERO: float = 0.0
        self.INF: float = float('inf')
        self.EPS: float = 1e-12

    @staticmethod
    def is_inf(val: float) -> bool:
        return math.isinf(val)

    @staticmethod
    def inf_or(val: float, default: float) -> float:
        return default if math.isinf(val) else val


# === 确定性 fair 算法 ===

def fair_distribute(total: float, capacities: list[float]) -> tuple[list[float], float]:
    n = len(capacities)
    if n == 0:
        return [], total
    assigned = [0.0] * n
    remaining = total
    active = list(range(n))
    eps = 1e-12
    while remaining > eps and active:
        per = remaining / len(active)
        capped = sorted(i for i in active
                        if per >= capacities[i] - assigned[i] - eps)
        if capped:
            for i in capped:
                take = capacities[i] - assigned[i]
                assigned[i] = capacities[i]
                remaining -= take
                active.remove(i)
        else:
            for i in active:
                assigned[i] += per
            remaining = 0.0
    return assigned, remaining


def fair_draw(target: float, supplies: list[float]) -> tuple[list[float], float]:
    n = len(supplies)
    if n == 0:
        return [], target
    drawn = [0.0] * n
    needed = target
    active = list(range(n))
    eps = 1e-12
    while needed > eps and active:
        per = needed / len(active)
        exhausted = sorted(i for i in active
                           if per >= supplies[i] - drawn[i] - eps)
        if exhausted:
            for i in exhausted:
                take = supplies[i] - drawn[i]
                drawn[i] = supplies[i]
                needed -= take
                active.remove(i)
        else:
            for i in active:
                drawn[i] += per
            needed = 0.0
    return drawn, needed


# === 无约束传播（所有容量为无穷大）===

def _propagate_unconstrained(net: Network, order: list[str],
                             rev_order: list[str]) -> None:
    """在无约束条件下传播流量，计算各管道的流量比例。

    将入口 supply 设为 1，不设 capacity 限制，让流量自由传播。
    结果中每条管道的 flow 代表该管道流量与总入口流量之比。
    """
    # 初始化：所有 supply=0, capacity=inf
    for p in net.pipes:
        p.supply = 0.0
        p.capacity = float('inf')

    # 找到入口，将第一条出管的 supply 设为 1
    for name in net.nodes:
        comp = net.nodes[name]
        if isinstance(comp, Inlet):
            for p in net.out_edges[name]:
                p.supply = 1.0

    # 迭代直到收敛（无约束下收敛很快）
    for _ in range(200):
        # 正向传播
        for name in order:
            comp = net.nodes[name]
            in_p = net.in_edges[name]
            out_p = net.out_edges[name]

            if isinstance(comp, Inlet):
                for p in out_p:
                    p.supply = 1.0  # 保持入口为 1

            elif isinstance(comp, Splitter):
                incoming = in_p[0].supply
                caps = [p.capacity for p in out_p]
                assigned, _ = fair_distribute(incoming, caps)
                for p, val in zip(out_p, assigned):
                    p.supply = val

            elif isinstance(comp, Merger):
                total = sum(p.supply for p in in_p)
                out_p[0].supply = total

            elif isinstance(comp, Limiter):
                in_p[0].supply = out_p[0].supply = in_p[0].supply
                # 限流器在无约束模式下直通

        # 反向传播：分流器反压
        for name in rev_order:
            comp = net.nodes[name]
            in_p = net.in_edges[name]
            out_p = net.out_edges[name]

            if isinstance(comp, Splitter):
                total_out = sum(p.supply for p in out_p)
                in_p[0].capacity = min(in_p[0].capacity, total_out)

        # 收敛判断
        max_delta = 0.0
        for p in net.pipes:
            f = p.flow
            # 用 supply 变化量判断
            max_delta = max(max_delta, abs(p.supply - getattr(p, '_prev_s', 0.0)))
            p._prev_s = p.supply
        if max_delta < 1e-12:
            break


def _compute_total_inlet(net: Network) -> float:
    """计算总入口流量"""
    total = 0.0
    for name, comp in net.nodes.items():
        if isinstance(comp, Inlet):
            for p in net.out_edges[name]:
                total += p.flow
    return total


# === 约束求解器 ===

def _push_supply(net: Network, order: list[str]) -> None:
    ctx = _NumCtx()
    for name in order:
        comp = net.nodes[name]
        in_p = net.in_edges[name]
        out_p = net.out_edges[name]

        if isinstance(comp, Inlet):
            for p in out_p:
                p.supply = ctx.inf_or(comp.max_flow, ctx.INF)

        elif isinstance(comp, Splitter):
            incoming = in_p[0].supply
            available = min(incoming, comp.max_flow) if not ctx.is_inf(comp.max_flow) else incoming
            caps = [min(ctx.inf_or(p.max_flow, ctx.INF), p.capacity) for p in out_p]
            assigned, _ = fair_distribute(available, caps)
            for p, val in zip(out_p, assigned):
                p.supply = val

        elif isinstance(comp, Merger):
            total_available = sum(p.supply for p in in_p)
            dp = out_p[0]
            downstream_cap = ctx.inf_or(dp.capacity, ctx.INF)
            out_supply = min(total_available, ctx.inf_or(comp.max_flow, total_available))
            out_supply = min(out_supply, downstream_cap)
            dp.supply = out_supply

        elif isinstance(comp, Limiter):
            incoming = in_p[0].supply
            dp = out_p[0]
            downstream_cap = ctx.inf_or(dp.capacity, ctx.INF)
            outgoing = incoming
            if not ctx.is_inf(comp.max_flow):
                outgoing = min(outgoing, comp.max_flow)
            outgoing = min(outgoing, downstream_cap)
            dp.supply = outgoing


def _pull_capacity(net: Network, rev_order: list[str]) -> None:
    ctx = _NumCtx()
    for name in rev_order:
        comp = net.nodes[name]
        in_p = net.in_edges[name]
        out_p = net.out_edges[name]

        if isinstance(comp, Outlet):
            for p in in_p:
                p.capacity = ctx.inf_or(comp.max_flow, ctx.INF)

        elif isinstance(comp, Splitter):
            total_out = sum(p.supply for p in out_p)
            cap = total_out
            if not ctx.is_inf(comp.max_flow):
                cap = min(cap, comp.max_flow)
            in_p[0].capacity = min(ctx.inf_or(in_p[0].capacity, ctx.INF), cap)

        elif isinstance(comp, Merger):
            downstream_cap = ctx.inf_or(out_p[0].capacity, ctx.INF)
            total_cap = downstream_cap
            if not ctx.is_inf(comp.max_flow):
                total_cap = min(total_cap, comp.max_flow)
            supplies = [p.supply for p in in_p]
            total_supply = sum(supplies)
            if not ctx.is_inf(total_cap) and total_cap < total_supply - ctx.EPS:
                drawn, _ = fair_draw(total_cap, supplies)
                for p, val in zip(in_p, drawn):
                    p.capacity = min(ctx.inf_or(p.capacity, ctx.INF), val)
            else:
                # 非瓶颈：慷慨容量（允许分流器溢出）
                for p in in_p:
                    p.capacity = min(ctx.inf_or(p.capacity, ctx.INF), total_cap)

        elif isinstance(comp, Limiter):
            outgoing_cap = ctx.inf_or(out_p[0].capacity, ctx.INF)
            incoming_cap = outgoing_cap
            if not ctx.is_inf(comp.max_flow):
                incoming_cap = min(incoming_cap, comp.max_flow)
            in_p[0].capacity = min(ctx.inf_or(in_p[0].capacity, ctx.INF), incoming_cap)


def solve(net: Network, epsilon: float = 1e-9, max_iterations: int = 1000,
          use_fraction: bool = False) -> int:
    order = topological_order(net)
    rev_order = list(reversed(order))

    prev_flows = [float(p.flow) for p in net.pipes]

    # 阶段 1：无约束传播求流量比例
    _propagate_unconstrained(net, order, rev_order)

    # 阶段 2：根据比例和总入口流量，按入口约束缩放
    total_inlet = _compute_total_inlet(net)
    scale = 1.0
    if total_inlet > 0:
        # 计算入口能提供的最大总流量
        max_total = 0.0
        for name, comp in net.nodes.items():
            if isinstance(comp, Inlet):
                max_total += comp.max_flow if not math.isinf(comp.max_flow) else float('inf')
        if not math.isinf(max_total) and total_inlet > max_total:
            scale = max_total / total_inlet

    # 按比例缩放所有管道流量
    for p in net.pipes:
        p.supply *= scale
        p.capacity = float('inf')  # 重置
    # 重新设置入口 supply
    for name, comp in net.nodes.items():
        if isinstance(comp, Inlet):
            for p in net.out_edges[name]:
                p.supply = min(comp.max_flow, p.supply) if not math.isinf(comp.max_flow) else p.supply

    # 阶段 3：有约束迭代（处理硬容量限制）
    for iteration in range(max_iterations):
        _push_supply(net, order)
        _pull_capacity(net, rev_order)

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
        _floats_to_fractions(net)

    return iteration + 1


def _floats_to_fractions(net: Network) -> None:
    for pipe in net.pipes:
        pipe.supply = Fraction(float(pipe.supply)).limit_denominator(10**8)
        pipe.capacity = Fraction(float(pipe.capacity)).limit_denominator(10**8)
