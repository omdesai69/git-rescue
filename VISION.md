# VISION — git-rescue

## Problem

Developers routinely lose work through destructive Git operations:
`git reset --hard`, accidental branch deletions, rebase mishaps, and discarded staged files.
Git internally preserves recovery data in the reflog and as dangling objects,
but the interfaces to access them (`git reflog`, `git fsck`) are cryptic,
error-prone, and hostile to anyone who isn't a Git internals expert.

## Target User

Any developer who uses Git from the command line — from junior engineers
to senior staff — who has lost work and needs fast, safe recovery without
memorizing plumbing commands.

## Success Criteria

1. A user who ran `git reset --hard` can recover their prior state in a single command.
2. Deleted branches are detected and restorable with one command.
3. Lost staged files (dangling blobs) are surfaced with previews and saved to disk.
4. Every recovery action is preceded by an automatic safety snapshot — the user can never make things worse by using the tool.
5. Zero external dependencies — installs cleanly on any system with Python 3.8+ and Git.

## Non-Goals

- GUI or TUI framework (curses, textual). This is a CLI tool with ANSI formatting.
- Replacing `git reflog` for power users who prefer raw output.
- Handling bare repositories or server-side Git operations.
- Network operations (push, fetch, clone).
- Supporting Git versions older than 2.10.

## Data Touched

- **Read**: `.git/logs/` (reflog), Git object store (via `git cat-file`, `git fsck`).
- **Write**: `refs/rescue/backup-*` (safety snapshots), `.git/rescue-recovered/` (recovered blobs).
- **No network, no credentials, no user PII.**

## Roadmap

| Version | Scope |
|---------|-------|
| 0.1.0 | Core commands: `timeline`, `undo`, `branches`, `files` |
| 0.2.0 | Interactive selection (pick which branch/blob to restore) |
| 0.3.0 | `git-rescue stash` — recover dropped stashes |
| 1.0.0 | Stable API, full test coverage, PyPI release |
