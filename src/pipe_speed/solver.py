"""管道网络流速求解器

每轮迭代遍历所有元件，每个元件:
  1. flow = min(Σsupply, max_flow)
  2. push supply: 推 flow 均分到输出管道
  3. pull capacity: 从 max_flow 均抽输入 → 设输入管道 capacity

--fraction 时全程使用 Fraction 精确有理数运算。
"""

from fractions import Fraction

from .models import Pipe, Inlet, Outlet, Splitter, Merger, Limiter
from .network import Network


def draw_capacity(max_flow, pipes: list[Pipe]) -> None:
    """从 max_flow 出发，均抽各管道的 supply → 设其 capacity"""
    if not pipes:
        return
    zero = type(max_flow)(0)
    for pipe in pipes:
        pipe.capacity = zero
    supplies = {id(p): max(p.supply, zero) for p in pipes}
    remaining_flow = max_flow
    active = list(pipes)
    while remaining_flow > zero and active:
        min_supply = min(supplies[id(p)] for p in active)
        draw = min(min_supply * len(active), remaining_flow)
        remaining_flow -= draw
        per_pipe = draw / len(active)
        for pipe in list(active):
            pipe.capacity += per_pipe
            supplies[id(pipe)] -= per_pipe
            if supplies[id(pipe)] <= zero:
                active.remove(pipe)


def push_supply(current_flow, pipes: list[Pipe]) -> None:
    """推 current_flow 均分到各管道的 capacity → 设其 supply"""
    if not pipes:
        return
    zero = type(current_flow)(0)
    for pipe in pipes:
        pipe.supply = zero
    capacities = {id(p): min(p.capacity, p.max_flow) for p in pipes}
    remaining_flow = current_flow
    active = list(pipes)
    while remaining_flow > zero and active:
        min_cap = min(capacities[id(p)] for p in active)
        push = min(min_cap * len(active), remaining_flow)
        remaining_flow -= push
        per_pipe = push / len(active)
        for pipe in list(active):
            pipe.supply += per_pipe
            capacities[id(pipe)] -= per_pipe
            if capacities[id(pipe)] <= zero:
                active.remove(pipe)


def solve(network: Network, epsilon: float = 1e-9, max_iterations: int = 1000,
          use_fraction: bool = False) -> int:
    order = list(network.nodes.keys())

    if use_fraction:
        _convert_to_fraction(network)
        eps = Fraction(1, 10**12)
    else:
        eps = epsilon

    for pipe in network.pipes:
        pipe.supply = pipe.max_flow
        pipe.capacity = pipe.max_flow

    previous_flows = [pipe.flow for pipe in network.pipes]

    for iteration in range(max_iterations):
        for name in order:
            component = network.nodes[name]
            inputs = network.in_edges[name]
            outputs = network.out_edges[name]
            max_flow = component.max_flow

            if isinstance(component, Inlet):
                if outputs:
                    for pipe in outputs:
                        pipe.supply = max_flow

            elif isinstance(component, Outlet):
                if inputs:
                    for pipe in inputs:
                        pipe.capacity = max_flow

            elif isinstance(component, Splitter):
                total_input = sum(p.supply for p in inputs)
                flow = min(total_input, max_flow)
                if outputs:
                    push_supply(flow, outputs)
                if inputs:
                    total_output = sum(p.supply for p in outputs)
                    draw_capacity(min(total_output, max_flow), inputs)

            elif isinstance(component, Merger):
                total_input = sum(p.supply for p in inputs)
                flow = min(total_input, max_flow)
                if outputs:
                    push_supply(flow, outputs)
                if inputs:
                    draw_capacity(max_flow, inputs)

            elif isinstance(component, Limiter):
                total_input = sum(p.supply for p in inputs)
                flow = min(total_input, max_flow)
                if outputs:
                    push_supply(flow, outputs)
                if inputs:
                    draw_capacity(flow, inputs)

        max_delta = type(previous_flows[0])(0)
        for i, pipe in enumerate(network.pipes):
            new_flow = pipe.flow
            delta = abs(new_flow - previous_flows[i])
            if delta > max_delta:
                max_delta = delta
            previous_flows[i] = new_flow
        if max_delta < eps:
            break

    if use_fraction:
        _simplify_fractions(network)

    return iteration + 1


def _convert_to_fraction(network: Network) -> None:
    """将网络中所有数值转为 Fraction"""
    for comp in network.nodes.values():
        comp.max_flow = Fraction(comp.max_flow).limit_denominator(10**12)
    for pipe in network.pipes:
        pipe.max_flow = Fraction(pipe.max_flow).limit_denominator(10**12)
        pipe.supply = Fraction(pipe.supply).limit_denominator(10**12)
        pipe.capacity = Fraction(pipe.capacity).limit_denominator(10**12)


def _simplify_fractions(network: Network) -> None:
    """将求解后的大分母 Fraction 约简到合理精度"""
    for pipe in network.pipes:
        pipe.supply = pipe.supply.limit_denominator(10**8)
        pipe.capacity = pipe.capacity.limit_denominator(10**8)
