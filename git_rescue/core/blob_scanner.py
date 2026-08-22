"""Dangling object scanner and lost staged file extractor.

Uses `git fsck` to find dangling blobs, commits, and trees,
then reconstructs lost content with metadata.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from git_rescue.core.git_client import GitClient, GitError

PREVIEW_MAX_BYTES = 200
RECOVERY_DIR_NAME = "rescue-recovered"


@dataclass
class DanglingObject:
    """A dangling git object found by fsck."""
    hash: str
    object_type: str
    size: int = 0
    preview: str = ""
    is_binary: bool = False


def scan_dangling(client: GitClient) -> List[DanglingObject]:
    """Run git fsck and parse dangling objects."""
    raw = client.fsck_dangling()
    objects = []

    pattern = re.compile(r"dangling (blob|commit|tree) ([0-9a-f]{40})")

    for match in pattern.finditer(raw):
        obj_type = match.group(1)
        obj_hash = match.group(2)

        obj = DanglingObject(hash=obj_hash, object_type=obj_type)

        try:
            obj.size = client.cat_file_size(obj_hash)
        except GitError:
            continue

        if obj_type == "blob":
            obj = _enrich_blob(client, obj)

        objects.append(obj)

    return objects


def _enrich_blob(client: GitClient, obj: DanglingObject) -> DanglingObject:
    """Add preview and binary detection to a blob object."""
    try:
        content = client.cat_file_content(obj.hash)
        preview = content[:PREVIEW_MAX_BYTES]

        if "\x00" in preview or _looks_binary(preview):
            obj.is_binary = True
            obj.preview = f"[binary data, {obj.size} bytes]"
        else:
            obj.preview = preview.rstrip()
            if len(content) > PREVIEW_MAX_BYTES:
                obj.preview += "\n..."
    except GitError:
        obj.preview = "[unable to read content]"

    return obj


def _looks_binary(text: str) -> bool:
    """Heuristic: if more than 10% of chars are non-printable, it's likely binary."""
    if not text:
        return False
    non_printable = sum(
        1 for c in text
        if ord(c) < 32 and c not in ("\n", "\r", "\t")
    )
    return non_printable / len(text) > 0.1


def recover_blobs(
    client: GitClient,
    target_dir: Optional[Path] = None,
) -> List[dict]:
    """Write dangling blobs to disk with metadata sidecars.

    Returns a list of recovery records (dicts with hash, path, size, etc.).
    """
    objects = scan_dangling(client)
    blobs = [obj for obj in objects if obj.object_type == "blob" and not obj.is_binary]

    if not blobs:
        return []

    if target_dir is None:
        git_dir = Path(client.repo_path) / ".git"
        target_dir = git_dir / RECOVERY_DIR_NAME

    target_dir.mkdir(parents=True, exist_ok=True)
    records = []

    for blob in blobs:
        try:
            content = client.cat_file_content(blob.hash)
        except GitError:
            continue

        short_hash = blob.hash[:12]
        ext = _guess_extension(content)
        filename = f"{short_hash}{ext}"
        filepath = target_dir / filename

        counter = 1
        while filepath.exists():
            filepath = target_dir / f"{short_hash}_{counter}{ext}"
            counter += 1

        filepath.write_text(content, encoding="utf-8")

        meta = {
            "hash": blob.hash,
            "size": blob.size,
            "recovered_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "path": str(filepath),
            "preview": blob.preview[:100],
        }
        meta_path = filepath.with_suffix(filepath.suffix + ".meta.json")
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        records.append(meta)

    return records


def _guess_extension(content: str) -> str:
    """Guess file extension from content heuristics."""
    first_line = content.split("\n", 1)[0].strip()

    if first_line.startswith("#!/"):
        if "python" in first_line:
            return ".py"
        if "bash" in first_line or "sh" in first_line:
            return ".sh"
        if "node" in first_line:
            return ".js"

    if first_line.startswith("<!DOCTYPE") or first_line.startswith("<html"):
        return ".html"
    if first_line.startswith("<?xml"):
        return ".xml"
    if first_line.startswith("{") or first_line.startswith("["):
        return ".json"
    if "import " in first_line or "from " in first_line or "def " in first_line:
        return ".py"
    if "function " in first_line or "const " in first_line or "var " in first_line:
        return ".js"
    if first_line.startswith("package "):
        return ".java"
    if first_line.startswith("#include"):
        return ".c"

    return ".txt"
