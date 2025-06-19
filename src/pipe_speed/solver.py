"""管道网络流速求解器

每轮迭代遍历所有元件，每个元件:
  1. flow = min(Σsupply, max_flow)
  2. capacity: 从 max_flow 均抽输入 (设上游 capacity)
  3. supply:   推 current_flow 均分到输出 (设下游 supply)
"""

import math
from fractions import Fraction

from .models import Pipe, Inlet, Outlet, Splitter, Merger, Limiter
from .network import Network, topological_order

INF = float('inf')
EPS = 1e-12


def _val(x: float) -> float:
    return 0.0 if math.isinf(x) else x


def _fcap(x: float) -> float:
    return 1e30 if math.isinf(x) else x


def draw_capacity(max_flow: float, supplies: list[float]) -> list[float]:
    n = len(supplies)
    if n == 0:
        return []
    caps = [0.0] * n
    rem = [max(s, 0.0) for s in supplies]
    flow = max_flow if not math.isinf(max_flow) else INF
    active = list(range(n))
    while flow > EPS and active:
        e = min(rem[i] for i in active)
        if e <= EPS:
            active = [i for i in active if rem[i] > EPS]
            continue
        f = min(e * len(active), flow)
        flow -= f
        per = f / len(active)
        for i in list(active):
            caps[i] += per
            rem[i] -= per
            if rem[i] <= EPS:
                active.remove(i)
    return caps


def push_supply(current_flow: float, capacities: list[float]) -> list[float]:
    n = len(capacities)
    if n == 0:
        return []
    out_s = [0.0] * n
    rem = [max(c, 0.0) for c in capacities]
    flow = current_flow if not math.isinf(current_flow) else INF
    active = list(range(n))
    while flow > EPS and active:
        e = min(rem[i] for i in active)
        if e <= EPS:
            active = [i for i in active if rem[i] > EPS]
            continue
        f = min(e * len(active), flow)
        flow -= f
        per = f / len(active)
        for i in list(active):
            out_s[i] += per
            rem[i] -= per
            if rem[i] <= EPS:
                active.remove(i)
    return out_s


def solve(net: Network, epsilon: float = 1e-9, max_iterations: int = 1000,
          use_fraction: bool = False) -> int:
    order = topological_order(net)  # 仅用于稳定迭代顺序

    for p in net.pipes:
        p.supply = 1.0

    prev_flows = [float(p.flow) for p in net.pipes]

    for iteration in range(max_iterations):
        for name in order:
            comp = net.nodes[name]
            in_p = net.in_edges[name]
            out_p = net.out_edges[name]
            mf = comp.max_flow

            # ---- 1. flow = min(Σsupply, max_flow) ----
            total_in = sum(_val(p.supply) for p in in_p)
            current_flow = total_in if math.isinf(mf) else min(total_in, mf)

            # ---- 2. 输出 supply（先推，让下游看到新 supply）----
            if out_p:
                caps = [min(_fcap(p.capacity), _fcap(p.max_flow)) for p in out_p]

                if isinstance(comp, Inlet):
                    f = mf if not math.isinf(mf) else INF
                    supplies = push_supply(f, caps)
                elif isinstance(comp, Outlet):
                    supplies = []
                elif isinstance(comp, Splitter):
                    if in_p:
                        current_flow = min(_val(in_p[0].supply),
                                          mf if not math.isinf(mf) else INF)
                    supplies = push_supply(current_flow, caps)
                elif isinstance(comp, Merger):
                    if out_p:
                        downstream_cap = _fcap(out_p[0].capacity)
                        current_flow = min(current_flow, downstream_cap)
                    supplies = push_supply(current_flow, caps)
                elif isinstance(comp, Limiter):
                    if out_p:
                        downstream_cap = _fcap(out_p[0].capacity)
                        current_flow = min(current_flow, downstream_cap)
                    supplies = push_supply(current_flow, caps)

                for p, s in zip(out_p, supplies):
                    p.supply = s

            # ---- 3. 输入 capacity（后拉，基于刚更新的 supply）----
            if in_p:
                if isinstance(comp, Inlet):
                    pass
                elif isinstance(comp, Outlet):
                    cap = mf if not math.isinf(mf) else INF
                    if cap < INF:
                        each = cap / len(in_p)
                        for p in in_p:
                            p.capacity = each
                elif isinstance(comp, Splitter):
                    total_out = sum(_val(p.supply) for p in out_p)
                    f = total_out if math.isinf(mf) else min(total_out, mf)
                    in_p[0].capacity = f
                elif isinstance(comp, Merger):
                    supplies = [_val(p.supply) for p in in_p]
                    total_supply = sum(supplies)
                    downstream_cap = _fcap(out_p[0].capacity) if out_p else INF
                    total_cap = mf if math.isinf(mf) else min(mf, downstream_cap)
                    if not math.isinf(total_cap) and total_cap < total_supply - EPS:
                        # 瓶颈：均抽
                        caps = draw_capacity(total_cap, supplies)
                    else:
                        # 非瓶颈：慷慨（每输入可承担 max_flow）
                        caps = [mf] * len(in_p)
                    for p, c in zip(in_p, caps):
                        p.capacity = c
                elif isinstance(comp, Limiter):
                    c_out = _fcap(out_p[0].capacity) if out_p else INF
                    cap = mf if math.isinf(mf) else min(mf, c_out)
                    in_p[0].capacity = cap

        # ---- 收敛判断 ----
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
