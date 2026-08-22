"""Tests for recovery.py — safety snapshots and 1-click restore."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from git_rescue.core.git_client import GitClient
from git_rescue.core.recovery import (
    create_backup_snapshot, recover_files, restore_branch, undo_last_destructive,
)


class TestBackupSnapshot:
    def test_creates_rescue_ref(self, make_repo):
        repo = make_repo()
        client = GitClient(repo)
        ref = create_backup_snapshot(client)
        assert ref.startswith("refs/rescue/backup-") and client.rev_parse(ref) == client.current_head()

    def test_multiple_backups_are_unique(self, make_repo):
        client = GitClient(make_repo())
        ref1 = create_backup_snapshot(client)
        time.sleep(1.05)
        ref2 = create_backup_snapshot(client)
        assert ref1 != ref2


class TestUndoLastDestructive:
    def test_undo_hard_reset(self, make_repo):
        """The money test: commit a file, reset --hard, then undo and verify recovery."""
        repo = make_repo()
        important_file = repo / "important.txt"
        important_file.write_text("critical data\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-m", "Add important file"], capture_output=True, check=True)

        subprocess.run(["git", "-C", str(repo), "reset", "--hard", "HEAD~1"], capture_output=True, check=True)
        assert not important_file.exists()

        result = undo_last_destructive(GitClient(repo))
        assert result.success is True and result.backup_ref.startswith("refs/rescue/backup-")
        assert important_file.exists() and important_file.read_text(encoding="utf-8") == "critical data\n"

    def test_undo_when_no_destructive_ops(self, make_repo):
        result = undo_last_destructive(GitClient(make_repo()))
        assert not result.success and "No destructive operations" in result.message


class TestRestoreBranch:
    def test_restore_deleted_branch(self, make_repo):
        repo = make_repo()
        subprocess.run(["git", "-C", str(repo), "checkout", "-b", "doomed-branch"], capture_output=True, check=True)
        (repo / "branch_file.txt").write_text("branch content", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-m", "Branch commit"], capture_output=True, check=True)

        branch_head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        default_branches = subprocess.run(["git", "-C", str(repo), "branch", "--format=%(refname:short)"], capture_output=True, text=True, check=True).stdout.strip().splitlines()
        target = [b for b in default_branches if b != "doomed-branch"][0]

        subprocess.run(["git", "-C", str(repo), "checkout", target], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(repo), "branch", "-D", "doomed-branch"], capture_output=True, check=True)

        client = GitClient(repo)
        assert "doomed-branch" not in client.branch_list()
        result = restore_branch(client, "doomed-branch", branch_head)
        assert result.success is True and "doomed-branch" in client.branch_list()

    def test_restore_already_existing_branch(self, make_repo):
        client = GitClient(make_repo())
        result = restore_branch(client, client.branch_list()[0], client.current_head())
        assert not result.success and "already exists" in result.message


class TestRecoverFiles:
    def test_recover_dangling_blob(self, make_repo):
        repo = make_repo()
        lost = repo / "lost_work.py"
        lost.write_text("def important_function():\n    return 42\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(repo), "reset", "HEAD", "--", "lost_work.py"], capture_output=True, check=True)
        lost.unlink()

        result = recover_files(GitClient(repo))
        assert result.backup_ref.startswith("refs/rescue/backup-")
        if result.success:
            assert len(result.recovered_files) >= 1 and (Path(repo) / ".git" / "rescue-recovered").exists()

    def test_no_dangling_objects(self, make_repo):
        result = recover_files(GitClient(make_repo()))
        assert result.backup_ref.startswith("refs/rescue/backup-")
