"""Shared test fixtures and helpers for git-rescue test suite."""

from __future__ import annotations

import subprocess
from pathlib import Path
import pytest


@pytest.fixture
def make_repo(tmp_path: Path):
    """Fixture providing a helper to initialize real, isolated Git repositories."""
    def _create(name: str = "repo") -> Path:
        p = tmp_path / name
        p.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", str(p)], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(p), "config", "user.email", "test@test.com"], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(p), "config", "user.name", "Test"], capture_output=True, check=True)
        (p / "README.md").write_text("# Test\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(p), "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(p), "commit", "-m", "Initial commit"], capture_output=True, check=True)
        return p
    return _create
