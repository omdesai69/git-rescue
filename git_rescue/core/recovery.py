"""Safety snapshotting and 1-click restore engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
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
    success: bool
    message: str
    backup_ref: str
    destructive_entry: Optional[ReflogEntry] = None
    restored_to: str = ""
    diff_summary: str = ""


@dataclass
class BranchRestoreResult:
    success: bool
    message: str
    backup_ref: str
    branch_name: str = ""
    commit_hash: str = ""
    commit_summary: str = ""


@dataclass
class FileRecoveryResult:
    success: bool
    message: str
    backup_ref: str
    recovered_files: List[dict] = field(default_factory=list)


def create_backup_snapshot(client: GitClient) -> str:
    """Create a safety backup ref pointing to current HEAD before mutations."""
    try:
        head = client.current_head()
    except GitError:
        raise GitError("Cannot create backup: no commits in this repository yet.")
    base = f"{BACKUP_REF_PREFIX}-{int(time.time())}"
    ref_name, suffix = base, 1
    # Two rescues inside the same second must not overwrite each other's backup.
    while client.ref_exists(ref_name):
        ref_name = f"{base}.{suffix}"
        suffix += 1
    client.create_ref(ref_name, head)
    return ref_name


def undo_last_destructive(client: GitClient) -> UndoResult:
    """Detect and revert the last destructive git operation."""
    backup_ref = create_backup_snapshot(client)
    # `reset --hard` below discards uncommitted work, which a backup ref (a commit
    # pointer) cannot restore. Refuse rather than silently destroy it.
    if client.is_worktree_dirty():
        return UndoResult(
            False,
            "Uncommitted changes present — `undo` would discard them.\n"
            "     Commit or stash them first (`git stash`), then run `git-rescue undo` again.",
            backup_ref,
        )

    entries = parse_reflog(client.reflog(limit=50))
    match = find_pre_destructive_hash(entries)
    if not match:
        return UndoResult(False, "No destructive operations found in recent reflog history.", backup_ref)

    destructive_entry, pre_hash = match
    try:
        diff_summary = client.diff_stat(client.current_head(), pre_hash)
    except GitError:
        diff_summary = ""

    client.reset_hard(pre_hash)
    return UndoResult(
        True, f"Reverted destructive operation: {destructive_entry.human_summary}",
        backup_ref, destructive_entry=destructive_entry, restored_to=pre_hash, diff_summary=diff_summary,
    )


def list_deleted_branches(client: GitClient) -> List[Tuple[str, str, str]]:
    """Find deleted branches and their commit summaries."""
    results = []
    for name, hash_val in find_deleted_branches(client):
        try:
            summary = client.show_commit_summary(hash_val)
        except GitError:
            summary = hash_val[:8]
        results.append((name, hash_val, summary))
    return results


def restore_branch(client: GitClient, branch_name: str, commit_hash: str) -> BranchRestoreResult:
    """Restore a deleted branch at a specific commit."""
    backup_ref = create_backup_snapshot(client)
    if not client.is_valid_branch_name(branch_name):
        return BranchRestoreResult(False, f"Invalid branch name: {branch_name!r}", backup_ref)
    if branch_name in set(client.branch_list()):
        return BranchRestoreResult(False, f"Branch '{branch_name}' already exists.", backup_ref)

    try:
        client.create_branch(branch_name, commit_hash)
    except GitError as exc:
        return BranchRestoreResult(False, f"Failed to restore branch: {exc}", backup_ref)

    try:
        summary = client.show_commit_summary(commit_hash)
    except GitError:
        summary = commit_hash[:8]

    return BranchRestoreResult(
        True, f"Restored branch '{branch_name}'", backup_ref,
        branch_name=branch_name, commit_hash=commit_hash, commit_summary=summary,
    )


def recover_files(client: GitClient) -> FileRecoveryResult:
    """Recover dangling blobs to .git/rescue-recovered/."""
    backup_ref = create_backup_snapshot(client)
    records = recover_blobs(client)
    if not records:
        return FileRecoveryResult(False, "No recoverable files found in dangling objects.", backup_ref)
    return FileRecoveryResult(
        True, f"Recovered {len(records)} file(s) to .git/rescue-recovered/", backup_ref, records,
    )
