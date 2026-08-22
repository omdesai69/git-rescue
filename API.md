# API — git-rescue (CLI Interface Contract)

## Commands

| Command | Method | Description | Exit Code |
|---|---|---|---|
| `git-rescue` | — | Alias for `timeline` | 0 success, 1 error |
| `git-rescue timeline` | — | Display colorized reflog event cards | 0 |
| `git-rescue undo` | — | Revert last destructive operation | 0 success, 1 no destructive op found |
| `git-rescue branches` | — | List and restore deleted branches | 0 |
| `git-rescue files` | — | Recover dangling blobs to disk | 0 |

## Global Flags

| Flag | Type | Default | Description |
|---|---|---|---|
| `--no-color` | bool | false | Disable ANSI color output |
| `--version` | — | — | Print version and exit |
| `-n, --limit` | int | 20 | Max entries to display (timeline) |

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Git error or no recoverable data found |
| 2 | Not a Git repository |
| 128 | Git binary not found |

## Abuse Protection

| Endpoint | Auth? | Rate Limit | Burst | Payload Cap | Timeout | Idempotent? |
|---|---|---|---|---|---|---|
| All commands | N/A | N/A | N/A | N/A | 30s per git subprocess | Yes (backup refs ensure repeatability) |

Rate limiting and payload caps are not applicable — this is a local CLI tool
with no network access. The 30s subprocess timeout prevents hangs on corrupted repos.

## Versioning

CLI follows semantic versioning. No API stability guarantee until v1.0.0.
