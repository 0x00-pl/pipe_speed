"""管道网络流速求解器

每轮迭代遍历所有元件，即时读写管道。
"""

from fractions import Fraction

from .models import Pipe, Inlet, Outlet, Splitter, Merger, Limiter
from .network import Network, topological_order


def draw_capacity(max_flow, pipes: list[Pipe]) -> None:
    if not pipes:
        return
    zero = type(max_flow)(0)
    for pipe in pipes:
        pipe.capacity = zero
    supplies = {id(p): max(p.supply, zero) for p in pipes}
    remaining = max_flow
    active = list(pipes)
    while remaining > zero and active:
        min_supply = min(supplies[id(p)] for p in active)
        draw = min(min_supply * len(active), remaining)
        remaining -= draw
        per_pipe = draw / len(active)
        for pipe in list(active):
            pipe.capacity += per_pipe
            supplies[id(pipe)] -= per_pipe
            if supplies[id(pipe)] <= zero:
                active.remove(pipe)


def push_supply(current_flow, pipes: list[Pipe]) -> None:
    if not pipes:
        return
    zero = type(current_flow)(0)
    for pipe in pipes:
        pipe.supply = zero
    capacities = {id(p): min(p.capacity, p.max_flow) for p in pipes}
    remaining = current_flow
    active = list(pipes)
    while remaining > zero and active:
        min_cap = min(capacities[id(p)] for p in active)
        push = min(min_cap * len(active), remaining)
        remaining -= push
        per_pipe = push / len(active)
        for pipe in list(active):
            pipe.supply += per_pipe
            capacities[id(pipe)] -= per_pipe
            if capacities[id(pipe)] <= zero:
                active.remove(pipe)


def solve(network: Network, epsilon: float = 1e-9, max_iterations: int = 1000,
          use_fraction: bool = False) -> int:
    if use_fraction:
        _to_fraction(network)
        eps = Fraction(1, 10**12)
    else:
        eps = epsilon

    for pipe in network.pipes:
        pipe.supply = pipe.max_flow
        pipe.capacity = pipe.max_flow

    order = topological_order(network)
    rev_order = topological_order(network, reverse=True)

    previous_flows = [pipe.flow for pipe in network.pipes]

    for iteration in range(max_iterations):
        # --- capacity pass: 出→入，均抽设上游 capacity ---
        for name in rev_order:
            component = network.nodes[name]
            inputs = network.in_edges[name]
            outputs = network.out_edges[name]
            max_flow = component.max_flow

            if isinstance(component, Inlet):
                pass
            elif isinstance(component, Outlet):
                for pipe in inputs:
                    pipe.capacity = max_flow
            elif isinstance(component, Splitter):
                if inputs:
                    total_output = sum(p.flow for p in outputs)
                    draw_capacity(min(total_output, max_flow), inputs)
            elif isinstance(component, Merger):
                if inputs:
                    draw_capacity(max_flow, inputs)
            elif isinstance(component, Limiter):
                if inputs:
                    flow = min(p.flow for p in inputs) if inputs else max_flow
                    flow = min(flow, max_flow)
                    if outputs:
                        flow = min(flow, min(p.capacity for p in outputs))
                    draw_capacity(flow, inputs)

        # --- supply pass: 入→出，推流设下游 supply ---
        for name in order:
            component = network.nodes[name]
            inputs = network.in_edges[name]
            outputs = network.out_edges[name]
            max_flow = component.max_flow

            if isinstance(component, Inlet):
                for pipe in outputs:
                    pipe.supply = max_flow
            elif isinstance(component, Outlet):
                pass
            elif isinstance(component, Splitter):
                total_input = sum(p.flow for p in inputs)
                flow = min(total_input, max_flow)
                push_supply(flow, outputs)
            elif isinstance(component, Merger):
                total_input = sum(p.flow for p in inputs)
                flow = min(total_input, max_flow)
                if outputs:
                    flow = min(flow, min(p.capacity for p in outputs))
                push_supply(flow, outputs)
            elif isinstance(component, Limiter):
                total_input = sum(p.flow for p in inputs)
                flow = min(total_input, max_flow)
                if outputs:
                    flow = min(flow, min(p.capacity for p in outputs))
                push_supply(flow, outputs)

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
        _simplify(network)

    return iteration + 1


def _to_fraction(network: Network) -> None:
    for comp in network.nodes.values():
        comp.max_flow = Fraction(comp.max_flow).limit_denominator(10**12)
    for pipe in network.pipes:
        pipe.max_flow = Fraction(pipe.max_flow).limit_denominator(10**12)


def _simplify(network: Network) -> None:
    for pipe in network.pipes:
        pipe.supply = pipe.supply.limit_denominator(10**8)
        pipe.capacity = pipe.capacity.limit_denominator(10**8)
