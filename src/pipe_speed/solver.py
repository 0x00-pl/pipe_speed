"""管道网络流速求解器

每轮迭代: capacity pass(逆拓扑) → supply pass(正拓扑)。
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


def validate(network: Network) -> list[str]:
    """验证网络的守恒性和分配逻辑，返回问题列表"""
    issues = []
    tolerance = 1e-6

    for name, component in network.nodes.items():
        inputs = network.in_edges[name]
        outputs = network.out_edges[name]
        total_in = sum(p.flow for p in inputs)
        total_out = sum(p.flow for p in outputs)

        if isinstance(component, Inlet):
            if total_in != 0:
                issues.append(f"[{name}] 入口入流应为0，实际 {total_in:.4f}")
            if outputs and total_out < eps:
                issues.append(f"[{name}] 入口无输出")

        elif isinstance(component, Outlet):
            if total_out != 0:
                issues.append(f"[{name}] 出口出流应为0，实际 {total_out:.4f}")
            if inputs and total_in < eps:
                issues.append(f"[{name}] 出口无输入")
            # 出口应设慷慨容量
            for pipe in inputs:
                if abs(pipe.capacity - component.max_flow) > tolerance:
                    issues.append(f"[{name}] 出口应设 capacity={component.max_flow}，实际 {pipe.capacity:.4f}")

        elif isinstance(component, Splitter):
            if abs(total_in - total_out) > tolerance:
                issues.append(f"[{name}] 分流器不守恒: in={total_in:.4f} out={total_out:.4f}")
            if inputs and len(inputs) != 1:
                issues.append(f"[{name}] 分流器应有1入，实际 {len(inputs)}")
            if outputs and len(outputs) > 3:
                issues.append(f"[{name}] 分流器最多3出，实际 {len(outputs)}")
            # 输入容量应 = sum(输出流)
            if inputs and outputs:
                expected_cap = min(sum(p.flow for p in outputs), component.max_flow)
                draw_capacity(expected_cap, inputs)
                actual_cap = inputs[0].capacity
                if abs(actual_cap - expected_cap) > tolerance:
                    issues.append(f"[{name}] 入管容量 {actual_cap:.4f} ≠ Σ出流 {expected_cap:.4f}")

        elif isinstance(component, Merger):
            if abs(total_in - total_out) > tolerance:
                issues.append(f"[{name}] 汇流器不守恒: in={total_in:.4f} out={total_out:.4f}")
            if outputs and len(outputs) != 1:
                issues.append(f"[{name}] 汇流器应有1出，实际 {len(outputs)}")
            if inputs and len(inputs) > 3:
                issues.append(f"[{name}] 汇流器最多3入，实际 {len(inputs)}")
            # 入管容量应均等或受限
            if inputs and len(inputs) >= 2:
                caps = [p.capacity for p in inputs]
                max_cap = max(caps)
                min_cap = min(caps)
                if max_cap - min_cap > tolerance:
                    # 允许不均等(供给不足)，但不超出 max_flow/N
                    fair = component.max_flow / len(inputs)
                    for i, pipe in enumerate(inputs):
                        if pipe.capacity > fair + eps:
                            issues.append(f"[{name}] 入{i}容量 {pipe.capacity:.4f} > 公平份额 {fair:.4f}")

        elif isinstance(component, Limiter):
            if abs(total_in - total_out) > tolerance:
                issues.append(f"[{name}] 限流器不守恒: in={total_in:.4f} out={total_out:.4f}")
            if inputs and len(inputs) != 1:
                issues.append(f"[{name}] 限流器应有1入，实际 {len(inputs)}")
            if outputs and len(outputs) != 1:
                issues.append(f"[{name}] 限流器应有1出，实际 {len(outputs)}")
            # 流量不应超过 max_flow
            if total_in > component.max_flow + tolerance:
                issues.append(f"[{name}] 限流器流量 {total_in:.4f} > max_flow {component.max_flow}")

    return issues


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
        # --- capacity pass: 出→入 ---
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
                    downstream_cap = min(p.capacity for p in outputs) if outputs else max_flow
                    draw_capacity(min(max_flow, downstream_cap), inputs)
            elif isinstance(component, Limiter):
                if inputs:
                    flow = min(p.flow for p in inputs) if inputs else max_flow
                    flow = min(flow, max_flow)
                    if outputs:
                        flow = min(flow, min(p.capacity for p in outputs))
                    draw_capacity(flow, inputs)

        # --- supply pass: 入→出 ---
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
        component.max_flow = Fraction(component.max_flow).limit_denominator(10**12)
    for pipe in network.pipes:
        pipe.max_flow = Fraction(pipe.max_flow).limit_denominator(10**12)


def _simplify(network: Network) -> None:
    for pipe in network.pipes:
        pipe.supply = pipe.supply.limit_denominator(10**8)
        pipe.capacity = pipe.capacity.limit_denominator(10**8)
