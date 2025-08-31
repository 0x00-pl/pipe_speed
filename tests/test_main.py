"""main.py CLI 测试"""

import pytest
import sys
from pathlib import Path
from pipe_speed.main import main, _read_input


class TestReadInput:
    def test_read_stdin(self, monkeypatch):
        monkeypatch.setattr(sys, 'stdin', type(sys.stdin)())
        monkeypatch.setattr(sys.stdin, 'read', lambda: "s -> a\na -> b")
        result = _read_input("-")
        assert "s -> a" in result

    def test_read_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("s -> a\na -> b", encoding="utf-8")
        result = _read_input(str(f))
        assert "s -> a" in result

    def test_read_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            _read_input("nonexistent_file_xyz.txt")

    def test_bom_stripped(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b'\xef\xbb\xbfs -> a\na -> b')
        result = _read_input(str(f))
        assert not result.startswith('﻿')
        assert result.startswith('s')


class TestMainBasic:
    def test_text_input(self, tmp_path, capsys):
        f = tmp_path / "net.txt"
        f.write_text("s -> a\na -> b\nb -> c")
        sys.argv = ["pipe-speed", str(f)]
        try:
            main()
        except SystemExit:
            pass
        captured = capsys.readouterr()
        assert "s → a" in captured.out

    def test_stdin_input(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, 'stdin', type(sys.stdin)())
        monkeypatch.setattr(sys.stdin, 'read', lambda: "s -> a\na -> b")
        sys.argv = ["pipe-speed", "-"]
        try:
            main()
        except SystemExit:
            pass
        captured = capsys.readouterr()
        assert "s → a" in captured.out

    def test_echo_flag(self, tmp_path, capsys):
        f = tmp_path / "net.txt"
        f.write_text("s : 50\ns -> a")
        sys.argv = ["pipe-speed", str(f), "--echo"]
        try:
            main()
        except SystemExit:
            pass
        captured = capsys.readouterr()
        assert "输入" in captured.out

    def test_show_flag(self, tmp_path, capsys):
        f = tmp_path / "net.txt"
        f.write_text("s -> a\na -> b")
        sys.argv = ["pipe-speed", str(f), "--mermaid-ascii"]
        try:
            main()
        except SystemExit:
            pass
        captured = capsys.readouterr()
        assert "拓扑" in captured.out

    def test_json_flag(self, tmp_path, capsys):
        f = tmp_path / "net.txt"
        f.write_text("s -> a\na -> b")
        sys.argv = ["pipe-speed", str(f), "--json"]
        try:
            main()
        except SystemExit:
            pass
        captured = capsys.readouterr()
        assert '"source"' in captured.out

    def test_fraction_flag(self, tmp_path, capsys):
        f = tmp_path / "net.txt"
        f.write_text("s : 10\ns -> a")
        sys.argv = ["pipe-speed", str(f), "--fraction"]
        try:
            main()
        except SystemExit:
            pass
        captured = capsys.readouterr()
        assert "/" in captured.out


class TestMainErrors:
    def test_file_not_found(self, capsys):
        sys.argv = ["pipe-speed", "nonexistent_xyz.txt"]
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1

    def test_invalid_network(self, tmp_path, capsys):
        f = tmp_path / "net.txt"
        f.write_text("invalid line here")
        sys.argv = ["pipe-speed", str(f)]
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1

    def test_missing_edges_json(self, capsys):
        import json
        sys.argv = ["pipe-speed", "-"]
        import io
        sys.stdin = io.StringIO('{"nodes":{}, "edges":[]}')
        with pytest.raises(SystemExit):
            main()

    def test_validate_failure(self, tmp_path, capsys):
        """Validate catches manually broken network"""
        # Use a network that will pass solve but fail validate
        f = tmp_path / "net.txt"
        f.write_text("s : 0\ns -> a\na -> b")
        sys.argv = ["pipe-speed", str(f)]
        try:
            main()
        except SystemExit:
            pass
        captured = capsys.readouterr()
        # Inlet with max_flow=0 triggers validation warning
        assert "验证失败" in captured.err or "入口无输出" in captured.err


class TestMainJsonInput:
    def test_json_file(self, tmp_path, capsys):
        import json
        f = tmp_path / "net.json"
        f.write_text(json.dumps({"nodes": {}, "edges": [{"from": "a", "to": "b"}]}))
        sys.argv = ["pipe-speed", str(f)]
        try:
            main()
        except SystemExit:
            pass
        captured = capsys.readouterr()
        assert "a → b" in captured.out
