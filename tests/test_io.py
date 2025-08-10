"""io_handler 测试：解析、格式化、查询"""

import pytest
from pipe_speed.io_handler import load_network, format_results, format_echo
from pipe_speed.solver import solve


class TestLoadTextFormat:
    def test_simple(self):
        net, queries = load_network("-", content="s -> a\na -> b\nb -> c")
        assert len(net.pipes) == 3
        assert not queries

    def test_with_node_attr(self):
        net, queries = load_network("-", content="s : 50\ns -> a\na -> b")
        assert net.nodes["s"].max_flow == 50

    def test_with_queries(self):
        net, queries = load_network("-", content="s -> a\na -> b\nb -> c\na -> b : ?")
        assert len(queries) == 1
        assert queries[0].source == "a"
        assert queries[0].target == "b"

    def test_query_wildcard_source(self):
        net, queries = load_network("-", content="s -> a\n* -> a : ?")
        assert queries[0].source == "*"
        assert queries[0].target == "a"

    def test_query_node_wildcard(self):
        net, queries = load_network("-", content="s -> a\na : ?")
        assert queries[0].node == "a"

    def test_comment_lines(self):
        net, _ = load_network("-", content="# comment\ns -> a\n# another\na -> b")
        assert len(net.pipes) == 2

    def test_empty_lines(self):
        net, _ = load_network("-", content="s -> a\n\n\na -> b")
        assert len(net.pipes) == 2

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            load_network("-", content="invalid line")

    def test_no_edges(self):
        with pytest.raises(ValueError):
            load_network("-", content="s : 10")

    def test_invalid_node_value(self):
        with pytest.raises(ValueError):
            load_network("-", content="s : abc\ns -> a")


class TestLoadJsonFormat:
    def test_simple_json(self):
        net, _ = load_network("-", content='{"nodes":{},"edges":[{"from":"a","to":"b"}]}')
        assert len(net.pipes) == 1

    def test_json_with_nodes(self):
        net, _ = load_network("-", content='{"nodes":{"s":{"max_flow":50}},"edges":[{"from":"s","to":"a"}]}')
        assert net.nodes["s"].max_flow == 50


class TestFormatResults:
    def test_basic_output(self):
        net, _ = load_network("-", content="s : 10\ns -> a\na -> b")
        solve(net)
        result = format_results(net, 3)
        assert "s → a" in result
        assert "a → b" in result

    def test_fraction_output(self):
        net, _ = load_network("-", content="s : 10\ns -> a")
        solve(net, use_fraction=True)
        result = format_results(net, 2, fraction=True)
        assert "/" in result

    def test_query_filter(self):
        net, queries = load_network("-", content="s -> a\na -> b\nb -> c\na -> b : ?")
        solve(net)
        result = format_results(net, 2, queries=queries)
        assert "a → b" in result
        assert "s → a" not in result

    def test_empty_query_result(self):
        net, queries = load_network("-", content="s -> a\nx -> y : ?")
        solve(net)
        result = format_results(net, 2, queries=queries)
        assert "(无匹配结果)" in result


class TestFormatEcho:
    def test_default_nodes_not_shown(self):
        net, _ = load_network("-", content="s -> a\na -> b")
        result = format_echo(net)
        assert "s -> a" in result
        assert "a -> b" in result
        # default max_flow (120) not shown
        assert ":" not in result

    def test_non_default_shown_with_queries(self):
        net, queries = load_network("-", content="s : 50\ns -> a\ns : ?")
        result = format_echo(net, queries)
        assert "s : 50" in result
        assert "s : ?" in result


class TestFileNotFound:
    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_network("nonexistent_file.txt")


class TestTypeOverride:
    def test_explicit_type_in_text(self):
        """Node with explicit type override"""
        net, _ = load_network("-", content="s : 50\ns -> a\na -> b\nb -> c")
        # s=inlet, a=limiter, b=limiter, c=outlet
        assert len(net.nodes) == 4


class TestPipeMaxFlow:
    def test_pipe_max_flow_used(self):
        net, _ = load_network("-", content="s : 10\ns -> a\na -> b")
        for p in net.pipes:
            assert p.max_flow == 120  # default


class TestFractionFormatting:
    def test_fraction_pipe_max_flow_ratio(self):
        from fractions import Fraction
        from pipe_speed.io_handler import format_results
        net, _ = load_network("-", content="s : 10\ns -> a\na -> b")
        solve(net, use_fraction=True)
        result = format_results(net, 2, fraction=True)
        assert "(1/12)" in result  # 10/120 = 1/12
