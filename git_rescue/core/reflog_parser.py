"""Semantic parser translating reflog entries into human-readable events."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from git_rescue.core.git_client import GitClient

FIELD_SEP = "\x1e"
HEX_CHARS = frozenset("0123456789abcdefABCDEF")

# `HEAD@{2026-08-23 17:00:53 +0530}` -> the reflog event date. Deliberately narrow:
# index selectors (`HEAD@{0}`) and relative ones (`HEAD@{2 hours ago}`) carry no
# absolute date, and must fall through to the commit date rather than yield "0".
_SELECTOR_DATE_RE = re.compile(r"@\{(\d{4}-\d{2}-\d{2}[ T][^}]*)\}\s*$")
_CHECKOUT_RE = re.compile(r"checkout: moving from (.+) to (.+)")


@dataclass
class ReflogEntry:
    """A single parsed reflog event."""
    hash: str
    ref: str
    action: str
    timestamp: str          # when the reflog event happened
    category: str
    human_summary: str
    is_destructive: bool = False
    commit_timestamp: str = ""   # committer date of `hash`, which may be far older


_PATTERNS: List[Tuple[re.Pattern, str, str, bool]] = [
    (re.compile(r"reset: moving to (.+)"), "hard_reset", "⚠️  Hard Reset → {0}", True),
    (re.compile(r"checkout: moving from (.+) to (.+)"), "checkout", "🔀 Switched from {0} → {1}", False),
    (re.compile(r"commit \(initial\): (.+)"), "commit", "✅ Initial commit: {0}", False),
    (re.compile(r"commit \(amend\): (.+)"), "commit_amend", "✏️  Amended: {0}", False),
    (re.compile(r"commit \(merge\): (.+)"), "merge_commit", "🔗 Merge commit: {0}", False),
    (re.compile(r"commit: (.+)"), "commit", "✅ Commit: {0}", False),
    (re.compile(r"rebase \(finish\): .+ onto (.+)"), "rebase", "🔄 Rebase finished onto {0}", False),
    (re.compile(r"rebase \(start\): .+"), "rebase", "🔄 Rebase started", False),
    (re.compile(r"rebase( \(pick\))?: (.+)"), "rebase", "🔄 Rebase pick: {1}", False),
    (re.compile(r"rebase \(abort\).*"), "rebase_abort", "🔄 Rebase aborted", True),
    (re.compile(r"merge (.+): .+"), "merge", "🔗 Merge: {0}", False),
    (re.compile(r"pull(: (.+))?"), "pull", "⬇️  Pull{0}", False),
    (re.compile(r"Branch: renamed .+ to (.+)"), "branch_rename", "🌿 Branch renamed → {0}", False),
    (re.compile(r"branch: Created from (.+)"), "branch_create", "🌿 Branch created from {0}", False),
    (re.compile(r"clone: from (.+)"), "clone", "📦 Cloned from {0}", False),
]


def _classify(action: str) -> Tuple[str, str, bool]:
    """Classify a reflog action string into (category, human_summary, is_destructive)."""
    if action == "pull":
        return "pull", "⬇️  Pull", False
    for pattern, category, template, destructive in _PATTERNS:
        match = pattern.match(action)
        if match:
            groups = match.groups()
            try:
                summary = template.format(*[g or "" for g in groups])
            except (IndexError, KeyError):
                summary = template
            return category, summary, destructive
    return "other", f"📋 {action}", False


def parse_reflog(raw: str) -> List[ReflogEntry]:
    """Parse raw reflog output into structured entries."""
    entries: List[ReflogEntry] = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split(FIELD_SEP)
        if len(parts) < 4:
            continue
        category, summary, destructive = _classify(parts[2])
        # Prefer the reflog event date embedded in the selector by --date=iso; the
        # commit date (parts[3]) belongs to the target commit, not to this event.
        selector_date = _SELECTOR_DATE_RE.search(parts[1])
        event_time = selector_date.group(1).strip() if selector_date else parts[3]
        entries.append(ReflogEntry(
            hash=parts[0], ref=parts[1], action=parts[2], timestamp=event_time,
            category=category, human_summary=summary, is_destructive=destructive,
            commit_timestamp=parts[3],
        ))
    return entries


def find_last_destructive(entries: List[ReflogEntry]) -> Optional[ReflogEntry]:
    """Return the most recent destructive reflog entry, or None."""
    return next((e for e in entries if e.is_destructive), None)


def find_pre_destructive_hash(entries: List[ReflogEntry]) -> Optional[Tuple[ReflogEntry, str]]:
    """Find the last destructive entry and the hash before it."""
    for i, entry in enumerate(entries):
        if entry.is_destructive and i + 1 < len(entries):
            return entry, entries[i + 1].hash
    return None


def _is_hash(s: str) -> bool:
    return 7 <= len(s) <= 64 and all(c in HEX_CHARS for c in s)


def find_deleted_branches(client: GitClient) -> List[Tuple[str, str]]:
    """Scan reflog for deleted branches and the last commit each pointed at.

    A reflog entry's hash is the value of HEAD *after* that operation. So for
    `checkout: moving from A to B` the entry's hash is B's tip, while A's tip is
    the hash of the *next* (older) entry — HEAD immediately before the checkout.
    Attributing the entry's own hash to A is what loses the branch's work.
    """
    entries = parse_reflog(client.reflog(limit=200))
    existing = set(client.branch_list())
    seen: dict[str, str] = {}   # newest sighting wins: entries are newest-first

    def consider(name: str, tip: str) -> None:
        if not name or not tip or name in existing or name in seen:
            return
        if _is_hash(name) or name.startswith("refs/") or "@{" in name:
            return
        seen[name] = tip

    for i, e in enumerate(entries):
        if e.category != "checkout":
            continue
        m = _CHECKOUT_RE.match(e.action)
        if not m:
            continue
        from_branch, to_branch = m.group(1), m.group(2)
        # HEAD after this checkout is the branch we moved *to*.
        consider(to_branch, e.hash)
        # HEAD before this checkout is the tip of the branch we moved *from*.
        if i + 1 < len(entries):
            consider(from_branch, entries[i + 1].hash)

    valid = []
    for name, hash_val in seen.items():
        try:
            client.rev_parse(hash_val)
            valid.append((name, hash_val))
        except Exception:
            pass
    return valid
