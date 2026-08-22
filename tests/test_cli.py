"""Tests for cli.py — subcommand invocation and argument parsing."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from git_rescue.cli import build_parser, main, Color


def _init_repo(path: Path) -> Path:
    """Initialize a git repo with an initial commit."""
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@test.com"],
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test"],
        capture_output=True, check=True,
    )
    (path / "README.md").write_text("# Test\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "Initial commit"],
        capture_output=True, check=True,
    )
    return path


class TestParser:
    def test_default_command(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.command is None

    def test_timeline_command(self):
        parser = build_parser()
        args = parser.parse_args(["timeline"])
        assert args.command == "timeline"

    def test_timeline_with_limit(self):
        parser = build_parser()
        args = parser.parse_args(["timeline", "-n", "30"])
        assert args.command == "timeline"
        assert args.limit == 30

    def test_undo_command(self):
        parser = build_parser()
        args = parser.parse_args(["undo"])
        assert args.command == "undo"

    def test_branches_command(self):
        parser = build_parser()
        args = parser.parse_args(["branches"])
        assert args.command == "branches"
        assert args.restore is None

    def test_branches_restore(self):
        parser = build_parser()
        args = parser.parse_args(["branches", "--restore", "my-branch"])
        assert args.command == "branches"
        assert args.restore == "my-branch"

    def test_files_command(self):
        parser = build_parser()
        args = parser.parse_args(["files"])
        assert args.command == "files"

    def test_no_color_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--no-color"])
        assert args.no_color is True

    def test_version_flag(self):
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0


class TestMainIntegration:
    def test_timeline_runs(self, tmp_path: Path, monkeypatch):
        repo = _init_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)
        exit_code = main(["--no-color", "timeline"])
        assert exit_code == 0

    def test_undo_no_destructive(self, tmp_path: Path, monkeypatch):
        repo = _init_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)
        exit_code = main(["--no-color", "undo"])
        assert exit_code == 1

    def test_branches_empty(self, tmp_path: Path, monkeypatch):
        repo = _init_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)
        exit_code = main(["--no-color", "branches"])
        assert exit_code == 0

    def test_files_runs(self, tmp_path: Path, monkeypatch):
        repo = _init_repo(tmp_path / "repo")
        monkeypatch.chdir(repo)
        exit_code = main(["--no-color", "files"])
        assert exit_code == 0

    def test_not_a_repo(self, tmp_path: Path, monkeypatch):
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.chdir(empty)
        exit_code = main(["--no-color", "timeline"])
        assert exit_code == 2


class TestColor:
    def test_disable_removes_codes(self):
        class TestColor(Color):
            pass

        TestColor.BOLD = "\033[1m"
        TestColor.RED = "\033[31m"
        TestColor.disable()
        assert TestColor.BOLD == ""
        assert TestColor.RED == ""
