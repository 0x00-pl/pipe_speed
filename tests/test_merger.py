"""汇流器测试：均抽、空管缺口再分配、全部空管降流量、自身超限截断"""

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


class TestMergerEvenDraw:
    """简单均抽"""

    def test_two_way_even(self):
        """入口A(5) + 入口B(5) → 汇流器 → 出口(100)：各抽 5"""
        net = _build_and_solve(
            nodes={
                "in_a": {"max_flow": 5},
                "in_b": {"max_flow": 5},
                "mg": {},
                "out": {"max_flow": 100},
            },
            edges=[
                {"from": "in_a", "to": "mg"},
                {"from": "in_b", "to": "mg"},
                {"from": "mg", "to": "out"},
            ]
        )
        assert _flow(net, "in_a", "mg") == pytest.approx(5)
        assert _flow(net, "in_b", "mg") == pytest.approx(5)
        assert _flow(net, "mg", "out") == pytest.approx(10)

    def test_three_way_even(self):
        """A(3)+B(3)+C(3) → 汇流器 → 出口：各抽 3，总 9"""
        net = _build_and_solve(
            nodes={
                "in_a": {"max_flow": 3},
                "in_b": {"max_flow": 3},
                "in_c": {"max_flow": 3},
                "mg": {},
                "out": {"max_flow": 100},
            },
            edges=[
                {"from": "in_a", "to": "mg"},
                {"from": "in_b", "to": "mg"},
                {"from": "in_c", "to": "mg"},
                {"from": "mg", "to": "out"},
            ]
        )
        assert _flow(net, "in_a", "mg") == pytest.approx(3)
        assert _flow(net, "in_b", "mg") == pytest.approx(3)
        assert _flow(net, "in_c", "mg") == pytest.approx(3)
        assert _flow(net, "mg", "out") == pytest.approx(9)


class TestMergerUnderflowRedistribution:
    """单管空管，缺口再分配"""

    def test_one_pipe_empty(self):
        """A(1)+B(10) → 汇流器 → 出口(100)：先均抽 5.5 但 A 只有 1，实际 A=1, B=10"""
        net = _build_and_solve(
            nodes={
                "in_a": {"max_flow": 1},
                "in_b": {"max_flow": 10},
                "mg": {},
                "out": {"max_flow": 100},
            },
            edges=[
                {"from": "in_a", "to": "mg"},
                {"from": "in_b", "to": "mg"},
                {"from": "mg", "to": "out"},
            ]
        )
        assert _flow(net, "in_a", "mg") == pytest.approx(1)
        assert _flow(net, "in_b", "mg") == pytest.approx(10)
        assert _flow(net, "mg", "out") == pytest.approx(11)


class TestMergerAllEmpty:
    """全部空管 → 降流量"""

    def test_all_inputs_empty(self):
        """A(2)+B(3) → 汇流器 → 出口(100)：A=2, B=3, 总=5"""
        net = _build_and_solve(
            nodes={
                "in_a": {"max_flow": 2},
                "in_b": {"max_flow": 3},
                "mg": {},
                "out": {"max_flow": 100},
            },
            edges=[
                {"from": "in_a", "to": "mg"},
                {"from": "in_b", "to": "mg"},
                {"from": "mg", "to": "out"},
            ]
        )
        assert _flow(net, "in_a", "mg") == pytest.approx(2)
        assert _flow(net, "in_b", "mg") == pytest.approx(3)
        assert _flow(net, "mg", "out") == pytest.approx(5)


class TestMergerSelfLimit:
    """汇流器自身 max_flow 限流"""

    def test_merger_max_flow_cap(self):
        """A(50)+B(50) → 汇流器(max=30) → 出口(100)：均抽 15 各"""
        net = _build_and_solve(
            nodes={
                "in_a": {"max_flow": 50},
                "in_b": {"max_flow": 50},
                "mg": {"max_flow": 30},
                "out": {"max_flow": 100},
            },
            edges=[
                {"from": "in_a", "to": "mg"},
                {"from": "in_b", "to": "mg"},
                {"from": "mg", "to": "out"},
            ]
        )
        assert _flow(net, "in_a", "mg") == pytest.approx(15)
        assert _flow(net, "in_b", "mg") == pytest.approx(15)
        assert _flow(net, "mg", "out") == pytest.approx(30)
