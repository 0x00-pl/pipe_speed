"""validate 测试：守恒性和分配验证"""

import pytest
from pipe_speed.io_handler import load_network
from pipe_speed.solver import solve
from pipe_speed.validate import validate


def test_all_pass_simple():
    net, _ = load_network("-", content="s : 10\ns -> a\na -> b\nb -> c")
    solve(net)
    assert validate(net) == []


def test_all_pass_splitter():
    net, _ = load_network("-", content="s : 10\ns -> sp\nsp -> a\nsp -> b")
    solve(net)
    assert validate(net) == []


def test_all_pass_merger():
    net, _ = load_network("-", content="a : 5\nb : 5\na -> mg\nb -> mg\nmg -> out")
    solve(net)
    assert validate(net) == []


def test_all_pass_limiter():
    net, _ = load_network("-", content="s : 10\ns -> lim\nlim : 5\nlim -> out")
    solve(net)
    assert validate(net) == []


def test_all_pass_cyclic():
    net, _ = load_network("-", content="s : 120\ns -> a\na -> b\nb -> a\nb -> e")
    solve(net)
    assert validate(net) == []


def test_conservation_violation_caught():
    """Manually break conservation and verify validate catches it"""
    net, _ = load_network("-", content="s : 10\ns -> a\na -> b")
    solve(net)
    # Manually break a pipe
    for pipe in net.pipes:
        if pipe.source == "a":
            pipe.supply = 999.0
    issues = validate(net)
    assert len(issues) > 0


def test_limiter_exceed_caught():
    """Verify validate catches limiter exceeding max_flow"""
    net, _ = load_network("-", content="s : 100\ns -> lim\nlim : 5\nlim -> out")
    solve(net)
    for pipe in net.pipes:
        if pipe.source == "s":
            pipe.supply = 100.0
            pipe.capacity = 100.0
    issues = validate(net)
    assert len(issues) > 0


def test_merger_capacity_check():
    """Verify validate checks merger capacity allocation"""
    net, _ = load_network("-", content="a : 5\nb : 5\na -> mg\nb -> mg\nmg : 3\nmg -> out")
    solve(net)
    assert validate(net) == []


def test_splitter_supply_check():
    """Verify validate checks splitter supply allocation"""
    net, _ = load_network("-", content="s : 6\ns -> sp\nsp -> a\nsp -> b\nsp -> c")
    solve(net)
    assert validate(net) == []


def test_inlet_no_output_caught():
    """Inlet with max_flow=0 produces no output — validate flags it"""
    net, _ = load_network("-", content="s : 0\ns -> a\na -> b")
    solve(net)
    issues = validate(net)
    # Inlet with max_flow=0 pushes 0 supply → output is 0 → flagged
    assert any("入口无输出" in i for i in issues)


def test_fair_allocate_empty():
    from pipe_speed.validate import _fair_allocate
    assert _fair_allocate(100, []) == []
