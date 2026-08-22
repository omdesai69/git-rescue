"""Tests for git_client.py — safe subprocess wrapper."""

from __future__ import annotations

import subprocess
from pathlib import Path
import pytest
from git_rescue.core.git_client import GitClient, GitError, NotAGitRepo


class TestGitClientInit:
    def test_valid_repo(self, make_repo):
        repo = make_repo()
        assert GitClient(repo).repo_path == repo

    def test_not_a_repo(self, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with pytest.raises(NotAGitRepo):
            GitClient(empty_dir)


class TestGitClientRun:
    def test_successful_command(self, make_repo):
        assert GitClient(make_repo()).run(["status"]).returncode == 0

    def test_failed_command_raises(self, make_repo):
        with pytest.raises(GitError):
            GitClient(make_repo()).run(["log", "--oneline", "nonexistent-ref-abc123"])


class TestGitClientReflog:
    def test_reflog_has_entries(self, make_repo):
        assert GitClient(make_repo()).reflog(limit=10)

    def test_reflog_limit(self, make_repo):
        repo = make_repo()
        for i in range(5):
            (repo / f"file_{i}.txt").write_text(f"content {i}", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True, check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", f"Commit {i}"], capture_output=True, check=True)
        raw = GitClient(repo).reflog(limit=3)
        assert len([l for l in raw.split("\n") if l.strip()]) == 3


class TestGitClientRefs:
    def test_rev_parse_head(self, make_repo):
        head = GitClient(make_repo()).rev_parse("HEAD")
        assert len(head) == 40 and all(c in "0123456789abcdef" for c in head)

    def test_create_ref(self, make_repo):
        client = GitClient(make_repo())
        head = client.current_head()
        client.create_ref("refs/rescue/test-backup", head)
        assert client.rev_parse("refs/rescue/test-backup") == head

    def test_create_branch(self, make_repo):
        client = GitClient(make_repo())
        client.create_branch("test-branch", client.current_head())
        assert "test-branch" in client.branch_list()

    def test_branch_list(self, make_repo):
        assert len(GitClient(make_repo()).branch_list()) >= 1
