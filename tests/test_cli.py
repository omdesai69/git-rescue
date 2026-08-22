"""Tests for cli.py — subcommand invocation and argument parsing."""

from __future__ import annotations

from pathlib import Path
import pytest
from git_rescue.cli import build_parser, main, Color


class TestParser:
    def test_default_command(self):
        assert build_parser().parse_args([]).command is None

    def test_timeline_command(self):
        assert build_parser().parse_args(["timeline"]).command == "timeline"

    def test_timeline_with_limit(self):
        args = build_parser().parse_args(["timeline", "-n", "30"])
        assert args.command == "timeline" and args.limit == 30

    def test_undo_command(self):
        assert build_parser().parse_args(["undo"]).command == "undo"

    def test_branches_command(self):
        args = build_parser().parse_args(["branches"])
        assert args.command == "branches" and args.restore is None

    def test_branches_restore(self):
        args = build_parser().parse_args(["branches", "--restore", "my-branch"])
        assert args.command == "branches" and args.restore == "my-branch"

    def test_files_command(self):
        assert build_parser().parse_args(["files"]).command == "files"

    def test_no_color_flag(self):
        assert build_parser().parse_args(["--no-color"]).no_color is True

    def test_version_flag(self):
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(["--version"])
        assert exc.value.code == 0


class TestMainIntegration:
    def test_timeline_runs(self, make_repo, monkeypatch):
        monkeypatch.chdir(make_repo())
        assert main(["--no-color", "timeline"]) == 0

    def test_undo_no_destructive(self, make_repo, monkeypatch):
        monkeypatch.chdir(make_repo())
        assert main(["--no-color", "undo"]) == 1

    def test_branches_empty(self, make_repo, monkeypatch):
        monkeypatch.chdir(make_repo())
        assert main(["--no-color", "branches"]) == 0

    def test_files_runs(self, make_repo, monkeypatch):
        monkeypatch.chdir(make_repo())
        assert main(["--no-color", "files"]) == 0

    def test_not_a_repo(self, tmp_path: Path, monkeypatch):
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.chdir(empty)
        assert main(["--no-color", "timeline"]) == 2


class TestColor:
    def test_disable_removes_codes(self):
        Color.disable()
        assert Color.BOLD == "" and Color.RED == ""
