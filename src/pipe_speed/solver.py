"""供需分离迭代求解器

核心思想：每条管道维护两个独立变量 —— supply（上游想推的量）和 capacity（下游能接的量）。
两者互不覆盖，flow = min(supply, capacity)。正向传播设置 supply，反向传播设置 capacity。
"""

import math

from .models import Pipe, Inlet, Outlet, Splitter, Merger, Limiter
from .network import Network, topological_order


def fair_distribute(total: float, capacities: list[float]) -> tuple[list[float], float]:
    """将 total 均分到 N 个输出，受各自 capacity 约束。

    优先均分；若某路超出 capacity，截断并将超出量在其他路中再均分。
    若全部满容，剩余流量返回（触发反压）。

    Args:
        total: 待分配的总流量
        capacities: 各输出口的容量上限列表

    Returns:
        (assigned, remaining): 分配结果列表 和 未分配的剩余量
    """
    n = len(capacities)
    if n == 0:
        return [], total

    assigned = [0.0] * n
    remaining = total
    active = set(range(n))

    while remaining > 1e-12 and active:
        per_output = remaining / len(active)

        # 找出本轮会超容的输出口
        capped = set()
        for i in active:
            if per_output >= capacities[i] - assigned[i] - 1e-12:
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
            remaining = 0.0

    return assigned, remaining


def fair_draw(target: float, supplies: list[float]) -> tuple[list[float], float]:
    """从 N 个输入中均抽 target 流量，受各自 supply 约束。

    优先均抽；若某路 supply 不足，抽光并将缺口在其他路中再均抽。
    若全部抽空，返回缺口（触发降流量）。

    Args:
        target: 期望抽取的总流量
        supplies: 各输入口的可用供应量列表

    Returns:
        (drawn, shortfall): 抽取结果列表 和 未能满足的缺口
    """
    n = len(supplies)
    if n == 0:
        return [], target

    drawn = [0.0] * n
    needed = target
    active = set(range(n))

    while needed > 1e-12 and active:
        per_input = needed / len(active)

        # 找出本轮会被抽空的输入口
        exhausted = set()
        for i in active:
            if per_input >= supplies[i] - drawn[i] - 1e-12:
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
            needed = 0.0

    return drawn, needed


def _inf_or(val: float, default: float) -> float:
    """若 val 为无穷大，返回 default；否则返回 val"""
    if math.isinf(val):
        return default
    return val


def push_supply(net: Network, order: list[str]) -> None:
    """正向传播：按拓扑序，设置下游管道的 supply"""
    for name in order:
        comp = net.nodes[name]
        in_pipes = net.in_edges[name]
        out_pipes = net.out_edges[name]

        if isinstance(comp, Inlet):
            # 入口始终尝试推最大值
            for pipe in out_pipes:
                pipe.supply = _inf_or(comp.max_flow, float('inf'))

        elif isinstance(comp, Outlet):
            # 出口无下游管道，无操作
            pass

        elif isinstance(comp, Splitter):
            # 读取来流
            incoming = in_pipes[0].supply
            if math.isinf(comp.max_flow):
                available = incoming
            else:
                available = min(incoming, comp.max_flow)

            # 各输出口的容量 = min(管道自身上限, 下游接受能力)
            caps = [
                min(_inf_or(p.max_flow, float('inf')),
                    _inf_or(p.capacity, float('inf')))
                for p in out_pipes
            ]

            assigned, _ = fair_distribute(available, caps)

            for pipe, val in zip(out_pipes, assigned):
                pipe.supply = val

        elif isinstance(comp, Merger):
            # 求和所有入管的 supply
            total_available = sum(p.supply for p in in_pipes)

            downstream_pipe = out_pipes[0]
            downstream_cap = _inf_or(downstream_pipe.capacity, float('inf'))

            output_supply = total_available
            if not math.isinf(comp.max_flow):
                output_supply = min(output_supply, comp.max_flow)
            output_supply = min(output_supply, downstream_cap)

            downstream_pipe.supply = output_supply

        elif isinstance(comp, Limiter):
            incoming = in_pipes[0].supply
            downstream_pipe = out_pipes[0]
            downstream_cap = _inf_or(downstream_pipe.capacity, float('inf'))

            outgoing = incoming
            if not math.isinf(comp.max_flow):
                outgoing = min(outgoing, comp.max_flow)
            outgoing = min(outgoing, downstream_cap)

            downstream_pipe.supply = outgoing


