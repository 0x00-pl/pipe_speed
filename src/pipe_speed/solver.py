"""供需分离迭代求解器

核心思想：每条管道维护两个独立变量 —— supply（上游想推的量）和 capacity（下游能接的量）。
两者互不覆盖，flow = min(supply, capacity)。正向传播设置 supply，反向传播设置 capacity。

支持两种数值类型：
- float（默认）：浮点运算
- Fraction（--fraction 模式）：精确有理数运算
"""

import math
from fractions import Fraction
from typing import Union

from .models import Pipe, Inlet, Outlet, Splitter, Merger, Limiter
from .network import Network, topological_order

# 数值类型
Num = Union[float, Fraction]


class _NumCtx:
    """数值上下文：提供零、无穷、精度等类型相关的常量和方法"""

    def __init__(self, use_fraction: bool):
        self.use_fraction = use_fraction
        if use_fraction:
            self.ZERO: Num = Fraction(0, 1)
            self.INF: Num = Fraction(10**20, 1)  # 足够大的"无穷"
            self.EPS: Num = Fraction(1, 10**12)
        else:
            self.ZERO: Num = 0.0
            self.INF: Num = float('inf')
            self.EPS: Num = 1e-12

    def is_inf(self, val: Num) -> bool:
        if self.use_fraction:
            return val >= self.INF / 2
        return math.isinf(float(val))

    def inf_or(self, val: Num, default: Num) -> Num:
        return default if self.is_inf(val) else val


def fair_distribute(total: Num, capacities: list[Num],
                    ctx: _NumCtx) -> tuple[list[Num], Num]:
    """将 total 均分到 N 个输出，受各自 capacity 约束。"""
    n = len(capacities)
    if n == 0:
        return [], total

    assigned = [ctx.ZERO] * n
    remaining = total
    active = set(range(n))

    while remaining > ctx.EPS and active:
        per_output = remaining / len(active)
        capped = set()
        for i in active:
            if per_output >= capacities[i] - assigned[i] - ctx.EPS:
                capped.add(i)
        if capped:
            for i in capped:
                take = capacities[i] - assigned[i]
                assigned[i] = capacities[i]
                remaining -= take
                active.remove(i)
        else:
            for i in active:
                assigned[i] += per_output
            remaining = ctx.ZERO

    return assigned, remaining


def fair_draw(target: Num, supplies: list[Num],
              ctx: _NumCtx) -> tuple[list[Num], Num]:
    """从 N 个输入中均抽 target 流量，受各自 supply 约束。"""
    n = len(supplies)
    if n == 0:
        return [], target

    drawn = [ctx.ZERO] * n
    needed = target
    active = set(range(n))

    while needed > ctx.EPS and active:
        per_input = needed / len(active)
        exhausted = set()
        for i in active:
            if per_input >= supplies[i] - drawn[i] - ctx.EPS:
                exhausted.add(i)
        if exhausted:
            for i in exhausted:
                take = supplies[i] - drawn[i]
                drawn[i] = supplies[i]
                needed -= take
                active.remove(i)
        else:
            for i in active:
                drawn[i] += per_input
            needed = ctx.ZERO

    return drawn, needed


def _push_supply(net: Network, order: list[str], ctx: _NumCtx) -> None:
    """正向传播"""
    for name in order:
        comp = net.nodes[name]
        in_pipes = net.in_edges[name]
        out_pipes = net.out_edges[name]

        if isinstance(comp, Inlet):
            for pipe in out_pipes:
                pipe.supply = ctx.inf_or(comp.max_flow, ctx.INF)

        elif isinstance(comp, Outlet):
            pass

        elif isinstance(comp, Splitter):
            incoming = in_pipes[0].supply
            if ctx.is_inf(comp.max_flow):
                available = incoming
            else:
                available = min(incoming, comp.max_flow)

            caps = [
                min(ctx.inf_or(p.max_flow, ctx.INF),
                    ctx.inf_or(p.capacity, ctx.INF))
                for p in out_pipes
            ]
            assigned, _ = fair_distribute(available, caps, ctx)
            for pipe, val in zip(out_pipes, assigned):
                pipe.supply = val

        elif isinstance(comp, Merger):
            total_available = sum(p.supply for p in in_pipes)
            downstream_pipe = out_pipes[0]
            downstream_cap = ctx.inf_or(downstream_pipe.capacity, ctx.INF)
            output_supply = total_available
            if not ctx.is_inf(comp.max_flow):
                output_supply = min(output_supply, comp.max_flow)
            output_supply = min(output_supply, downstream_cap)
            downstream_pipe.supply = output_supply

        elif isinstance(comp, Limiter):
            incoming = in_pipes[0].supply
            downstream_pipe = out_pipes[0]
            downstream_cap = ctx.inf_or(downstream_pipe.capacity, ctx.INF)
            outgoing = incoming
            if not ctx.is_inf(comp.max_flow):
                outgoing = min(outgoing, comp.max_flow)
            outgoing = min(outgoing, downstream_cap)
            downstream_pipe.supply = outgoing


