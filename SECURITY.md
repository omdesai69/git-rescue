# SECURITY — git-rescue

## Scope

Local-only CLI tool. No network, no auth, no user accounts, no secrets, no database.
Security concerns are limited to: subprocess safety, input validation, and data integrity.

## OWASP Top 10:2025 Applicability

| Control | Applicability | Implementation |
|---|---|---|
| A01 Broken Access Control | N/A | No access control — single-user local tool |
| A02 Security Misconfig | Low | No config files; tool validates git repo exists on startup |
| A03 Supply Chain | Mitigated | Zero runtime dependencies (ADR-0001) |
| A04 Crypto Failures | N/A | No cryptography used |
| A05 Injection | Mitigated | All subprocess calls use list-form args, never `shell=True` |
| A06 Insecure Design | Mitigated | Safety-first backup before mutations (ADR-0002) |
| A07 Auth Failures | N/A | No authentication |
| A08 Integrity Failures | Low | Tool trusts local git binary and object store |
| A09 Logging/Alerting | N/A | CLI tool — output goes to terminal |
| A10 Exceptional Conditions | Mitigated | All git subprocess calls wrapped in try/except with user-facing error messages |

## Subprocess Safety

```python
# ALWAYS this (list form):
subprocess.run(["git", "reflog", "--format=%H %gD %gs"], ...)

# NEVER this (shell form):
subprocess.run(f"git reflog --format='{user_input}'", shell=True, ...)
```

- All Git commands constructed as Python lists.
- No user input is interpolated into shell strings.
- `shell=True` is never used.

## Secrets

- No secrets are used, stored, or transmitted.
- No `.env` files.
- No API keys.

## Input Validation

- CLI arguments are validated by argparse (type-safe subcommands).
- Branch names passed to `restore_branch()` are validated against Git's ref naming rules.
- File paths for blob recovery use `pathlib` for safe construction.

## Data Integrity

- Backup refs (`refs/rescue/backup-*`) are created before any mutation.
- Recovered blobs are written to `.git/rescue-recovered/`, never to the working tree.
- The tool never force-deletes refs, branches, or files.