def pull_capacity(net: Network, rev_order: list[str]) -> None:
    """反向传播：按逆拓扑序，设置上游管道的 capacity"""
    for name in rev_order:
        comp = net.nodes[name]
        in_pipes = net.in_edges[name]
        out_pipes = net.out_edges[name]

        if isinstance(comp, Inlet):
            # 无上游管道，无操作
            pass

        elif isinstance(comp, Outlet):
            # 出口始终尝试拉最大值
            for pipe in in_pipes:
                pipe.capacity = _inf_or(comp.max_flow, float('inf'))

        elif isinstance(comp, Splitter):
            # 用实际分配量（supply），而非下游 capacity：
            # 下游管道的 capacity 可能是 inf（被 outlet 设为无穷大），
            # 但分流器实际能分配的量受各管道 max_flow 和下游元件接受能力约束。
            # 使用当前轮 push_supply 分配的各出管 supply 之和，
            # 反映分流器在当前约束下实际能输出的总量。
            total_out_supply = sum(p.supply for p in out_pipes)
            cap = total_out_supply
            if not math.isinf(comp.max_flow):
                cap = min(cap, comp.max_flow)
            in_pipes[0].capacity = min(
                _inf_or(in_pipes[0].capacity, float('inf')), cap
            )

        elif isinstance(comp, Merger):
            downstream_cap = _inf_or(out_pipes[0].capacity, float('inf'))
            total_cap = downstream_cap
            if not math.isinf(comp.max_flow):
                total_cap = min(total_cap, comp.max_flow)

            supplies = [p.supply for p in in_pipes]
            total_supply = sum(supplies)

            # 瓶颈判断：汇流器的总输出能力是否构成瓶颈
            if math.isinf(total_cap) or total_cap >= total_supply - 1e-12:
                # 不瓶颈：设置慷慨的 capacity，允许上游分流器溢出
                for pipe in in_pipes:
                    pipe.capacity = min(
                        _inf_or(pipe.capacity, float('inf')), total_cap
                    )
            else:
                # 瓶颈：用 fair_draw 均分有限的输出能力
                drawn, _ = fair_draw(total_cap, supplies)
                for pipe, val in zip(in_pipes, drawn):
                    pipe.capacity = min(
                        _inf_or(pipe.capacity, float('inf')), val
                    )

        elif isinstance(comp, Limiter):
            outgoing_cap = _inf_or(out_pipes[0].capacity, float('inf'))
            incoming_cap = outgoing_cap
            if not math.isinf(comp.max_flow):
                incoming_cap = min(incoming_cap, comp.max_flow)
            in_pipes[0].capacity = min(
                _inf_or(in_pipes[0].capacity, float('inf')), incoming_cap
            )


def solve(net: Network, epsilon: float = 1e-9, max_iterations: int = 1000) -> int:
    """求解管道网络的稳态流速

    Args:
        net: 已构建的网络
        epsilon: 收敛阈值
        max_iterations: 最大迭代次数

    Returns:
        实际迭代次数
    """
    order = topological_order(net)
    rev_order = list(reversed(order))

    # 初始化：所有管道 supply=0, capacity=inf（dataclass 默认值）

    # 记录上一轮的 flow 用于收敛判断
    prev_flows = [0.0] * len(net.pipes)

    for iteration in range(max_iterations):
        # 正向传播
        push_supply(net, order)

        # 反向传播
        pull_capacity(net, rev_order)

        # 收敛判断
        max_delta = 0.0
        for i, pipe in enumerate(net.pipes):
            new_flow = pipe.flow
            delta = abs(new_flow - prev_flows[i])
            if delta > max_delta:
                max_delta = delta
            prev_flows[i] = new_flow

        if max_delta < epsilon:
            return iteration + 1

    # 达到最大迭代次数但未收敛，仍返回结果
    return max_iterations