def _pull_capacity(net: Network, rev_order: list[str], ctx: _NumCtx) -> None:
    """反向传播"""
    for name in rev_order:
        comp = net.nodes[name]
        in_pipes = net.in_edges[name]
        out_pipes = net.out_edges[name]

        if isinstance(comp, Inlet):
            pass

        elif isinstance(comp, Outlet):
            for pipe in in_pipes:
                pipe.capacity = ctx.inf_or(comp.max_flow, ctx.INF)

        elif isinstance(comp, Splitter):
            total_out_supply = sum(p.supply for p in out_pipes)
            cap = total_out_supply
            if not ctx.is_inf(comp.max_flow):
                cap = min(cap, comp.max_flow)
            in_pipes[0].capacity = min(
                ctx.inf_or(in_pipes[0].capacity, ctx.INF), cap
            )

        elif isinstance(comp, Merger):
            downstream_cap = ctx.inf_or(out_pipes[0].capacity, ctx.INF)
            total_cap = downstream_cap
            if not ctx.is_inf(comp.max_flow):
                total_cap = min(total_cap, comp.max_flow)

            supplies = [p.supply for p in in_pipes]
            total_supply = sum(supplies)

            if ctx.is_inf(total_cap) or total_cap >= total_supply - ctx.EPS:
                for pipe in in_pipes:
                    pipe.capacity = min(
                        ctx.inf_or(pipe.capacity, ctx.INF), total_cap
                    )
            else:
                drawn, _ = fair_draw(total_cap, supplies, ctx)
                for pipe, val in zip(in_pipes, drawn):
                    pipe.capacity = min(
                        ctx.inf_or(pipe.capacity, ctx.INF), val
                    )

        elif isinstance(comp, Limiter):
            outgoing_cap = ctx.inf_or(out_pipes[0].capacity, ctx.INF)
            incoming_cap = outgoing_cap
            if not ctx.is_inf(comp.max_flow):
                incoming_cap = min(incoming_cap, comp.max_flow)
            in_pipes[0].capacity = min(
                ctx.inf_or(in_pipes[0].capacity, ctx.INF), incoming_cap
            )


def solve(net: Network, epsilon: float = 1e-9, max_iterations: int = 1000,
          use_fraction: bool = False) -> int:
    """求解管道网络的稳态流速

    Args:
        net: 已构建的网络
        epsilon: 收敛阈值
        max_iterations: 最大迭代次数
        use_fraction: True 时求解后将结果转为 Fraction 精确分数

    Returns:
        实际迭代次数
    """
    ctx = _NumCtx(use_fraction=False)  # 始终用 float 求解

    order = topological_order(net)
    rev_order = list(reversed(order))

    prev_flows = [float(p.flow) for p in net.pipes]

    for iteration in range(max_iterations):
        _push_supply(net, order, ctx)
        _pull_capacity(net, rev_order, ctx)

        max_delta = 0.0
        for i, pipe in enumerate(net.pipes):
            new_flow = float(pipe.flow)
            delta = abs(new_flow - prev_flows[i])
            if delta > max_delta:
                max_delta = delta
            prev_flows[i] = new_flow

        if max_delta < epsilon:
            break

    # Fraction 模式：将 float 结果转为精确分数
    if use_fraction:
        _floats_to_fractions(net)

    return iteration + 1


def _floats_to_fractions(net: Network) -> None:
    """将求解后的 float 结果转为精确 Fraction（使用 limit_denominator）"""
    for name, comp in net.nodes.items():
        mf = comp.max_flow
        if not isinstance(mf, Fraction) and mf != float('inf'):
            comp.max_flow = Fraction(mf).limit_denominator(10**8)

    for pipe in net.pipes:
        # 流速：float → Fraction
        pipe.supply = Fraction(float(pipe.supply)).limit_denominator(10**8)
        pipe.capacity = Fraction(float(pipe.capacity)).limit_denominator(10**8)
        if pipe.max_flow != float('inf') and not isinstance(pipe.max_flow, Fraction):
            pipe.max_flow = Fraction(pipe.max_flow).limit_denominator(10**8)
