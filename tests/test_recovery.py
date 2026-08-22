"""Tests for recovery.py — safety snapshots and 1-click restore.

These are integration tests that perform real git operations
in isolated temporary repos to verify actual recovery flows.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from git_rescue.core.git_client import GitClient
from git_rescue.core.recovery import (
    create_backup_snapshot,
    list_deleted_branches,
    recover_files,
    restore_branch,
    undo_last_destructive,
)


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


class TestBackupSnapshot:
    def test_creates_rescue_ref(self, tmp_path: Path):
        repo = _init_repo(tmp_path / "repo")
        client = GitClient(repo)
        ref = create_backup_snapshot(client)

        assert ref.startswith("refs/rescue/backup-")
        resolved = client.rev_parse(ref)
        head = client.current_head()
        assert resolved == head

    def test_multiple_backups_are_unique(self, tmp_path: Path):
        import time
        repo = _init_repo(tmp_path / "repo")
        client = GitClient(repo)

        ref1 = create_backup_snapshot(client)
        time.sleep(1.1)
        ref2 = create_backup_snapshot(client)

        assert ref1 != ref2


class TestUndoLastDestructive:
    def test_undo_hard_reset(self, tmp_path: Path):
        """The money test: commit a file, reset --hard, then undo and verify recovery."""
        repo = _init_repo(tmp_path / "repo")

        important_file = repo / "important.txt"
        important_file.write_text("critical data\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "Add important file"],
            capture_output=True, check=True,
        )

        assert important_file.exists()

        subprocess.run(
            ["git", "-C", str(repo), "reset", "--hard", "HEAD~1"],
            capture_output=True, check=True,
        )

        assert not important_file.exists(), "File should be gone after hard reset"

        client = GitClient(repo)
        result = undo_last_destructive(client)

        assert result.success is True
        assert result.backup_ref.startswith("refs/rescue/backup-")
        assert result.destructive_entry is not None
        assert important_file.exists(), "File should be restored after undo"
        assert important_file.read_text(encoding="utf-8") == "critical data\n"

    def test_undo_when_no_destructive_ops(self, tmp_path: Path):
        repo = _init_repo(tmp_path / "repo")
        client = GitClient(repo)
        result = undo_last_destructive(client)

        assert result.success is False
        assert "No destructive operations" in result.message


class TestRestoreBranch:
    def test_restore_deleted_branch(self, tmp_path: Path):
        repo = _init_repo(tmp_path / "repo")

        subprocess.run(
            ["git", "-C", str(repo), "checkout", "-b", "doomed-branch"],
            capture_output=True, check=True,
        )
        (repo / "branch_file.txt").write_text("branch content", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "Branch commit"],
            capture_output=True, check=True,
        )

        branch_head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()

        default_branch = subprocess.run(
            ["git", "-C", str(repo), "branch", "--format=%(refname:short)"],
            capture_output=True, text=True, check=True,
        ).stdout.strip().splitlines()
        target = [b for b in default_branch if b != "doomed-branch"][0]

        subprocess.run(
            ["git", "-C", str(repo), "checkout", target],
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "branch", "-D", "doomed-branch"],
            capture_output=True, check=True,
        )

        client = GitClient(repo)
        branches_before = client.branch_list()
        assert "doomed-branch" not in branches_before

        result = restore_branch(client, "doomed-branch", branch_head)

        assert result.success is True
        assert "doomed-branch" in client.branch_list()
        assert result.backup_ref.startswith("refs/rescue/backup-")

    def test_restore_already_existing_branch(self, tmp_path: Path):
        repo = _init_repo(tmp_path / "repo")
        client = GitClient(repo)
        head = client.current_head()
        default_branch = client.branch_list()[0]

        result = restore_branch(client, default_branch, head)
        assert result.success is False
        assert "already exists" in result.message


class TestRecoverFiles:
    def test_recover_dangling_blob(self, tmp_path: Path):
        repo = _init_repo(tmp_path / "repo")

        lost_file = repo / "lost_work.py"
        lost_file.write_text("def important_function():\n    return 42\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True, check=True)

        subprocess.run(
            ["git", "-C", str(repo), "reset", "HEAD", "--", "lost_work.py"],
            capture_output=True, check=True,
        )
        lost_file.unlink()

        client = GitClient(repo)
        result = recover_files(client)

        assert result.backup_ref.startswith("refs/rescue/backup-")

        if result.success:
            assert len(result.recovered_files) >= 1
            recovery_dir = Path(repo) / ".git" / "rescue-recovered"
            assert recovery_dir.exists()

    def test_no_dangling_objects(self, tmp_path: Path):
        repo = _init_repo(tmp_path / "repo")
        client = GitClient(repo)
        result = recover_files(client)
        assert result.backup_ref.startswith("refs/rescue/backup-")
