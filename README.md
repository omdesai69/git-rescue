# 🛟 git-rescue

[![PyPI version](https://img.shields.io/pypi/v/git-rescue.svg)](https://pypi.org/project/git-rescue/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#)

**Zero-dependency Git disaster recovery.** Parses your reflog and dangling objects into human-readable action cards with safe, 1-click restore.

---

## The Problem

You just ran `git reset --hard` and your work is gone. Or you deleted a branch. Or a rebase went sideways.

Git *stores* everything you need to recover — in the reflog and as dangling objects — but the commands to access them are cryptic:

```bash
# 😵 This is what recovery looks like today:
git reflog | head -20
git fsck --lost-found --no-reflogs
git cat-file -p abc1234
git reset --hard HEAD@{3}   # ...and pray
```

## The Solution

```bash
pip install git-rescue
```

```bash
# 🛟 This is what recovery should look like:
git-rescue                    # See what happened
git-rescue undo               # Revert the last destructive operation
git-rescue branches           # Find and restore deleted branches
git-rescue files              # Recover lost staged files
```

---

## Quick Start

### Installation

```bash
pip install git-rescue
```

Or run directly from source:

```bash
git clone https://github.com/omdesai/git-rescue.git
cd git-rescue
pip install -e .
```

### Requirements

- **Python 3.8+**
- **Git 2.10+** (installed and on PATH)
- **Zero Python dependencies** — uses only the standard library

---

## Commands

### `git-rescue` / `git-rescue timeline`

Scans your reflog and displays a colorized timeline of recent actions:

```
  ╔══════════════════════════════════════╗
  ║         🛟  git-rescue v0.1.0        ║
  ║     Zero-dependency Git recovery     ║
  ╚══════════════════════════════════════╝

  ● [0] a1b2c3d4  ✅ Commit: Fix authentication bug
    2024-06-15 14:32:00 +0530
  │
  ▸ [1] d4e5f6a7  ⚠️  Hard Reset → HEAD~2
    2024-06-15 14:30:00 +0530
  │
  ● [2] f6a7b8c9  ✅ Commit: Add user dashboard
    2024-06-15 14:25:00 +0530

  ⚠  1 destructive operation(s) detected. Run `git-rescue undo` to recover.
```

Use `-n` to control how many entries to show:

```bash
git-rescue timeline -n 50
```

### `git-rescue undo`

Detects the last destructive command and safely reverts to the state before it:

```
  Backup created: refs/rescue/backup-1718448600

  ╭──────────────────────────────────────────╮
  │ 🛟  Recovery Complete                     │
  │ Reverted: ⚠️  Hard Reset → HEAD~2        │
  │                                          │
  │   Restored to: a1b2c3d4e5f6             │
  │   Backup ref:  refs/rescue/backup-...    │
  │                                          │
  │   Changes recovered:                     │
  │     dashboard.py | 45 +++++++++          │
  │     auth.py      | 12 +++               │
  ╰──────────────────────────────────────────╯

  To undo this recovery: git reset --hard refs/rescue/backup-1718448600
```

### `git-rescue branches`

Finds deleted branches in the reflog and offers restoration:

```bash
git-rescue branches                        # List deleted branches
git-rescue branches --restore feature-x    # Restore a specific branch
```

### `git-rescue files`

Recovers dangling blobs (lost staged files) from `git fsck`:

```
  🛟  Recovered 3 file(s)

  ╭──────────────────────────────────────────╮
  │ 📄 Recovered File                        │
  │   Hash:    a1b2c3d4e5f6                 │
  │   Size:    1,234 bytes                  │
  │   Saved:   .git/rescue-recovered/...    │
  │                                          │
  │   Preview:                               │
  │     def important_function():            │
  │         return calculate_revenue()       │
  ╰──────────────────────────────────────────╯
```

Recovered files are saved to `.git/rescue-recovered/` with JSON metadata sidecars.

---

## Safety Guarantee

**git-rescue can never make things worse.**

Before executing ANY recovery action, it automatically creates a timestamped backup ref:

```
refs/rescue/backup-1718448600
```

This means:
- ✅ Your pre-rescue state is always preserved
- ✅ You can always undo an undo: `git reset --hard refs/rescue/backup-<timestamp>`
- ✅ Backup refs are immune to Git garbage collection (they're named refs)

---

## Global Options

| Flag | Description |
|------|-------------|
| `--no-color` | Disable ANSI color output |
| `--version` | Print version and exit |
| `-n, --limit` | Max entries to display (timeline only, default: 20) |

The `NO_COLOR` environment variable is also respected.

---

## How It Works

1. **Timeline**: Parses `git reflog` output, classifies each entry semantically (hard reset, checkout, commit, rebase, merge), and renders colorized cards.

2. **Undo**: Finds the most recent destructive operation in the reflog, identifies the commit hash of the state *before* that operation, creates a safety backup, and performs `git reset --hard` to restore.

3. **Branches**: Cross-references branch names in checkout reflog entries against existing branches to find deletions, then recreates branches at their last known commit.

4. **Files**: Runs `git fsck --lost-found` to find dangling blobs, extracts content previews, detects binary vs text, and writes recoverable files to `.git/rescue-recovered/`.

---

## Development

```bash
git clone https://github.com/omdesai/git-rescue.git
cd git-rescue
pip install -e ".[dev]"
pytest
```

---

## License

MIT — see [LICENSE](LICENSE).

Copyright (c) 2026 Om Desai
