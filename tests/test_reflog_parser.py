"""Tests for reflog_parser.py — semantic classification of reflog events."""

from __future__ import annotations

import subprocess
from pathlib import Path
from git_rescue.core.git_client import GitClient
from git_rescue.core.reflog_parser import (
    ReflogEntry, _classify, find_deleted_branches,
    find_last_destructive, find_pre_destructive_hash, parse_reflog,
)


class TestClassify:
    def test_hard_reset(self):
        cat, summary, destructive = _classify("reset: moving to HEAD~1")
        assert cat == "hard_reset" and destructive is True and "Hard Reset" in summary

    def test_checkout(self):
        cat, summary, destructive = _classify("checkout: moving from main to feature")
        assert cat == "checkout" and not destructive and "main" in summary and "feature" in summary

    def test_commit(self):
        cat, summary, _ = _classify("commit: Add new feature")
        assert cat == "commit" and "Add new feature" in summary

    def test_initial_commit(self):
        assert _classify("commit (initial): Initial commit")[0] == "commit"

    def test_amend(self):
        assert _classify("commit (amend): Fix typo")[0] == "commit_amend"

    def test_rebase_finish(self):
        assert _classify("rebase (finish): rebase abc123 onto def456")[0] == "rebase"

    def test_merge(self):
        assert _classify("merge feature-branch: Fast-forward")[0] == "merge"

    def test_pull(self):
        assert _classify("pull: Fast-forward")[0] == "pull"

    def test_unknown_action(self):
        assert _classify("some-unknown-action: details")[0] == "other"

    def test_clone(self):
        assert _classify("clone: from https://github.com/test/repo")[0] == "clone"


class TestParseReflog:
    def test_parse_valid_entries(self):
        raw = ("abc1234567890123456789012345678901234567\x1eHEAD@{0}\x1ecommit: Add feature\x1e2024-01-01 12:00:00 +0000\n"
               "def4567890123456789012345678901234567890\x1eHEAD@{1}\x1ereset: moving to HEAD~1\x1e2024-01-01 11:00:00 +0000\n")
        entries = parse_reflog(raw)
        assert len(entries) == 2 and entries[0].category == "commit" and entries[1].is_destructive

    def test_empty_input(self):
        assert parse_reflog("") == []

    def test_malformed_lines_skipped(self):
        assert parse_reflog("incomplete line without separators\n") == []

    def test_timestamp_prefers_reflog_event_date(self):
        """`%ci` is the target commit's date. Checking out an old commit today must
        not be timestamped years ago on the timeline."""
        raw = ("abc1234567890123456789012345678901234567\x1e"
               "HEAD@{2026-08-23 17:00:53 +0530}\x1e"
               "checkout: moving from main to old-thing\x1e"
               "2020-01-01 10:00:00 +0000\n")
        entry = parse_reflog(raw)[0]
        assert entry.timestamp == "2026-08-23 17:00:53 +0530"
        assert entry.commit_timestamp == "2020-01-01 10:00:00 +0000"

    def test_timestamp_falls_back_to_commit_date(self):
        """Index-form selectors carry no date; the commit date is the only option."""
        raw = ("abc1234567890123456789012345678901234567\x1eHEAD@{0}\x1e"
               "commit: x\x1e2024-01-01 12:00:00 +0000\n")
        assert parse_reflog(raw)[0].timestamp == "2024-01-01 12:00:00 +0000"



class TestFindDestructive:
    def _make_entries(self) -> list[ReflogEntry]:
        return [
            ReflogEntry("aaa", "HEAD@{0}", "commit: normal", "2024-01-03", "commit", "Commit", False),
            ReflogEntry("bbb", "HEAD@{1}", "reset: moving to HEAD~1", "2024-01-02", "hard_reset", "Hard Reset", True),
            ReflogEntry("ccc", "HEAD@{2}", "commit: old", "2024-01-01", "commit", "Old commit", False),
        ]

    def test_find_last_destructive(self):
        assert find_last_destructive(self._make_entries()).hash == "bbb"

    def test_find_pre_destructive_hash(self):
        dest, pre_hash = find_pre_destructive_hash(self._make_entries())
        assert dest.hash == "bbb" and pre_hash == "ccc"

    def test_no_destructive_returns_none(self):
        entries = [ReflogEntry("aaa", "HEAD@{0}", "commit: normal", "2024-01-01", "commit", "Commit", False)]
        assert find_last_destructive(entries) is None and find_pre_destructive_hash(entries) is None


class TestFindDeletedBranches:
    def test_detects_deleted_branch(self, make_repo):
        repo = make_repo()
        subprocess.run(["git", "-C", str(repo), "checkout", "-b", "feature-x"], capture_output=True, check=True)
        (repo / "feature.txt").write_text("feature", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-m", "Feature commit"], capture_output=True, check=True)
        for b in ("master", "main"):
            subprocess.run(["git", "-C", str(repo), "checkout", b], capture_output=True, check=False)
        subprocess.run(["git", "-C", str(repo), "branch", "-D", "feature-x"], capture_output=True, check=True)

        deleted = find_deleted_branches(GitClient(repo))
        assert "feature-x" in [name for name, _ in deleted]

    def test_reports_the_branch_own_tip_not_the_checkout_target(self, make_repo):
        """A reflog entry's hash is HEAD *after* the op.

        For `checkout: moving from feature to main` that hash is main's tip, so
        attributing it to `feature` restored the branch at the wrong commit and
        silently dropped every commit made on it.
        """
        repo = make_repo()
        run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True)
        base = run("rev-parse", "HEAD").stdout.strip()

        run("checkout", "-b", "feature-y")
        (repo / "work.txt").write_text("the work", encoding="utf-8")
        run("add", ".")
        run("commit", "-m", "Work that must survive")
        feature_tip = run("rev-parse", "HEAD").stdout.strip()
        assert feature_tip != base

        default = next(b for b in ("master", "main")
                       if subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", b],
                                         capture_output=True).returncode == 0)
        run("checkout", default)
        run("branch", "-D", "feature-y")

        found = dict(find_deleted_branches(GitClient(repo)))
        assert found.get("feature-y") == feature_tip, (
            f"expected feature-y at its own tip {feature_tip[:8]}, got {str(found.get('feature-y'))[:8]}"
        )

    def test_reflog_selectors_are_never_reported_as_branches(self, make_repo):
        """Names were once derived from the reflog selector, yielding `HEAD@{3}`."""
        repo = make_repo()
        subprocess.run(["git", "-C", str(repo), "checkout", "-b", "tmp-branch"], capture_output=True, check=True)
        for b in ("master", "main"):
            subprocess.run(["git", "-C", str(repo), "checkout", b], capture_output=True, check=False)
        subprocess.run(["git", "-C", str(repo), "branch", "-D", "tmp-branch"], capture_output=True, check=True)

        for name, _ in find_deleted_branches(GitClient(repo)):
            assert "@{" not in name and not name.startswith("refs/")

