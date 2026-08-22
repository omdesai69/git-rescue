"""Tests for git_client.py — safe subprocess wrapper.

All tests use isolated temporary git repos via tmp_path.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from git_rescue.core.git_client import GitClient, GitError, NotAGitRepo


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
    readme = path / "README.md"
    readme.write_text("# Test repo\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(path), "add", "."],
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "Initial commit"],
        capture_output=True, check=True,
    )
    return path


class TestGitClientInit:
    def test_valid_repo(self, tmp_path: Path):
        repo = _init_repo(tmp_path / "repo")
        client = GitClient(repo)
        assert client.repo_path == repo

    def test_not_a_repo(self, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with pytest.raises(NotAGitRepo):
            GitClient(empty_dir)


class TestGitClientRun:
    def test_successful_command(self, tmp_path: Path):
        repo = _init_repo(tmp_path / "repo")
        client = GitClient(repo)
        result = client.run(["status"])
        assert result.returncode == 0

    def test_failed_command_raises(self, tmp_path: Path):
        repo = _init_repo(tmp_path / "repo")
        client = GitClient(repo)
        with pytest.raises(GitError):
            client.run(["log", "--oneline", "nonexistent-ref-abc123"])


class TestGitClientReflog:
    def test_reflog_has_entries(self, tmp_path: Path):
        repo = _init_repo(tmp_path / "repo")
        client = GitClient(repo)
        raw = client.reflog(limit=10)
        assert raw, "Reflog should have at least the initial commit"

    def test_reflog_limit(self, tmp_path: Path):
        repo = _init_repo(tmp_path / "repo")
        for i in range(5):
            (repo / f"file_{i}.txt").write_text(f"content {i}", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(repo), "add", "."],
                capture_output=True, check=True,
            )
            subprocess.run(
                ["git", "-C", str(repo), "commit", "-m", f"Commit {i}"],
                capture_output=True, check=True,
            )
        client = GitClient(repo)
        raw = client.reflog(limit=3)
        lines = [l for l in raw.split("\n") if l.strip()]
        assert len(lines) == 3


class TestGitClientRefs:
    def test_rev_parse_head(self, tmp_path: Path):
        repo = _init_repo(tmp_path / "repo")
        client = GitClient(repo)
        head = client.rev_parse("HEAD")
        assert len(head) == 40
        assert all(c in "0123456789abcdef" for c in head)

    def test_create_ref(self, tmp_path: Path):
        repo = _init_repo(tmp_path / "repo")
        client = GitClient(repo)
        head = client.current_head()
        client.create_ref("refs/rescue/test-backup", head)
        resolved = client.rev_parse("refs/rescue/test-backup")
        assert resolved == head

    def test_create_branch(self, tmp_path: Path):
        repo = _init_repo(tmp_path / "repo")
        client = GitClient(repo)
        head = client.current_head()
        client.create_branch("test-branch", head)
        branches = client.branch_list()
        assert "test-branch" in branches

    def test_branch_list(self, tmp_path: Path):
        repo = _init_repo(tmp_path / "repo")
        client = GitClient(repo)
        branches = client.branch_list()
        assert len(branches) >= 1
