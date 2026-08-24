# ARCHITECTURE — git-rescue

## Overview

```
┌─────────────────────────────────────────────┐
│                   CLI Layer                  │
│  cli.py (argparse + ANSI terminal output)   │
└────────────────────┬────────────────────────┘
                     │
┌────────────────────▼────────────────────────┐
│               Core Engine                    │
│  ┌──────────────┐ ┌──────────────────────┐  │
│  │ reflog_parser│ │    blob_scanner      │  │
│  └──────┬───────┘ └──────────┬───────────┘  │
│         │                    │               │
│  ┌──────▼────────────────────▼───────────┐  │
│  │            recovery.py                │  │
│  │  (safety snapshots + restore engine)  │  │
│  └──────────────────┬───────────────────┘   │
│                     │                        │
│  ┌──────────────────▼───────────────────┐   │
│  │          git_client.py               │   │
│  │  (subprocess wrapper for git CLI)    │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
                     │
              ┌──────▼──────┐
              │  git binary  │
              └─────────────┘
```

## Stack

| Technology | Why | Alternatives Considered | Trade-off | Maintenance |
|---|---|---|---|---|
| Python 3.8+ | Ubiquitous, batteries-included stdlib | Rust (too heavy for CLI), Go (no pip ecosystem) | Slower than compiled, but startup is fast enough for CLI | Python is evergreen |
| subprocess | Direct git CLI access, exact parity with user's git | GitPython, pygit2 (libgit2) | Extra process per call, but avoids C deps and version drift | Zero maintenance — stdlib |
| argparse | Built-in CLI framework | click, typer | Less ergonomic, but zero deps | stdlib — no breakage |
| dataclasses | Typed data containers | NamedTuple, attrs | Slightly less flexible than attrs, but stdlib | stdlib since 3.7 |

## Folder Tree

```
git_rescue/
├── git_rescue/
│   ├── __init__.py           # version + exports
│   ├── __main__.py           # python -m entrypoint
│   ├── cli.py                # argparse + terminal formatting
│   └── core/
│       ├── __init__.py
│       ├── git_client.py     # subprocess git wrapper
│       ├── reflog_parser.py  # reflog → semantic events
│       ├── blob_scanner.py   # fsck → dangling objects
│       └── recovery.py       # safety snapshot + restore
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # make_repo fixture (real isolated git repos)
│   ├── test_git_client.py
│   ├── test_reflog_parser.py
│   ├── test_blob_scanner.py
│   ├── test_recovery.py
│   └── test_cli.py
├── pyproject.toml
├── LICENSE
└── README.md
```

## Core Data Flow

### Timeline Command
```
git reflog --format → raw lines → ReflogEntry[] → semantic classifier → ANSI cards → stdout
```

### Undo Command
```
reflog → find_last_destructive() → create_backup_snapshot() → git reset --hard <pre-state> → diff summary
```

### Branches Command
```
reflog → find_deleted_branches() → create_backup_snapshot() → git branch <name> <hash> → confirmation
```

### Files Command
```
git fsck --dangling → DanglingObject[] → filter blobs → cat-file → .git/rescue-recovered/ → report
```

`--dangling` rather than `--lost-found`: both report the same objects, but
`--lost-found` writes copies into `.git/lost-found/`. Scanning must never mutate
the repository it is diagnosing.

## Auth Flow

N/A — local-only tool, no authentication.

## Integrations

None. This tool calls only the local `git` binary.

## Caching / State

No custom caching. Relies entirely on Git's own object store and reflog.

## Deploy Target

PyPI package (`pip install git-rescue`), runnable as `git-rescue` CLI or `python -m git_rescue`.
