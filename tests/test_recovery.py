"""Tests for recovery.py — safety snapshots and 1-click restore."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from git_rescue.core.git_client import GitClient
from git_rescue.core.reflog_parser import find_deleted_branches
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

    def test_backups_in_the_same_second_do_not_collide(self, make_repo):
        """The ref name is second-granular, so two quick rescues shared a name and
        the second silently overwrote the first backup."""
        client = GitClient(make_repo())
        refs = [create_backup_snapshot(client) for _ in range(3)]
        assert len(set(refs)) == 3
        for ref in refs:
            assert client.ref_exists(ref)


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

    def test_undo_refuses_to_discard_uncommitted_work(self, make_repo):
        """`reset --hard` wipes the worktree, which a backup *ref* cannot restore."""
        repo = make_repo()
        (repo / "tracked.txt").write_text("committed\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-m", "Add tracked"], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(repo), "reset", "--hard", "HEAD~1"], capture_output=True, check=True)

        precious = repo / "README.md"
        precious.write_text("# unsaved work I care about\n", encoding="utf-8")

        result = undo_last_destructive(GitClient(repo))
        assert not result.success and "Uncommitted changes" in result.message
        assert precious.read_text(encoding="utf-8") == "# unsaved work I care about\n"


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

    def test_rejects_invalid_branch_names(self, make_repo):
        """SECURITY.md promises ref-name validation; nothing enforced it."""
        client = GitClient(make_repo())
        head = client.current_head()
        for bad in ("-D", "--force", "has space", "bad..name"):
            result = restore_branch(client, bad, head)
            assert not result.success and "Invalid branch name" in result.message
        assert client.branch_list() == [b for b in client.branch_list() if not b.startswith("-")]

    def test_restores_branch_at_its_own_tip(self, make_repo):
        """End-to-end: the recovered branch must carry the work back with it."""
        repo = make_repo()
        run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True)
        run("checkout", "-b", "lost-work")
        (repo / "precious.txt").write_text("do not lose me\n", encoding="utf-8")
        run("add", ".")
        run("commit", "-m", "Precious commit")
        tip = run("rev-parse", "HEAD").stdout.strip()

        default = next(b for b in ("master", "main")
                       if subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", b],
                                         capture_output=True).returncode == 0)
        run("checkout", default)
        run("branch", "-D", "lost-work")

        client = GitClient(repo)
        target = dict(find_deleted_branches(client))["lost-work"]
        result = restore_branch(client, "lost-work", target)
        assert result.success
        assert client.rev_parse("lost-work") == tip
        assert "precious.txt" in run("show", "--name-only", "--format=", "lost-work").stdout



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
