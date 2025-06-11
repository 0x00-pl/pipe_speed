"""分流器测试：均分、满容溢出再分配、全部满管反压、自身超限截断"""

import pytest
from pipe_speed.models import Inlet, Outlet, Splitter
from pipe_speed.network import Network, build_network
from pipe_speed.solver import solve


def _build_and_solve(nodes: dict, edges: list[dict]) -> Network:
    """辅助：构建网络并求解"""
    net = build_network(nodes, edges)
    solve(net)
    return net


def _flow(net: Network, source: str, target: str) -> float:
    """辅助：查找管道流速"""
    for p in net.pipes:
        if p.source == source and p.target == target:
            return p.flow
    raise ValueError(f"管道 {source}→{target} 未找到")


class TestSplitterEvenDistribution:
    """简单均分"""

    def test_two_way_even(self):
        """入口(10) → 分流器 → [出口A, 出口B]：各 5"""
        net = _build_and_solve(
            nodes={
                "in": {"max_flow": 10},
                "sp": {},
                "a": {"max_flow": 100},
                "b": {"max_flow": 100},
            },
            edges=[
                {"from": "in", "to": "sp"},
                {"from": "sp", "to": "a"},
                {"from": "sp", "to": "b"},
            ]
        )
        assert _flow(net, "in", "sp") == pytest.approx(10)
        assert _flow(net, "sp", "a") == pytest.approx(5)
        assert _flow(net, "sp", "b") == pytest.approx(5)

    def test_three_way_even(self):
        """入口(30) → 分流器 → [A,B,C]：各 10"""
        net = _build_and_solve(
            nodes={
                "in": {"max_flow": 30},
                "sp": {},
                "a": {"max_flow": 100},
                "b": {"max_flow": 100},
                "c": {"max_flow": 100},
            },
            edges=[
                {"from": "in", "to": "sp"},
                {"from": "sp", "to": "a"},
                {"from": "sp", "to": "b"},
                {"from": "sp", "to": "c"},
            ]
        )
        assert _flow(net, "in", "sp") == pytest.approx(30)
        assert _flow(net, "sp", "a") == pytest.approx(10)
        assert _flow(net, "sp", "b") == pytest.approx(10)
        assert _flow(net, "sp", "c") == pytest.approx(10)


class TestSplitterOverflowRedistribution:
    """单管满容，溢出再分配"""

    def test_one_pipe_full(self):
        """入口(10) → 分流器 → [A(cap=3), B(cap=100)]：A=3, B=7"""
        net = _build_and_solve(
            nodes={
                "in": {"max_flow": 10},
                "sp": {},
                "a": {"max_flow": 100},
                "b": {"max_flow": 100},
            },
            edges=[
                {"from": "in", "to": "sp"},
                {"from": "sp", "to": "a", "max_flow": 3},
                {"from": "sp", "to": "b"},
            ]
        )
        assert _flow(net, "sp", "a") == pytest.approx(3)
        assert _flow(net, "sp", "b") == pytest.approx(7)
        assert _flow(net, "in", "sp") == pytest.approx(10)

    def test_two_pipes_full_third_takes_rest(self):
        """入口(30) → 分流器 → [A(cap=3), B(cap=5), C(cap=100)]：A=3, B=5, C=22"""
        net = _build_and_solve(
            nodes={
                "in": {"max_flow": 30},
                "sp": {},
                "a": {"max_flow": 100},
                "b": {"max_flow": 100},
                "c": {"max_flow": 100},
            },
            edges=[
                {"from": "in", "to": "sp"},
                {"from": "sp", "to": "a", "max_flow": 3},
                {"from": "sp", "to": "b", "max_flow": 5},
                {"from": "sp", "to": "c"},
            ]
        )
        assert _flow(net, "sp", "a") == pytest.approx(3)
        assert _flow(net, "sp", "b") == pytest.approx(5)
        assert _flow(net, "sp", "c") == pytest.approx(22)
        assert _flow(net, "in", "sp") == pytest.approx(30)


class TestSplitterAllFullBackpressure:
    """全部满管 → 反压输入"""

    def test_all_outputs_full(self):
        """入口(100) → 分流器 → [A(cap=3), B(cap=5), C(cap=2)]：全部被限，反压入口"""
        net = _build_and_solve(
            nodes={
                "in": {"max_flow": 100},
                "sp": {},
                "a": {"max_flow": 100},
                "b": {"max_flow": 100},
                "c": {"max_flow": 100},
            },
            edges=[
                {"from": "in", "to": "sp"},
                {"from": "sp", "to": "a", "max_flow": 3},
                {"from": "sp", "to": "b", "max_flow": 5},
                {"from": "sp", "to": "c", "max_flow": 2},
            ]
        )
        assert _flow(net, "sp", "a") == pytest.approx(3)
        assert _flow(net, "sp", "b") == pytest.approx(5)
        assert _flow(net, "sp", "c") == pytest.approx(2)
        # 反压：入口只能推 3+5+2=10
        assert _flow(net, "in", "sp") == pytest.approx(10)


class TestSplitterSelfLimit:
    """分流器自身 max_flow 限流"""

    def test_splitter_max_flow_cap(self):
        """入口(100) → 分流器(max=20) → [A, B]：各 10，入口被限 20"""
        net = _build_and_solve(
            nodes={
                "in": {"max_flow": 100},
                "sp": {"max_flow": 20},
                "a": {"max_flow": 100},
                "b": {"max_flow": 100},
            },
            edges=[
                {"from": "in", "to": "sp"},
                {"from": "sp", "to": "a"},
                {"from": "sp", "to": "b"},
            ]
        )
        assert _flow(net, "in", "sp") == pytest.approx(20)
        assert _flow(net, "sp", "a") == pytest.approx(10)
        assert _flow(net, "sp", "b") == pytest.approx(10)
