"""Tests for cli.py — subcommand invocation and argument parsing."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
import pytest
import git_rescue
from git_rescue.cli import (
    Color, _box, _display_width, _header, _strip_ansi, build_parser, main,
)

PROJECT_ROOT = str(Path(git_rescue.__file__).resolve().parent.parent)


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

    @pytest.mark.parametrize("argv", [
        ["--no-color", "timeline"],
        ["timeline", "--no-color"],
        ["--no-color", "branches"],
        ["branches", "--no-color"],
        ["files", "--no-color"],
        ["undo", "--no-color"],
    ])
    def test_no_color_accepted_on_either_side_of_subcommand(self, argv):
        """`git-rescue timeline --no-color` was rejected as an unknown argument;
        moving the flag to a parent parser must not let the subparser default
        overwrite a value already set at the top level."""
        args = build_parser().parse_args(argv)
        assert getattr(args, "no_color", False) is True

    def test_no_color_defaults_off(self):
        assert getattr(build_parser().parse_args(["timeline"]), "no_color", False) is False

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

    def test_enable_restores_codes(self):
        Color.disable()
        Color.enable()
        assert Color.BOLD == "\033[1m" and Color.CYAN == "\033[36m"
        Color.disable()


class TestNoColorIsComplete:
    """`Color.disable()` only zeroed the class attributes. Escape codes captured at
    import time — in TIMELINE_STYLES and in `_box`'s default argument — kept being
    emitted, and with RESET blanked they were never even terminated."""

    def _run_capture(self, capsys, repo, monkeypatch, argv):
        monkeypatch.chdir(repo)
        Color.enable()
        assert main(argv) is not None
        out = capsys.readouterr()
        return out.out + out.err

    def test_timeline_emits_no_escape_codes(self, make_repo, monkeypatch, capsys):
        text = self._run_capture(capsys, make_repo(), monkeypatch, ["--no-color", "timeline"])
        assert "\033" not in text

    def test_timeline_with_trailing_flag_emits_no_escape_codes(self, make_repo, monkeypatch, capsys):
        text = self._run_capture(capsys, make_repo(), monkeypatch, ["timeline", "--no-color"])
        assert "\033" not in text

    def test_all_commands_emit_no_escape_codes(self, make_repo, monkeypatch, capsys):
        repo = make_repo()
        for cmd in ("timeline", "branches", "files", "undo"):
            text = self._run_capture(capsys, repo, monkeypatch, ["--no-color", cmd])
            assert "\033" not in text, cmd

    def test_no_color_env_var_is_honored(self, make_repo, monkeypatch, capsys):
        monkeypatch.setenv("NO_COLOR", "1")
        text = self._run_capture(capsys, make_repo(), monkeypatch, ["timeline"])
        assert "\033" not in text


class TestBoxRendering:
    def test_borders_align_with_emoji(self):
        """Emoji are two columns wide but one code point, so len()-based padding
        pushed the right border out of line on any row containing one."""
        Color.disable()
        rendered = _box("🛟  Recovery Complete", [
            "  Restored to: abc123def456",
            "  ⚠️  a warning row",
            "  plain ascii row",
        ])
        widths = {_display_width(line) for line in rendered.splitlines()}
        assert len(widths) == 1, f"ragged box widths: {widths}"

    def test_header_frame_survives_a_longer_version(self, monkeypatch):
        Color.disable()
        monkeypatch.setattr("git_rescue.cli.__version__", "10.20.30-rc1")
        # Keep leading indentation: stripping it would skew the first line.
        widths = {_display_width(l) for l in _header().splitlines() if l.strip()}
        assert len(widths) == 1, f"ragged header widths: {widths}"

    def test_box_never_narrower_than_minimum(self):
        Color.disable()
        assert _display_width(_box("x", ["y"]).splitlines()[0]) == 40

    def test_strip_ansi_removes_sgr_sequences(self):
        assert _strip_ansi("\033[31mred\033[0m") == "red"


class TestModuleEntrypoint:
    """`python -m git_rescue` discarded main()'s return value and always exited 0."""

    def _run(self, cwd, *args):
        return subprocess.run(
            [sys.executable, "-m", "git_rescue", "--no-color", *args],
            cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONPATH": PROJECT_ROOT, "PYTHONIOENCODING": "utf-8"},
        )

    def test_propagates_not_a_repo_exit_code(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert self._run(empty, "timeline").returncode == 2

    def test_propagates_failure_exit_code(self, make_repo):
        assert self._run(make_repo(), "undo").returncode == 1

    def test_propagates_success_exit_code(self, make_repo):
        assert self._run(make_repo(), "timeline").returncode == 0

