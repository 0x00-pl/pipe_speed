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

    def test_format_single_iteration(self):
        from pipe_speed.io_handler import format_results
        net, _ = load_network("-", content="s -> a")
        solve(net)
        result = format_results(net, 1)
        assert "收敛于 1 次迭代" in result


class TestQueryMatching:
    def test_query_node_match(self):
        from pipe_speed.io_handler import Query
        q = Query(node="a")
        assert q.matches("a", "b")
        assert q.matches("b", "a")
        assert not q.matches("b", "c")

    def test_query_wildcard_both(self):
        from pipe_speed.io_handler import Query
        q = Query(source="*", target="*")
        assert q.matches("a", "b")

    def test_query_source_only(self):
        from pipe_speed.io_handler import Query
        q = Query(source="a")
        assert q.matches("a", "b")


class TestTextFormatErrors:
    def test_empty_node_name_in_edge(self):
        with pytest.raises(ValueError, match="节点名为空"):
            load_network("-", content=" -> b")

    def test_empty_node_name_in_attr(self):
        with pytest.raises(ValueError, match="名称为空"):
            load_network("-", content=" : 10")

    def test_malformed_edge(self):
        with pytest.raises(ValueError, match="无效的管道定义"):
            load_network("-", content="a -> b -> c")


class TestFormatResultsEdgeCases:
    def test_zero_total_inlet_fraction(self):
        from pipe_speed.io_handler import format_results
        net, _ = load_network("-", content="in : 0\nin -> a\na -> b")
        solve(net)
        result = format_results(net, 2, fraction=True)
        assert "in → a" in result


class TestRenderNetwork:
    def test_render_empty(self):
        from pipe_speed.io_handler import render_network
        from pipe_speed.network import Network
        net = Network()
        result = render_network(net)
        assert "空网络" in result

    def test_render_without_mermaidx(self, monkeypatch):
        """Test render without mermaidx installed"""
        import builtins
        original_import = builtins.__import__
        def mock_import(name, *args, **kwargs):
            if name == 'mermaidx':
                raise ImportError("No module named 'mermaidx'")
            return original_import(name, *args, **kwargs)
        monkeypatch.setattr(builtins, '__import__', mock_import)
        from pipe_speed.io_handler import render_network
        net, _ = load_network("-", content="s -> a\na -> b")
        result = render_network(net)
        assert "mermaidx" in result.lower()

    def test_render_basic(self):
        from pipe_speed.io_handler import render_network
        net, _ = load_network("-", content="s -> a\na -> b\nb -> c")
        result = render_network(net)
        assert "s" in result
        assert "a" in result


class TestJsonFormatEdgeCases:
    def test_json_missing_edges(self):
        with pytest.raises(ValueError, match="缺少 'edges'"):
            load_network("-", content='{"nodes":{}}')

    def test_json_file_loading(self, tmp_path):
        import json
        f = tmp_path / "test.json"
        f.write_text(json.dumps({"edges": [{"from": "a", "to": "b"}]}))
        net, _ = load_network(str(f))
        assert len(net.pipes) == 1
