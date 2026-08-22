# TODO — git-rescue v0.1.0

## Core Features

### `timeline` command
- **Why**: Developers need to understand what happened in their repo before they can fix it.
- **Who**: Any developer debugging a Git mishap.
- **Simpler version?**: No — this is the simplest useful form (colorized reflog).
- **Cuttable?**: No — this is the foundation all other commands build on.

### `undo` command
- **Why**: `git reset --hard` is the #1 cause of accidental data loss. One-click reversal is the primary value prop.
- **Who**: Any developer who just ran a destructive command.
- **Simpler version?**: Could just print the command instead of executing it — but that defeats the "1-click" promise.
- **Cuttable?**: No — this is the headline feature.

### `branches` command
- **Why**: Deleted branches are recoverable via reflog but the process is manual and error-prone.
- **Who**: Developers who accidentally delete branches (especially after `git branch -D`).
- **Simpler version?**: Could just list deleted branches without restoration — but restoration is trivial to add.
- **Cuttable?**: Could be deferred, but it's low effort and high value.

### `files` command
- **Why**: Staged files that are never committed become dangling blobs. `git fsck` finds them but doesn't name them.
- **Who**: Developers who staged work, then lost it through reset or checkout.
- **Simpler version?**: Could just list blobs without saving — but saving is the whole point.
- **Cuttable?**: Could be deferred to v0.2.0, but it rounds out the feature set.

## Safety Infrastructure

### Backup refs (`refs/rescue/backup-*`)
- **Why**: The safety-first invariant. Cannot cut this.
- **Already solved?**: Git stash is similar but doesn't capture full HEAD state.

### ANSI terminal formatting
- **Why**: Readable output is the UX differentiator over raw `git reflog`.
- **Already solved?**: `rich` library does this, but we're zero-dep.

## Non-v1 Features (Deferred)

- Interactive branch/blob selection (v0.2.0)
- Dropped stash recovery (v0.3.0)
- `cleanup` command to prune old backup refs (v0.3.0)
- `--json` output mode for scripting (v0.4.0)
