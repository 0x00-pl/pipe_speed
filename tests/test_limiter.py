"""限流器测试：直通、截断反压"""

import pytest
from pipe_speed.network import build_network
from pipe_speed.solver import solve


def _build_and_solve(nodes: dict, edges: list[dict]):
    net = build_network(nodes, edges)
    solve(net)
    return net


def _flow(net, source: str, target: str) -> float:
    for p in net.pipes:
        if p.source == source and p.target == target:
            return p.flow
    raise ValueError(f"管道 {source}→{target} 未找到")


class TestLimiterPassthrough:
    """低于上限 → 直通"""

    def test_below_limit(self):
        """入口(5) → 限流器(max=10) → 出口(100)：直通 5"""
        net = _build_and_solve(
            nodes={
                "in": {"max_flow": 5},
                "lim": {"max_flow": 10},
                "out": {"max_flow": 100},
            },
            edges=[
                {"from": "in", "to": "lim"},
                {"from": "lim", "to": "out"},
            ]
        )
        assert _flow(net, "in", "lim") == pytest.approx(5)
        assert _flow(net, "lim", "out") == pytest.approx(5)


class TestLimiterCap:
    """高于上限 → 截断"""

    def test_above_limit(self):
        """入口(100) → 限流器(max=10) → 出口(100)：截断为 10"""
        net = _build_and_solve(
            nodes={
                "in": {"max_flow": 100},
                "lim": {"max_flow": 10},
                "out": {"max_flow": 100},
            },
            edges=[
                {"from": "in", "to": "lim"},
                {"from": "lim", "to": "out"},
            ]
        )
        assert _flow(net, "in", "lim") == pytest.approx(10)
        assert _flow(net, "lim", "out") == pytest.approx(10)


class TestLimiterBackpressure:
    """限流器造成的反压传播到入口"""

    def test_backpressure_to_inlet(self):
        """入口(100) → 限流器(10) → 出口(100)：入口被反压至 10"""
        net = _build_and_solve(
            nodes={
                "in": {"max_flow": 100},
                "lim": {"max_flow": 10},
                "out": {"max_flow": 100},
            },
            edges=[
                {"from": "in", "to": "lim"},
                {"from": "lim", "to": "out"},
            ]
        )
        assert _flow(net, "in", "lim") == pytest.approx(10)
