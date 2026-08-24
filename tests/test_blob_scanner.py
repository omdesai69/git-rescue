"""Regression tests for blob_scanner.py — dangling object parsing and typing."""

from __future__ import annotations

import subprocess
from pathlib import Path

from git_rescue.core.blob_scanner import (
    FSCK_PATTERN, _guess_extension, _looks_binary, recover_blobs, scan_dangling,
)
from git_rescue.core.git_client import GitClient


class TestFsckPattern:
    def test_matches_sha1_object_id(self):
        oid = "a" * 40
        match = FSCK_PATTERN.search(f"dangling blob {oid}")
        assert match and match.group(2) == oid

    def test_captures_full_sha256_object_id(self):
        """A 64-hex id must not be truncated to its first 40 characters."""
        oid = "b" * 64
        match = FSCK_PATTERN.search(f"dangling blob {oid}")
        assert match and match.group(2) == oid and len(match.group(2)) == 64

    def test_matches_all_object_types(self):
        oid = "c" * 40
        for obj_type in ("blob", "commit", "tree"):
            match = FSCK_PATTERN.search(f"dangling {obj_type} {oid}")
            assert match and match.group(1) == obj_type


class TestGuessExtension:
    def test_shebangs(self):
        assert _guess_extension("#!/bin/bash\necho hi") == ".sh"
        assert _guess_extension("#!/usr/bin/env python3\n") == ".py"
        assert _guess_extension("#!/usr/bin/env node\n") == ".js"

    def test_javascript_is_not_mistaken_for_shell(self):
        """`"sh" in line` used to claim any line containing those two letters."""
        assert _guess_extension("const shape = 1;") == ".js"
        assert _guess_extension("function show() {}") == ".js"
        assert _guess_extension("var dashboard = 2;") == ".js"

    def test_json_is_not_mistaken_for_shell(self):
        assert _guess_extension('{"shell": true}') == ".json"

    def test_structured_formats(self):
        assert _guess_extension("<!DOCTYPE html>") == ".html"
        assert _guess_extension("<?xml version='1.0'?>") == ".xml"
        assert _guess_extension("#include <stdio.h>") == ".c"
        assert _guess_extension("package com.example;") == ".java"

    def test_python_keywords(self):
        assert _guess_extension("import os") == ".py"
        assert _guess_extension("class Foo:") == ".py"

    def test_unknown_falls_back_to_txt(self):
        assert _guess_extension("just some prose about a shell") == ".txt"


class TestLooksBinary:
    def test_nul_byte_is_binary(self):
        assert _looks_binary("abc\x00def") is True

    def test_plain_text_is_not_binary(self):
        assert _looks_binary("hello world\n") is False

    def test_empty_is_not_binary(self):
        assert _looks_binary("") is False


class TestScanDoesNotMutateRepo:
    def test_no_lost_found_directory_created(self, make_repo):
        """Scanning is read-only: `--lost-found` used to write copies into .git."""
        repo = make_repo()
        (repo / "orphan.py").write_text("def orphan():\n    return 1\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(repo), "reset", "HEAD", "--", "orphan.py"],
                       capture_output=True, check=True)

        scan_dangling(GitClient(repo))
        assert not (Path(repo) / ".git" / "lost-found").exists()


class TestRecoverBlobs:
    def test_metadata_records_full_object_id(self, make_repo):
        repo = make_repo()
        (repo / "orphan.py").write_text("def orphan():\n    return 1\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(repo), "reset", "HEAD", "--", "orphan.py"],
                       capture_output=True, check=True)

        client = GitClient(repo)
        records = recover_blobs(client)
        for record in records:
            # Must be a resolvable object id, not an abbreviation.
            assert client.rev_parse(record["hash"]) == record["hash"]
            assert Path(record["path"]).exists()

    def test_sidecar_sits_beside_recovered_file(self, make_repo, tmp_path):
        repo = make_repo()
        (repo / "orphan.py").write_text("def orphan():\n    return 2\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(repo), "reset", "HEAD", "--", "orphan.py"],
                       capture_output=True, check=True)

        out = tmp_path / "recovered"
        records = recover_blobs(GitClient(repo), target_dir=out)
        for record in records:
            path = Path(record["path"])
            assert path.exists()
            assert path.with_name(path.name + ".meta.json").exists()
