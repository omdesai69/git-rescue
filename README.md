# git-rescue

[![PyPI version](https://img.shields.io/pypi/v/git-rescue-cli.svg)](https://pypi.org/project/git-rescue-cli/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#)

**Zero-dependency Git disaster recovery.** Parses reflog and dangling objects into human-readable action cards with safe, 1-click restore.

---

## The Problem

Accidental `git reset --hard`, deleted branches, or aborted rebases leave orphaned commits and lost work. While Git preserves these in the reflog and loose object databases, manual recovery commands are low-level and error-prone:

```bash
# Manual recovery:
git reflog | head -20
git fsck --lost-found --no-reflogs
git cat-file -p abc1234
git reset --hard HEAD@{3}
```

## The Solution

```bash
pip install git-rescue-cli
```

```bash
# Recovery with git-rescue:
git-rescue                    # Inspect timeline and recent actions
git-rescue undo               # Revert the last destructive operation
git-rescue branches           # Find and restore deleted branches
git-rescue files              # Recover lost staged files
```

---

## Quick Start

### Installation

```bash
pip install git-rescue-cli
```

Or install from source:

```bash
git clone https://github.com/omdesai69/git-rescue.git
cd git-rescue
pip install -e .
```

### Requirements

- **Python 3.8+**
- **Git 2.10+** (available on PATH)
- **Zero external dependencies** (standard library only)

---

## Commands

### `git-rescue` / `git-rescue timeline`

Scans reflog entries and displays a structured timeline:

```
  +--------------------------------------+
  |         git-rescue v0.1.0            |
  |     Zero-dependency Git recovery     |
  +--------------------------------------+

  * [0] a1b2c3d4  Commit: Fix authentication bug
    2024-06-15 14:32:00 +0530
  |
  > [1] d4e5f6a7  Hard Reset -> HEAD~2
    2024-06-15 14:30:00 +0530
  |
  * [2] f6a7b8c9  Commit: Add user dashboard
    2024-06-15 14:25:00 +0530

  1 destructive operation detected. Run `git-rescue undo` to recover.
```

Control displayed entry count:
```bash
git-rescue timeline -n 50
```

### `git-rescue undo`

Identifies the latest destructive operation and safely restores pre-operation state:

```
  Backup created: refs/rescue/backup-1718448600

  +------------------------------------------+
  | Recovery Complete                        |
  | Reverted: Hard Reset -> HEAD~2           |
  |                                          |
  |   Restored to: a1b2c3d4e5f6              |
  |   Backup ref:  refs/rescue/backup-...    |
  |                                          |
  |   Changes recovered:                     |
  |     dashboard.py | 45 +++++++++          |
  |     auth.py      | 12 +++               |
  +------------------------------------------+

  To revert this operation: git reset --hard refs/rescue/backup-1718448600
```

### `git-rescue branches`

Scans reflog for branch references and provides restoration:

```bash
git-rescue branches                        # List deleted branches
git-rescue branches --restore feature-x    # Restore specific branch
```

### `git-rescue files`

Recovers dangling blobs (lost staged files) from `git fsck`:

```bash
git-rescue files
```

Recovered files are written to `.git/rescue-recovered/` alongside JSON metadata sidecars.

---

## Safety Guarantees

Before executing any state-modifying action, `git-rescue` automatically creates an immutable timestamped backup ref:

```
refs/rescue/backup-<timestamp>
```

- Pre-rescue state is fully preserved.
- Undo operations are reversible: `git reset --hard refs/rescue/backup-<timestamp>`.
- Backup refs are explicit Git references protected from automatic garbage collection.

---

## Global Options

| Flag | Description |
|------|-------------|
| `--no-color` | Disable ANSI color formatting |
| `--version` | Display version information |
| `-n, --limit` | Maximum entries to display (timeline) |

The `NO_COLOR` environment variable is fully supported.

---

## Development

```bash
git clone https://github.com/omdesai69/git-rescue.git
cd git-rescue
pip install -e ".[dev]"
pytest
```

---

## License

MIT - see [LICENSE](LICENSE).

Copyright (c) 2026 Om Desai

