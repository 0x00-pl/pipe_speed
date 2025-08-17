"""端到端网络场景测试"""

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


class TestSimpleChain:
    """简单链路"""

    def test_inlet_to_outlet(self):
        """入口(10) → 出口(10)：直通 10"""
        net = _build_and_solve(
            nodes={
                "in": {"max_flow": 10},
                "out": {"max_flow": 10},
            },
            edges=[
                {"from": "in", "to": "out"},
            ]
        )
        assert _flow(net, "in", "out") == pytest.approx(10)

    def test_inlet_to_outlet_limited_by_outlet(self):
        """入口(100) → 出口(10)：出口小，入口被限"""
        net = _build_and_solve(
            nodes={
                "in": {"max_flow": 100},
                "out": {"max_flow": 10},
            },
            edges=[
                {"from": "in", "to": "out"},
            ]
        )
        assert _flow(net, "in", "out") == pytest.approx(10)


class TestSplitterToTwoOutlets:
    """入口 → 分流器 → 两出口"""

    def test_basic(self):
        """入口(10) → 分流器 → [出口A(max=10), 出口B(max=10)]"""
        net = _build_and_solve(
            nodes={
                "in": {"max_flow": 10},
                "sp": {},
                "a": {"max_flow": 10},
                "b": {"max_flow": 10},
            },
            edges=[
                {"from": "in", "to": "sp"},
                {"from": "sp", "to": "a"},
                {"from": "sp", "to": "b"},
            ]
        )
        assert _flow(net, "sp", "a") == pytest.approx(5)
        assert _flow(net, "sp", "b") == pytest.approx(5)

    def test_one_outlet_limited(self):
        """入口(20) → 分流器 → [出口A(限流max=5), 出口B(max=100)]：A=5, B=15"""
        net = _build_and_solve(
            nodes={
                "in": {"max_flow": 20},
                "sp": {},
                "lim": {"max_flow": 5},
                "a": {"max_flow": 100},
                "b": {"max_flow": 100},
            },
            edges=[
                {"from": "in", "to": "sp"},
                {"from": "sp", "to": "lim"},
                {"from": "lim", "to": "a"},
                {"from": "sp", "to": "b"},
            ]
        )
        assert _flow(net, "sp", "lim") == pytest.approx(5)
        assert _flow(net, "sp", "b") == pytest.approx(15)


class TestTwoInletsToMerger:
    """两入口 → 汇流器 → 出口"""

    def test_basic(self):
        """A(5)+B(5) → 汇流器 → 出口(100)：总 10"""
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
        assert _flow(net, "mg", "out") == pytest.approx(10)


class TestExplicitType:
    def test_invalid_type_error(self):
        from pipe_speed.network import build_network
        with pytest.raises(ValueError, match="未知的类型"):
            build_network(
                {"x": {"type": "unknown"}},
                [{"from": "x", "to": "a"}, {"from": "a", "to": "b"}]
            )


class TestComplexNetwork:
    """多级混合网络"""

    def test_splitter_limiter_chain(self):
        """入口(100) → 分流器 → [限流器(30)→出口A, 出口B(100)]：限流路=30, 直通路=70"""
        net = _build_and_solve(
            nodes={
                "in": {"max_flow": 100},
                "sp": {},
                "lim": {"max_flow": 30},
                "a": {"max_flow": 100},
                "b": {"max_flow": 100},
            },
            edges=[
                {"from": "in", "to": "sp"},
                {"from": "sp", "to": "lim"},
                {"from": "lim", "to": "a"},
                {"from": "sp", "to": "b"},
            ]
        )
        assert _flow(net, "sp", "lim") == pytest.approx(30)
        assert _flow(net, "lim", "a") == pytest.approx(30)
        assert _flow(net, "sp", "b") == pytest.approx(70)
        assert _flow(net, "in", "sp") == pytest.approx(100)

    def test_splitter_limiter_merger_chain(self):
        """入口(100) → 分流器 → [限流器(20)→出口A, 汇流器→出口B]，另入口2(10)→汇流器"""
        net = _build_and_solve(
            nodes={
                "in1": {"max_flow": 100},
                "in2": {"max_flow": 10},
                "sp": {},
                "lim": {"max_flow": 20},
                "mg": {},
                "a": {"max_flow": 100},
                "b": {"max_flow": 100},
            },
            edges=[
                {"from": "in1", "to": "sp"},
                {"from": "sp", "to": "lim"},
                {"from": "lim", "to": "a"},
                {"from": "sp", "to": "mg"},
                {"from": "in2", "to": "mg"},
                {"from": "mg", "to": "b"},
            ]
        )
        # 分流器入 70，限流路 20，汇流路 50
        assert _flow(net, "sp", "lim") == pytest.approx(20)
        assert _flow(net, "sp", "mg") == pytest.approx(50)
        assert _flow(net, "in2", "mg") == pytest.approx(10)
        assert _flow(net, "mg", "b") == pytest.approx(60)

    def test_pipe_capacity_limits_split(self):
        """管道自身 max_flow 限制分流"""
        net = _build_and_solve(
            nodes={
                "in": {"max_flow": 100},
                "sp": {},
                "a": {"max_flow": 100},
                "b": {"max_flow": 100},
            },
            edges=[
                {"from": "in", "to": "sp"},
                {"from": "sp", "to": "a", "max_flow": 10},
                {"from": "sp", "to": "b"},
            ]
        )
        assert _flow(net, "sp", "a") == pytest.approx(10)
        assert _flow(net, "sp", "b") == pytest.approx(90)
