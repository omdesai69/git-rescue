"""Safe subprocess wrapper for Git plumbing commands.

All interactions with the git binary go through this module.
Arguments are always passed as lists to prevent shell injection.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List, Optional


class GitError(Exception):
    """Raised when a git command fails."""

class NotAGitRepo(GitError):
    """Raised when the current directory is not inside a git repository."""

class GitNotFound(GitError):
    """Raised when the git binary is not found on PATH."""


class GitClient:
    """Thin, safe wrapper around the git CLI."""

    SUBPROCESS_TIMEOUT = 30

    # %gD is the reflog selector. Combined with --date=iso it carries the date of the
    # reflog *event* — unlike %ci, which is the target commit's own committer date.
    REFLOG_FORMAT = "%H\x1e%gD\x1e%gs\x1e%ci"

    def __init__(self, repo_path: Optional[Path] = None):
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self._env = os.environ.copy()
        self._env["GIT_TERMINAL_PROMPT"] = "0"
        self._env.setdefault("LC_ALL", "C.UTF-8")
        self._validate_git_binary()
        self._validate_repo()

    def _validate_git_binary(self) -> None:
        try:
            subprocess.run(["git", "--version"], capture_output=True, timeout=5, check=True)
        except FileNotFoundError:
            raise GitNotFound("git is not installed or not on PATH. Install git from https://git-scm.com/")
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or b"").decode("utf-8", "replace").strip() if isinstance(exc.stderr, bytes) else str(exc.stderr or "").strip()
            raise GitNotFound(f"git is installed but failed to run (exit {exc.returncode}): {detail or 'no output'}")
        except subprocess.TimeoutExpired:
            raise GitNotFound("git did not respond within 5s. Check your git installation.")
        except OSError as exc:
            raise GitNotFound(f"Failed to execute git: {exc}")

    def _validate_repo(self) -> None:
        result = self.run(["rev-parse", "--is-inside-work-tree"], check=False)
        if result.returncode != 0:
            raise NotAGitRepo(f"Not a git repository: {self.repo_path}\nRun this command from inside a git repo.")

    @staticmethod
    def _out(result: subprocess.CompletedProcess) -> str:
        """stdout as text — empty string when output was not captured."""
        return result.stdout or ""

    def run(self, args: List[str], *, check: bool = True, capture: bool = True,
            timeout: Optional[int] = None) -> subprocess.CompletedProcess:
        """Execute a git command safely. Args passed as list — never shell=True."""
        cmd = ["git", "-C", str(self.repo_path)] + args
        effective_timeout = timeout or self.SUBPROCESS_TIMEOUT
        try:
            result = subprocess.run(
                cmd, capture_output=capture, text=True,
                timeout=effective_timeout,
                env=self._env,
                encoding="utf-8", errors="replace",
            )
        except subprocess.TimeoutExpired:
            raise GitError(f"Git command timed out after {effective_timeout}s: git {' '.join(args)}")
        except OSError as exc:
            raise GitError(f"Failed to run git: {exc}")

        if check and result.returncode != 0:
            stderr = (result.stderr or "").strip() or "unknown error"
            raise GitError(f"git {' '.join(args)}: {stderr}")
        return result

    def reflog(self, limit: int = 50) -> str:
        limit = max(0, int(limit))
        return self._out(self.run([
            "reflog", "show", "--date=iso", f"--format={self.REFLOG_FORMAT}", f"-n{limit}",
        ])).strip()

    def fsck_dangling(self) -> str:
        # --dangling (not --lost-found): reports the same objects on stdout without
        # writing copies into .git/lost-found/. Scanning must not mutate the repo.
        result = self.run(["fsck", "--no-reflogs", "--dangling", "--no-progress"], check=False)
        parts = [p for p in ((result.stdout or "").strip(), (result.stderr or "").strip()) if p]
        return "\n".join(parts)

    def cat_file_size(self, object_hash: str) -> int:
        return int(self._out(self.run(["cat-file", "-s", object_hash])).strip())

    def cat_file_content(self, object_hash: str) -> str:
        return self._out(self.run(["cat-file", "-p", object_hash]))

    def rev_parse(self, ref: str) -> str:
        return self._out(self.run(["rev-parse", ref])).strip()

    def is_valid_branch_name(self, name: str) -> bool:
        """Validate a branch name against git's own ref naming rules."""
        # git check-ref-format accepts leading dashes inside a path component, but
        # `git branch -foo` would parse as an option — reject those outright.
        if not name or name.startswith("-") or "\x00" in name:
            return False
        result = self.run(["check-ref-format", f"refs/heads/{name}"], check=False)
        return result.returncode == 0

    def create_ref(self, ref_name: str, commit_hash: str) -> None:
        self.run(["update-ref", ref_name, commit_hash])

    def ref_exists(self, ref_name: str) -> bool:
        return self.run(["rev-parse", "--verify", "--quiet", ref_name], check=False).returncode == 0

    def create_branch(self, name: str, commit_hash: str) -> None:
        self.run(["branch", "--", name, commit_hash])

    def reset_hard(self, target: str) -> None:
        self.run(["reset", "--hard", target])

    def diff_stat(self, ref_a: str, ref_b: str) -> str:
        return self._out(self.run(["diff", "--stat", ref_a, ref_b], check=False)).strip()

    def current_head(self) -> str:
        return self.rev_parse("HEAD")

    def is_worktree_dirty(self) -> bool:
        """True when tracked files have uncommitted changes (staged or not)."""
        return bool(self._out(self.run(["status", "--porcelain", "--untracked-files=no"], check=False)).strip())

    def branch_list(self) -> List[str]:
        result = self.run(["branch", "--format=%(refname:short)"], check=False)
        return [b for b in self._out(result).strip().split("\n") if b]

    def show_commit_summary(self, commit_hash: str) -> str:
        return self._out(self.run(["log", "--format=%h %s (%ci)", "-n1", commit_hash], check=False)).strip()
