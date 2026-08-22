"""Safe subprocess wrapper for Git plumbing commands.

All interactions with the git binary go through this module.
Arguments are always passed as lists to prevent shell injection.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


class GitError(Exception):
    """Raised when a git command fails."""


class NotAGitRepo(GitError):
    """Raised when the current directory is not inside a git repository."""


class GitNotFound(GitError):
    """Raised when the git binary is not found on PATH."""


class GitClient:
    """Thin, safe wrapper around the git CLI.

    Every method builds a list-form command and runs it via subprocess.
    Never uses shell=True. Validates that we're inside a git repo on init.
    """

    SUBPROCESS_TIMEOUT = 30

    def __init__(self, repo_path: Optional[Path] = None):
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self._validate_git_binary()
        self._validate_repo()

    def _validate_git_binary(self) -> None:
        try:
            subprocess.run(
                ["git", "--version"],
                capture_output=True,
                timeout=5,
                check=True,
            )
        except FileNotFoundError:
            raise GitNotFound(
                "git is not installed or not on PATH. "
                "Install git from https://git-scm.com/"
            )

    def _validate_repo(self) -> None:
        result = self.run(
            ["rev-parse", "--is-inside-work-tree"],
            check=False,
        )
        if result.returncode != 0:
            raise NotAGitRepo(
                f"Not a git repository: {self.repo_path}\n"
                "Run this command from inside a git repo."
            )

    def run(
        self,
        args: List[str],
        *,
        check: bool = True,
        capture: bool = True,
        timeout: Optional[int] = None,
    ) -> subprocess.CompletedProcess:
        """Execute a git command safely.

        Args:
            args: Command arguments (without the leading 'git').
            check: Raise GitError on non-zero exit.
            capture: Capture stdout/stderr.
            timeout: Subprocess timeout in seconds.

        Returns:
            CompletedProcess with decoded text output.
        """
        cmd = ["git", "-C", str(self.repo_path)] + args
        timeout = timeout or self.SUBPROCESS_TIMEOUT

        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env.setdefault("LC_ALL", "C.UTF-8")

        try:
            result = subprocess.run(
                cmd,
                capture_output=capture,
                text=True,
                timeout=timeout,
                env=env,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            raise GitError(
                f"Git command timed out after {timeout}s: git {' '.join(args)}"
            )
        except OSError as exc:
            raise GitError(f"Failed to run git: {exc}")

        if check and result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else "unknown error"
            raise GitError(f"git {' '.join(args)}: {stderr}")

        return result

    def reflog(self, limit: int = 50) -> str:
        """Raw reflog output with hash, ref decorator, subject, and ISO date."""
        result = self.run([
            "reflog", "show",
            "--format=%H\x1e%gD\x1e%gs\x1e%ci",
            f"-n{limit}",
        ])
        return result.stdout.strip()

    def fsck_dangling(self) -> str:
        """Find dangling objects (blobs, commits, trees)."""
        result = self.run(
            ["fsck", "--no-reflogs", "--lost-found", "--no-progress"],
            check=False,
        )
        output = result.stdout.strip()
        if result.stderr:
            output += "\n" + result.stderr.strip()
        return output

    def cat_file_type(self, object_hash: str) -> str:
        """Return the type of a git object (commit, tree, blob, tag)."""
        result = self.run(["cat-file", "-t", object_hash])
        return result.stdout.strip()

    def cat_file_size(self, object_hash: str) -> int:
        """Return the size of a git object in bytes."""
        result = self.run(["cat-file", "-s", object_hash])
        return int(result.stdout.strip())

    def cat_file_content(self, object_hash: str) -> str:
        """Return the content of a git object as text."""
        result = self.run(["cat-file", "-p", object_hash])
        return result.stdout

    def rev_parse(self, ref: str) -> str:
        """Resolve a ref to a full SHA-1 hash."""
        result = self.run(["rev-parse", ref])
        return result.stdout.strip()

    def create_ref(self, ref_name: str, commit_hash: str) -> None:
        """Create or update a git ref (e.g., refs/rescue/backup-*)."""
        self.run(["update-ref", ref_name, commit_hash])

    def create_branch(self, name: str, commit_hash: str) -> None:
        """Create a branch pointing at the given commit."""
        self.run(["branch", name, commit_hash])

    def reset_hard(self, target: str) -> None:
        """Hard reset to a target ref/hash."""
        self.run(["reset", "--hard", target])

    def log_oneline(self, ref: str, count: int = 5) -> str:
        """Short log output for a ref."""
        result = self.run([
            "log", "--oneline", f"-n{count}", ref,
        ], check=False)
        return result.stdout.strip()

    def diff_stat(self, ref_a: str, ref_b: str) -> str:
        """Stat-format diff between two refs."""
        result = self.run(
            ["diff", "--stat", ref_a, ref_b],
            check=False,
        )
        return result.stdout.strip()

    def current_head(self) -> str:
        """Return the current HEAD hash."""
        return self.rev_parse("HEAD")

    def branch_list(self) -> List[str]:
        """Return list of local branch names."""
        result = self.run(
            ["branch", "--format=%(refname:short)"],
            check=False,
        )
        return [b for b in result.stdout.strip().splitlines() if b]

    def show_commit_summary(self, commit_hash: str) -> str:
        """One-line summary of a commit."""
        result = self.run([
            "log", "--format=%h %s (%ci)", "-n1", commit_hash,
        ], check=False)
        return result.stdout.strip()
