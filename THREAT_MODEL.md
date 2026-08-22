# THREAT MODEL — git-rescue

## Assets

| Asset | Sensitivity |
|-------|-------------|
| User's Git repository | High — source code, commit history |
| Working tree files | High — uncommitted work |
| Git reflog | Medium — contains operation history |
| Backup refs (refs/rescue/*) | Medium — safety snapshots |

## Attackers

Minimal attack surface. This tool:
- Has no network access.
- Accepts no external input beyond CLI arguments.
- Runs with the user's own filesystem permissions.

The primary "attacker" is **accidental misuse** by the user or **bugs in the tool itself**.

## Entry Points

| Entry Point | Input Source | Trust Level |
|---|---|---|
| CLI arguments | User-typed | Trusted (the user is running the tool) |
| Git reflog output | Local git binary | Trusted (local process) |
| Git fsck output | Local git binary | Trusted (local process) |
| Git object content | Local .git/ store | Trusted (local filesystem) |

## Trust Boundaries

```
User → CLI (argparse) → git_client.py → subprocess → git binary → .git/ store
```

Single trust boundary: `subprocess` call to `git`. Mitigated by list-form arguments (no shell injection).

## Abuse Cases (STRIDE)

| Threat | Category | Risk | Mitigation |
|---|---|---|---|
| Malicious reflog entry causes command injection | Tampering | Low | Arguments passed as list, never shell=True |
| Tool destroys current work during recovery | Tampering | Medium | Safety-first backup ref before any mutation (ADR-0002) |
| User runs `undo` multiple times, cascading resets | Tampering | Low | Each invocation creates a new backup; previous state always recoverable |
| Recovered blob overwrites existing file | Tampering | Low | Blobs written to `.git/rescue-recovered/`, not working tree |
| Tool exposes sensitive file content in terminal | Info Disclosure | Low | Tool only shows previews of content the user already has access to |
| Corrupted git object causes crash | DoS | Low | Error handling around cat-file; graceful degradation |

## Attack Chain Analysis

Not applicable — no network, no authentication, no multi-user access.
The tool runs in the same security context as `git` itself.
