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

    def test_uncaptured_output_does_not_crash_helpers(self, make_repo):
        """capture=False leaves stdout as None; helpers must tolerate it."""
        client = GitClient(make_repo())
        result = client.run(["rev-parse", "HEAD"], capture=False)
        assert client._out(result) == ""

    def test_timeout_message_reports_effective_timeout(self, make_repo, monkeypatch):
        """The message interpolated the `timeout` argument, printing "after Nones"."""
        client = GitClient(make_repo())

        def fake_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout"))

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(GitError) as exc:
            client.run(["status"])
        assert f"after {GitClient.SUBPROCESS_TIMEOUT}s" in str(exc.value)
        assert "None" not in str(exc.value)


class TestFsckIsReadOnly:
    def test_does_not_write_lost_found(self, make_repo):
        repo = make_repo()
        GitClient(repo).fsck_dangling()
        assert not (Path(repo) / ".git" / "lost-found").exists()


class TestBranchNameValidation:
    def test_accepts_ordinary_names(self, make_repo):
        client = GitClient(make_repo())
        for name in ("feature-x", "release/1.2", "fix_123"):
            assert client.is_valid_branch_name(name) is True

    def test_rejects_malformed_and_option_like_names(self, make_repo):
        client = GitClient(make_repo())
        for name in ("", "-D", "--force", "has space", "has..dots", "ends.lock", "back\\slash"):
            assert client.is_valid_branch_name(name) is False, name


class TestWorktreeState:
    def test_clean_repo_is_not_dirty(self, make_repo):
        assert GitClient(make_repo()).is_worktree_dirty() is False

    def test_modified_tracked_file_is_dirty(self, make_repo):
        repo = make_repo()
        (repo / "README.md").write_text("# Changed\n", encoding="utf-8")
        assert GitClient(repo).is_worktree_dirty() is True


class TestRefExists:
    def test_missing_ref(self, make_repo):
        assert GitClient(make_repo()).ref_exists("refs/rescue/nope") is False

    def test_present_ref(self, make_repo):
        client = GitClient(make_repo())
        client.create_ref("refs/rescue/yes", client.current_head())
        assert client.ref_exists("refs/rescue/yes") is True



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
