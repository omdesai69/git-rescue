"""Safety snapshotting and 1-click restore engine.

Every mutating operation MUST go through this module to ensure
the safety-first invariant: a backup ref is always created before
any state change.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from git_rescue.core.git_client import GitClient, GitError
from git_rescue.core.reflog_parser import (
    ReflogEntry,
    find_deleted_branches,
    find_pre_destructive_hash,
    parse_reflog,
)
from git_rescue.core.blob_scanner import recover_blobs


BACKUP_REF_PREFIX = "refs/rescue/backup"


@dataclass
class UndoResult:
    """Result of an undo operation."""
    success: bool
    message: str
    backup_ref: str
    destructive_entry: Optional[ReflogEntry] = None
    restored_to: str = ""
    diff_summary: str = ""


@dataclass
class BranchRestoreResult:
    """Result of a branch restore operation."""
    success: bool
    message: str
    backup_ref: str
    branch_name: str = ""
    commit_hash: str = ""
    commit_summary: str = ""


@dataclass
class FileRecoveryResult:
    """Result of a file recovery operation."""
    success: bool
    message: str
    backup_ref: str
    recovered_files: List[dict] = None

    def __post_init__(self):
        if self.recovered_files is None:
            self.recovered_files = []


def create_backup_snapshot(client: GitClient) -> str:
    """Create a safety backup ref pointing to current HEAD.

    Returns the ref name (e.g., refs/rescue/backup-1719849600).
    This is the core safety invariant — called before every mutation.
    """
    try:
        head = client.current_head()
    except GitError:
        raise GitError(
            "Cannot create backup: no commits in this repository yet."
        )

    timestamp = int(time.time())
    ref_name = f"{BACKUP_REF_PREFIX}-{timestamp}"
    client.create_ref(ref_name, head)
    return ref_name


def undo_last_destructive(client: GitClient) -> UndoResult:
    """Detect and revert the last destructive git operation.

    1. Creates a backup snapshot of current state
    2. Finds the most recent destructive action in reflog
    3. Resets to the state before that action
    4. Reports what was recovered
    """
    backup_ref = create_backup_snapshot(client)

    raw = client.reflog(limit=50)
    entries = parse_reflog(raw)

    result = find_pre_destructive_hash(entries)
    if result is None:
        return UndoResult(
            success=False,
            message="No destructive operations found in recent reflog history.",
            backup_ref=backup_ref,
        )

    destructive_entry, pre_hash = result

    current_head = client.current_head()
    diff_summary = ""
    try:
        diff_summary = client.diff_stat(current_head, pre_hash)
    except GitError:
        pass

    client.reset_hard(pre_hash)

    return UndoResult(
        success=True,
        message=f"Reverted destructive operation: {destructive_entry.human_summary}",
        backup_ref=backup_ref,
        destructive_entry=destructive_entry,
        restored_to=pre_hash,
        diff_summary=diff_summary,
    )


def list_deleted_branches(client: GitClient) -> List[Tuple[str, str, str]]:
    """Find deleted branches and their commit summaries.

    Returns list of (branch_name, commit_hash, commit_summary).
    """
    deleted = find_deleted_branches(client)
    results = []

    for name, hash_val in deleted:
        try:
            summary = client.show_commit_summary(hash_val)
        except GitError:
            summary = hash_val[:8]
        results.append((name, hash_val, summary))

    return results


def restore_branch(
    client: GitClient,
    branch_name: str,
    commit_hash: str,
) -> BranchRestoreResult:
    """Restore a deleted branch at a specific commit.

    1. Creates a backup snapshot
    2. Creates the branch
    3. Reports success
    """
    backup_ref = create_backup_snapshot(client)

    existing = client.branch_list()
    if branch_name in existing:
        return BranchRestoreResult(
            success=False,
            message=f"Branch '{branch_name}' already exists.",
            backup_ref=backup_ref,
        )

    try:
        client.create_branch(branch_name, commit_hash)
    except GitError as exc:
        return BranchRestoreResult(
            success=False,
            message=f"Failed to restore branch: {exc}",
            backup_ref=backup_ref,
        )

    try:
        summary = client.show_commit_summary(commit_hash)
    except GitError:
        summary = commit_hash[:8]

    return BranchRestoreResult(
        success=True,
        message=f"Restored branch '{branch_name}'",
        backup_ref=backup_ref,
        branch_name=branch_name,
        commit_hash=commit_hash,
        commit_summary=summary,
    )


def recover_files(client: GitClient) -> FileRecoveryResult:
    """Recover dangling blobs to .git/rescue-recovered/.

    1. Creates a backup snapshot
    2. Scans for dangling objects
    3. Writes recoverable blobs to disk
    4. Reports results
    """
    backup_ref = create_backup_snapshot(client)

    records = recover_blobs(client)

    if not records:
        return FileRecoveryResult(
            success=False,
            message="No recoverable files found in dangling objects.",
            backup_ref=backup_ref,
        )

    return FileRecoveryResult(
        success=True,
        message=f"Recovered {len(records)} file(s) to .git/rescue-recovered/",
        backup_ref=backup_ref,
        recovered_files=records,
    )
