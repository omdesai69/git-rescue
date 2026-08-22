"""Semantic parser translating reflog entries into human-readable events.

Parses `git reflog` output and classifies each entry into a category
(hard reset, branch switch, commit, rebase, etc.) with human-friendly summaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from git_rescue.core.git_client import GitClient

FIELD_SEP = "\x1e"


@dataclass
class ReflogEntry:
    """A single parsed reflog event."""
    hash: str
    ref: str
    action: str
    timestamp: str
    category: str
    human_summary: str
    is_destructive: bool = False


_PATTERNS: List[Tuple[re.Pattern, str, str, bool]] = [
    (
        re.compile(r"reset: moving to (.+)"),
        "hard_reset",
        "⚠️  Hard Reset → {0}",
        True,
    ),
    (
        re.compile(r"checkout: moving from (.+) to (.+)"),
        "checkout",
        "🔀 Switched from {0} → {1}",
        False,
    ),
    (
        re.compile(r"commit \(initial\): (.+)"),
        "commit",
        "✅ Initial commit: {0}",
        False,
    ),
    (
        re.compile(r"commit \(amend\): (.+)"),
        "commit_amend",
        "✏️  Amended: {0}",
        False,
    ),
    (
        re.compile(r"commit \(merge\): (.+)"),
        "merge_commit",
        "🔗 Merge commit: {0}",
        False,
    ),
    (
        re.compile(r"commit: (.+)"),
        "commit",
        "✅ Commit: {0}",
        False,
    ),
    (
        re.compile(r"rebase \(finish\): .+ onto (.+)"),
        "rebase",
        "🔄 Rebase finished onto {0}",
        False,
    ),
    (
        re.compile(r"rebase \(start\): .+"),
        "rebase",
        "🔄 Rebase started",
        False,
    ),
    (
        re.compile(r"rebase( \(pick\))?: (.+)"),
        "rebase",
        "🔄 Rebase pick: {1}",
        False,
    ),
    (
        re.compile(r"rebase \(abort\).*"),
        "rebase_abort",
        "🔄 Rebase aborted",
        True,
    ),
    (
        re.compile(r"merge (.+): .+"),
        "merge",
        "🔗 Merge: {0}",
        False,
    ),
    (
        re.compile(r"pull: (.+)"),
        "pull",
        "⬇️  Pull: {0}",
        False,
    ),
    (
        re.compile(r"pull"),
        "pull",
        "⬇️  Pull",
        False,
    ),
    (
        re.compile(r"Branch: renamed .+ to (.+)"),
        "branch_rename",
        "🌿 Branch renamed → {0}",
        False,
    ),
    (
        re.compile(r"branch: Created from (.+)"),
        "branch_create",
        "🌿 Branch created from {0}",
        False,
    ),
    (
        re.compile(r"clone: from (.+)"),
        "clone",
        "📦 Cloned from {0}",
        False,
    ),
]


def _classify(action: str) -> Tuple[str, str, bool]:
    """Classify a reflog action string into (category, human_summary, is_destructive)."""
    for pattern, category, template, destructive in _PATTERNS:
        match = pattern.match(action)
        if match:
            groups = match.groups()
            try:
                summary = template.format(*groups)
            except (IndexError, KeyError):
                summary = template
            return category, summary, destructive

    return "other", f"📋 {action}", False


def parse_reflog(raw: str) -> List[ReflogEntry]:
    """Parse raw reflog output into structured entries."""
    entries = []
    for line in raw.split("\n"):
        if not line.strip():
            continue

        parts = line.split(FIELD_SEP)
        if len(parts) < 4:
            continue

        hash_val, ref, action, timestamp = parts[0], parts[1], parts[2], parts[3]
        category, summary, destructive = _classify(action)

        entries.append(ReflogEntry(
            hash=hash_val,
            ref=ref,
            action=action,
            timestamp=timestamp,
            category=category,
            human_summary=summary,
            is_destructive=destructive,
        ))

    return entries


def find_last_destructive(entries: List[ReflogEntry]) -> Optional[ReflogEntry]:
    """Return the most recent destructive reflog entry, or None."""
    for entry in entries:
        if entry.is_destructive:
            return entry
    return None


def find_pre_destructive_hash(
    entries: List[ReflogEntry],
) -> Optional[Tuple[ReflogEntry, str]]:
    """Find the last destructive entry and the hash of the state before it.

    Returns (destructive_entry, pre_destructive_hash) or None.
    In the reflog, the entry immediately *after* the destructive one
    (i.e., at index+1 since reflog is newest-first) is the prior state.
    """
    for i, entry in enumerate(entries):
        if entry.is_destructive and i + 1 < len(entries):
            return entry, entries[i + 1].hash
    return None


def find_deleted_branches(client: GitClient) -> List[Tuple[str, str]]:
    """Scan reflog for branch deletion events.

    Checks checkout entries for branches that no longer exist.
    Returns list of (branch_name, last_known_commit_hash).
    """
    raw = client.reflog(limit=200)
    entries = parse_reflog(raw)
    existing = set(client.branch_list())

    seen_branches: dict[str, str] = {}

    for entry in entries:
        if entry.category == "checkout":
            match = re.match(r"checkout: moving from (.+) to (.+)", entry.action)
            if match:
                from_branch = match.group(1)
                to_branch = match.group(2)
                for branch_name in (from_branch, to_branch):
                    if (
                        branch_name not in existing
                        and branch_name not in seen_branches
                        and not _is_hash(branch_name)
                        and not branch_name.startswith("refs/")
                    ):
                        seen_branches[branch_name] = entry.hash

        if entry.category == "branch_create":
            match_bc = re.match(r"branch: Created from (.+)", entry.action)
            branch_ref = entry.ref
            short_name = branch_ref.split("/")[-1] if "/" in branch_ref else branch_ref
            if short_name not in existing and short_name not in seen_branches:
                seen_branches[short_name] = entry.hash

    result = []
    for name, hash_val in seen_branches.items():
        try:
            client.rev_parse(hash_val)
            result.append((name, hash_val))
        except Exception:
            pass

    return result


def _is_hash(s: str) -> bool:
    """Check if a string looks like a git hash (hex, 7+ chars)."""
    return bool(re.match(r"^[0-9a-f]{7,40}$", s))
