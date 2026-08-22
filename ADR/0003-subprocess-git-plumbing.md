# ADR-0003: Subprocess Git Plumbing

## Status
Accepted

## Context
We need to interact with Git's object store, reflog, and refs.
Two approaches: bind to libgit2 (via GitPython/pygit2) or shell out to `git` CLI.

## Decision
Use `subprocess.run()` with list-form arguments (never `shell=True`) to call
the user's installed `git` binary directly.

## Alternatives
| Option | Rejected Because |
|---|---|
| GitPython | C extension dependency, version drift with user's git, see ADR-0001 |
| pygit2 | Requires libgit2 system library — installation friction on Windows/macOS |
| dulwich | Pure Python git, but large dep and doesn't support all plumbing commands |

## Consequences
- Exact parity with the user's Git version and config.
- Each Git operation spawns a subprocess — negligible overhead for a CLI tool.
- All arguments are passed as lists, preventing shell injection.
- Git must be installed and on PATH — the tool validates this on startup.
