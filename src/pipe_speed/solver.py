"""管道网络流速求解器

每轮迭代遍历所有元件，每个元件:
  1. flow = min(Σsupply, max_flow)
  2. push supply: 推 flow 均分到输出管道
  3. pull capacity: 从 max_flow 均抽输入 → 设输入管道 capacity
"""

import math
from fractions import Fraction

from .models import Pipe, Inlet, Outlet, Splitter, Merger, Limiter
from .network import Network

INF = float('inf')
EPS = 1e-12


def _safe_val(value: float) -> float:
    return 0.0 if math.isinf(value) else value


def _safe_cap(value: float) -> float:
    return 1e30 if math.isinf(value) else value


def draw_capacity(max_flow: float, pipes: list[Pipe]) -> None:
    """从 max_flow 出发，均抽各管道的 supply → 设其 capacity"""
    if not pipes:
        return
    for pipe in pipes:
        pipe.capacity = 0.0
    supplies = {id(p): max(p.supply, 0.0) for p in pipes}
    remaining_flow = max_flow if not math.isinf(max_flow) else INF
    active = list(pipes)
    while remaining_flow > EPS and active:
        min_supply = min(supplies[id(p)] for p in active)
        if min_supply <= EPS:
            active = [p for p in active if supplies[id(p)] > EPS]
            continue
        draw = min(min_supply * len(active), remaining_flow)
        remaining_flow -= draw
        per_pipe = draw / len(active)
        for pipe in list(active):
            pipe.capacity += per_pipe
            supplies[id(pipe)] -= per_pipe
            if supplies[id(pipe)] <= EPS:
                active.remove(pipe)


def push_supply(current_flow: float, pipes: list[Pipe]) -> None:
    """推 current_flow 均分到各管道的 capacity → 设其 supply"""
    if not pipes:
        return
    for pipe in pipes:
        pipe.supply = 0.0
    capacities = {id(p): min(_safe_cap(p.capacity), _safe_cap(p.max_flow))
                  for p in pipes}
    remaining_flow = current_flow if not math.isinf(current_flow) else INF
    active = list(pipes)
    while remaining_flow > EPS and active:
        min_cap = min(capacities[id(p)] for p in active)
        if min_cap <= EPS:
            active = [p for p in active if capacities[id(p)] > EPS]
            continue
        push = min(min_cap * len(active), remaining_flow)
        remaining_flow -= push
        per_pipe = push / len(active)
        for pipe in list(active):
            pipe.supply += per_pipe
            capacities[id(pipe)] -= per_pipe
            if capacities[id(pipe)] <= EPS:
                active.remove(pipe)


def solve(network: Network, epsilon: float = 1e-9, max_iterations: int = 1000,
          use_fraction: bool = False) -> int:
    order = list(network.nodes.keys())

    for pipe in network.pipes:
        pipe.supply = pipe.max_flow
        pipe.capacity = pipe.max_flow

    previous_flows = [float(p.flow) for p in network.pipes]

    for iteration in range(max_iterations):
        for name in order:
            component = network.nodes[name]
            inputs = network.in_edges[name]
            outputs = network.out_edges[name]
            max_flow = component.max_flow

            if isinstance(component, Inlet):
                if outputs:
                    flow = max_flow if not math.isinf(max_flow) else INF
                    push_supply(flow, outputs)

            elif isinstance(component, Outlet):
                if inputs:
                    capacity = max_flow if not math.isinf(max_flow) else INF
                    if capacity < INF:
                        for pipe in inputs:
                            pipe.capacity = capacity

            elif isinstance(component, Splitter):
                total_input = sum(_safe_val(p.supply) for p in inputs)
                flow = min(total_input, max_flow if not math.isinf(max_flow) else INF)
                if outputs:
                    push_supply(flow, outputs)
                if inputs:
                    total_output = sum(_safe_val(p.supply) for p in outputs)
                    capacity_limit = total_output if math.isinf(max_flow) else min(total_output, max_flow)
                    draw_capacity(capacity_limit, inputs)

            elif isinstance(component, Merger):
                total_input = sum(_safe_val(p.supply) for p in inputs)
                flow = min(total_input, max_flow if not math.isinf(max_flow) else INF)
                if outputs:
                    downstream_cap = min(_safe_cap(p.capacity) for p in outputs)
                    flow = min(flow, downstream_cap)
                    push_supply(flow, outputs)
                if inputs:
                    draw_capacity(max_flow, inputs)

            elif isinstance(component, Limiter):
                total_input = sum(_safe_val(p.supply) for p in inputs)
                flow = min(total_input, max_flow if not math.isinf(max_flow) else INF)
                if outputs:
                    downstream_cap = min(_safe_cap(p.capacity) for p in outputs)
                    flow = min(flow, downstream_cap)
                    push_supply(flow, outputs)
                if inputs:
                    downstream_cap = min(_safe_cap(p.capacity) for p in outputs) if outputs else INF
                    capacity_limit = max_flow if math.isinf(max_flow) else min(max_flow, downstream_cap)
                    draw_capacity(capacity_limit, inputs)

        max_delta = 0.0
        for i, pipe in enumerate(network.pipes):
            new_flow = float(pipe.flow)
            delta = abs(new_flow - previous_flows[i])
            if delta > max_delta:
                max_delta = delta
            previous_flows[i] = new_flow
        if max_delta < epsilon:
            break

    if use_fraction:
        for pipe in network.pipes:
            pipe.supply = Fraction(float(pipe.supply)).limit_denominator(10**8)
            pipe.capacity = Fraction(float(pipe.capacity)).limit_denominator(10**8)

    return iteration + 1
