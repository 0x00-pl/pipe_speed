"""管道网络流速求解器 (Jacobi 风格)

每轮迭代：快照所有管道 → 所有元件基于快照独立计算 → 统一写入。
"""

from fractions import Fraction

from .models import Pipe, Inlet, Outlet, Splitter, Merger, Limiter
from .network import Network

_pid = id


def draw_capacity(max_flow, snap_supply: dict, snap_capacity: dict,
                  pipes: list[Pipe], write_capacity: dict) -> None:
    if not pipes:
        return
    zero = type(max_flow)(0)
    for pipe in pipes:
        write_capacity[_pid(pipe)] = zero
    supplies = {_pid(p): max(snap_supply.get(_pid(p), p.supply), zero)
                for p in pipes}
    remaining_flow = max_flow
    active = list(pipes)
    while remaining_flow > zero and active:
        min_supply = min(supplies[_pid(p)] for p in active)
        draw = min(min_supply * len(active), remaining_flow)
        remaining_flow -= draw
        per_pipe = draw / len(active)
        for pipe in list(active):
            write_capacity[_pid(pipe)] += per_pipe
            supplies[_pid(pipe)] -= per_pipe
            if supplies[_pid(pipe)] <= zero:
                active.remove(pipe)


def push_supply(current_flow, snap_capacity: dict,
                pipes: list[Pipe], write_supply: dict) -> None:
    if not pipes:
        return
    zero = type(current_flow)(0)
    for pipe in pipes:
        write_supply[_pid(pipe)] = zero
    capacities = {_pid(p): min(
        snap_capacity.get(_pid(p), p.capacity), p.max_flow)
        for p in pipes}
    remaining_flow = current_flow
    active = list(pipes)
    while remaining_flow > zero and active:
        min_cap = min(capacities[_pid(p)] for p in active)
        push = min(min_cap * len(active), remaining_flow)
        remaining_flow -= push
        per_pipe = push / len(active)
        for pipe in list(active):
            write_supply[_pid(pipe)] += per_pipe
            capacities[_pid(pipe)] -= per_pipe
            if capacities[_pid(pipe)] <= zero:
                active.remove(pipe)


def solve(network: Network, epsilon: float = 1e-9, max_iterations: int = 1000,
          use_fraction: bool = False) -> int:
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
        # snapshot
        snap_supply = {_pid(p): p.supply for p in network.pipes}
        snap_capacity = {_pid(p): p.capacity for p in network.pipes}
        new_supply = {}
        new_capacity = {}

        for name in network.nodes:
            component = network.nodes[name]
            inputs = network.in_edges[name]
            outputs = network.out_edges[name]
            max_flow = component.max_flow

            # read supply from snapshot
            total_input = sum(snap_supply.get(_pid(p), p.supply) for p in inputs)
            flow = min(total_input, max_flow)

            if isinstance(component, Inlet):
                flow = max_flow
                if outputs:
                    for pipe in outputs:
                        new_supply[_pid(pipe)] = flow

            elif isinstance(component, Outlet):
                if inputs:
                    for pipe in inputs:
                        new_capacity[_pid(pipe)] = max_flow

            elif isinstance(component, Splitter):
                if outputs:
                    push_supply(flow, snap_capacity, outputs, new_supply)
                if inputs:
                    total_output = sum(
                        new_supply.get(_pid(p),
                                       snap_supply.get(_pid(p), p.supply))
                        for p in outputs
                    )
                    draw_capacity(min(total_output, max_flow),
                                  snap_supply, snap_capacity,
                                  inputs, new_capacity)

            elif isinstance(component, Merger):
                if outputs:
                    downstream_cap = min(snap_capacity.get(_pid(p), p.capacity)
                                         for p in outputs)
                    flow = min(flow, downstream_cap)
                    push_supply(flow, snap_capacity, outputs, new_supply)
                if inputs:
                    draw_capacity(flow,
                                  snap_supply, snap_capacity,
                                  inputs, new_capacity)

            elif isinstance(component, Limiter):
                if outputs:
                    downstream_cap = min(snap_capacity.get(_pid(p), p.capacity)
                                         for p in outputs)
                    flow = min(flow, downstream_cap)
                    push_supply(flow, snap_capacity, outputs, new_supply)
                if inputs:
                    draw_capacity(flow,
                                  snap_supply, snap_capacity,
                                  inputs, new_capacity)

        # apply writes
        for pipe in network.pipes:
            pid = _pid(pipe)
            if pid in new_supply:
                pipe.supply = new_supply[pid]
            if pid in new_capacity:
                pipe.capacity = new_capacity[pid]

        # convergence
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
    for comp in network.nodes.values():
        comp.max_flow = Fraction(comp.max_flow).limit_denominator(10**12)
    for pipe in network.pipes:
        pipe.max_flow = Fraction(pipe.max_flow).limit_denominator(10**12)


def _simplify_fractions(network: Network) -> None:
    for pipe in network.pipes:
        pipe.supply = pipe.supply.limit_denominator(10**8)
        pipe.capacity = pipe.capacity.limit_denominator(10**8)
