# ADR-0002: Safety-First Backup Refs

## Status
Accepted

## Context
A recovery tool that can itself cause data loss is worse than useless.
If `git-rescue undo` performs a `reset --hard` to restore a prior state,
it overwrites the current working tree — potentially destroying uncommitted work
the user created *after* the original accident.

## Decision
Before executing ANY mutating operation, `git-rescue` MUST automatically create
a lightweight ref at `refs/rescue/backup-<unix_timestamp>` pointing to the
current HEAD. This ensures:
1. The user can always return to the pre-rescue state.
2. Git's garbage collector won't prune the backup (it's a named ref).
3. Backups are discoverable via `git for-each-ref refs/rescue/`.

## Alternatives
| Option | Rejected Because |
|---|---|
| Git stash | Stash only captures working tree + index, not full commit graph state |
| Tag objects | Tags pollute `git tag` output; refs/rescue/ is a clean namespace |
| No backup | Violates safety-first invariant — unacceptable |

## Consequences
- Every mutating command creates exactly one ref. Over time these accumulate.
- Future versions may add a `git-rescue cleanup` command to prune old backup refs.
- Ref names use Unix timestamps for uniqueness and sortability.
