"""Dangling object scanner and lost staged file extractor."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from git_rescue.core.git_client import GitClient, GitError

PREVIEW_MAX_BYTES = 200
RECOVERY_DIR_NAME = "rescue-recovered"
FSCK_PATTERN = re.compile(r"dangling (blob|commit|tree) ([0-9a-f]{40})")

EXTENSION_RULES = [
    (lambda l: "python" in l or l.startswith(("import ", "from ", "def ")), ".py"),
    (lambda l: "bash" in l or "sh" in l, ".sh"),
    (lambda l: "node" in l or l.startswith(("function ", "const ", "var ")), ".js"),
    (lambda l: l.startswith(("<!DOCTYPE", "<html")), ".html"),
    (lambda l: l.startswith("<?xml"), ".xml"),
    (lambda l: l.startswith(("{", "[")), ".json"),
    (lambda l: l.startswith("package "), ".java"),
    (lambda l: l.startswith("#include"), ".c"),
]


@dataclass
class DanglingObject:
    """A dangling git object found by fsck."""
    hash: str
    object_type: str
    size: int = 0
    preview: str = ""
    is_binary: bool = False
    content: Optional[str] = None


def _looks_binary(text: str) -> bool:
    if not text:
        return False
    if "\x00" in text:
        return True
    non_printable = sum(1 for c in text if ord(c) < 32 and c not in "\n\r\t")
    return (non_printable / len(text)) > 0.1


def _guess_extension(content: str) -> str:
    first_line = content.split("\n", 1)[0].strip()
    for predicate, ext in EXTENSION_RULES:
        if predicate(first_line):
            return ext
    return ".txt"


def scan_dangling(client: GitClient) -> List[DanglingObject]:
    """Run git fsck and parse dangling objects."""
    raw = client.fsck_dangling()
    objects: List[DanglingObject] = []

    for match in FSCK_PATTERN.finditer(raw):
        obj_type, obj_hash = match.group(1), match.group(2)
        try:
            size = client.cat_file_size(obj_hash)
        except GitError:
            continue

        obj = DanglingObject(hash=obj_hash, object_type=obj_type, size=size)
        if obj_type == "blob":
            try:
                content = client.cat_file_content(obj_hash)
                obj.content = content
                sample = content[:PREVIEW_MAX_BYTES]
                if _looks_binary(sample):
                    obj.is_binary = True
                    obj.preview = f"[binary data, {obj.size} bytes]"
                else:
                    obj.preview = sample.rstrip() + ("\n..." if len(content) > PREVIEW_MAX_BYTES else "")
            except GitError:
                obj.preview = "[unable to read content]"
        objects.append(obj)

    return objects


def recover_blobs(client: GitClient, target_dir: Optional[Path] = None) -> List[dict]:
    """Write dangling blobs to disk with metadata sidecars (single-pass I/O)."""
    blobs = [b for b in scan_dangling(client) if b.object_type == "blob" and not b.is_binary]
    if not blobs:
        return []

    target_dir = target_dir or (Path(client.repo_path) / ".git" / RECOVERY_DIR_NAME)
    target_dir.mkdir(parents=True, exist_ok=True)
    records: List[dict] = []
    iso_time = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    for blob in blobs:
        content = blob.content
        if content is None:
            try:
                content = client.cat_file_content(blob.hash)
            except GitError:
                continue

        short_hash = blob.hash[:12]
        ext = _guess_extension(content)
        filepath = target_dir / f"{short_hash}{ext}"
        counter = 1
        while filepath.exists():
            filepath = target_dir / f"{short_hash}_{counter}{ext}"
            counter += 1

        filepath.write_text(content, encoding="utf-8")
        meta = {
            "hash": blob.hash, "size": blob.size, "recovered_at": iso_time,
            "path": str(filepath), "preview": blob.preview[:100],
        }
        meta_path = filepath.with_suffix(filepath.suffix + ".meta.json")
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        records.append(meta)

    return records
