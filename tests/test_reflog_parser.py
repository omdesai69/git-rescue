"""Tests for reflog_parser.py — semantic classification of reflog events."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from git_rescue.core.git_client import GitClient
from git_rescue.core.reflog_parser import (
    ReflogEntry,
    _classify,
    find_deleted_branches,
    find_last_destructive,
    find_pre_destructive_hash,
    parse_reflog,
)


class TestClassify:
    def test_hard_reset(self):
        cat, summary, destructive = _classify("reset: moving to HEAD~1")
        assert cat == "hard_reset"
        assert destructive is True
        assert "Hard Reset" in summary

    def test_checkout(self):
        cat, summary, destructive = _classify("checkout: moving from main to feature")
        assert cat == "checkout"
        assert destructive is False
        assert "main" in summary
        assert "feature" in summary

    def test_commit(self):
        cat, summary, destructive = _classify("commit: Add new feature")
        assert cat == "commit"
        assert destructive is False
        assert "Add new feature" in summary

    def test_initial_commit(self):
        cat, summary, destructive = _classify("commit (initial): Initial commit")
        assert cat == "commit"
        assert destructive is False

    def test_amend(self):
        cat, summary, destructive = _classify("commit (amend): Fix typo")
        assert cat == "commit_amend"
        assert destructive is False

    def test_rebase_finish(self):
        cat, summary, destructive = _classify(
            "rebase (finish): rebase abc123 onto def456"
        )
        assert cat == "rebase"
        assert destructive is False

    def test_merge(self):
        cat, summary, destructive = _classify("merge feature-branch: Fast-forward")
        assert cat == "merge"
        assert destructive is False

    def test_pull(self):
        cat, summary, destructive = _classify("pull: Fast-forward")
        assert cat == "pull"
        assert destructive is False

    def test_unknown_action(self):
        cat, summary, destructive = _classify("some-unknown-action: details")
        assert cat == "other"
        assert destructive is False

    def test_clone(self):
        cat, summary, destructive = _classify("clone: from https://github.com/test/repo")
        assert cat == "clone"
        assert destructive is False


class TestParseReflog:
    def test_parse_valid_entries(self):
        raw = (
            "abc1234567890123456789012345678901234567\x1eHEAD@{0}\x1e"
            "commit: Add feature\x1e2024-01-01 12:00:00 +0000\n"
            "def4567890123456789012345678901234567890\x1eHEAD@{1}\x1e"
            "reset: moving to HEAD~1\x1e2024-01-01 11:00:00 +0000\n"
        )
        entries = parse_reflog(raw)
        assert len(entries) == 2
        assert entries[0].category == "commit"
        assert entries[1].category == "hard_reset"
        assert entries[1].is_destructive is True

    def test_empty_input(self):
        assert parse_reflog("") == []

    def test_malformed_lines_skipped(self):
        raw = "incomplete line without separators\n"
        entries = parse_reflog(raw)
        assert len(entries) == 0


class TestFindDestructive:
    def _make_entries(self) -> list[ReflogEntry]:
        return [
            ReflogEntry("aaa", "HEAD@{0}", "commit: normal", "2024-01-03",
                        "commit", "Commit", False),
            ReflogEntry("bbb", "HEAD@{1}", "reset: moving to HEAD~1", "2024-01-02",
                        "hard_reset", "Hard Reset", True),
            ReflogEntry("ccc", "HEAD@{2}", "commit: old", "2024-01-01",
                        "commit", "Old commit", False),
        ]

    def test_find_last_destructive(self):
        entries = self._make_entries()
        result = find_last_destructive(entries)
        assert result is not None
        assert result.hash == "bbb"

    def test_find_pre_destructive_hash(self):
        entries = self._make_entries()
        result = find_pre_destructive_hash(entries)
        assert result is not None
        destructive, pre_hash = result
        assert destructive.hash == "bbb"
        assert pre_hash == "ccc"

    def test_no_destructive_returns_none(self):
        entries = [
            ReflogEntry("aaa", "HEAD@{0}", "commit: normal", "2024-01-01",
                        "commit", "Commit", False),
        ]
        assert find_last_destructive(entries) is None
        assert find_pre_destructive_hash(entries) is None


class TestFindDeletedBranches:
    def test_detects_deleted_branch(self, tmp_path: Path):
        repo = tmp_path / "repo"
        subprocess.run(["git", "init", str(repo)], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "test@test.com"],
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "Test"],
            capture_output=True, check=True,
        )

        (repo / "file.txt").write_text("content", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "Initial"],
            capture_output=True, check=True,
        )

        subprocess.run(
            ["git", "-C", str(repo), "checkout", "-b", "feature-x"],
            capture_output=True, check=True,
        )
        (repo / "feature.txt").write_text("feature", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "Feature commit"],
            capture_output=True, check=True,
        )

        subprocess.run(
            ["git", "-C", str(repo), "checkout", "master"],
            capture_output=True, check=False,
        )
        subprocess.run(
            ["git", "-C", str(repo), "checkout", "main"],
            capture_output=True, check=False,
        )
        subprocess.run(
            ["git", "-C", str(repo), "branch", "-D", "feature-x"],
            capture_output=True, check=True,
        )

        client = GitClient(repo)
        deleted = find_deleted_branches(client)
        branch_names = [name for name, _ in deleted]
        assert "feature-x" in branch_names
