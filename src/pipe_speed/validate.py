"""网络验证：守恒性 + 分配逻辑"""

from .models import Inlet, Outlet, Splitter, Merger, Limiter
from .network import Network


def _fair_allocate(total, limits: list) -> list:
    """均分 total 到 N 路，受 limits 约束。耗尽时重分配给剩余路。"""
    if not limits:
        return []
    zero = type(total)(0)
    allocated = [zero] * len(limits)
    remaining_limits = [max(limit, zero) for limit in limits]
    remaining_total = total
    active = list(range(len(limits)))
    while remaining_total > zero and active:
        min_limit = min(remaining_limits[i] for i in active)
        batch = min(min_limit * len(active), remaining_total)
        remaining_total -= batch
        per_item = batch / len(active)
        for i in list(active):
            allocated[i] += per_item
            remaining_limits[i] -= per_item
            if remaining_limits[i] <= zero:
                active.remove(i)
    return allocated


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
            assert total_in == 0, f"[{name}] 入口入流应为0，实际 {total_in:.4f}"
            if outputs and total_out < tolerance:
                issues.append(f"[{name}] 入口无输出")

        elif isinstance(component, Outlet):
            if inputs and total_in < tolerance:
                issues.append(f"[{name}] 出口无输入")
            for pipe in inputs:
                if abs(pipe.capacity - component.max_flow) > tolerance:
                    issues.append(f"[{name}] 出口应设 capacity={component.max_flow}，实际 {pipe.capacity:.4f}")

        elif isinstance(component, Splitter):
            if abs(total_in - total_out) > tolerance:
                issues.append(f"[{name}] 分流器不守恒: in={total_in:.4f} out={total_out:.4f}")
            if outputs and total_in > 0:
                limits = [p.max_flow if p.supply < p.capacity else p.capacity for p in outputs]
                expected = _fair_allocate(min(total_in, component.max_flow), limits)
                for i, pipe in enumerate(outputs):
                    if abs(pipe.supply - expected[i]) > tolerance:
                        issues.append(f"[{name}] 出{i} supply={pipe.supply:.4f} ≠ 期望 {expected[i]:.4f}")
            if inputs and outputs:
                expected_cap = min(sum(p.flow for p in outputs), component.max_flow)
                if inputs[0].capacity > expected_cap + tolerance:
                    issues.append(f"[{name}] 入管容量 {inputs[0].capacity:.4f} > Σ出流 {expected_cap:.4f}")

        elif isinstance(component, Merger):
            if abs(total_in - total_out) > tolerance:
                issues.append(f"[{name}] 汇流器不守恒: in={total_in:.4f} out={total_out:.4f}")
            if inputs:
                downstream_cap = min(p.capacity for p in outputs) if outputs else component.max_flow
                capacity_limit = min(component.max_flow, downstream_cap)
                limits = [p.max_flow if p.supply > p.capacity else max(p.supply, 0) for p in inputs]
                expected = _fair_allocate(capacity_limit, limits)
                for i, pipe in enumerate(inputs):
                    if abs(pipe.capacity - expected[i]) > tolerance:
                        issues.append(f"[{name}] 入{i} capacity={pipe.capacity:.4f} ≠ 期望 {expected[i]:.4f}")

        elif isinstance(component, Limiter):
            if abs(total_in - total_out) > tolerance:
                issues.append(f"[{name}] 限流器不守恒: in={total_in:.4f} out={total_out:.4f}")
            if total_in > component.max_flow + tolerance:
                issues.append(f"[{name}] 限流器流量 {total_in:.4f} > max_flow {component.max_flow}")

    return issues
