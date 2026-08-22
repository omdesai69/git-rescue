# ADR-0001: Zero-Dependency, Stdlib-Only

## Status
Accepted

## Context
A Git recovery tool must install quickly, reliably, and on any system.
Adding dependencies like `GitPython`, `click`, or `rich` introduces:
- Supply-chain risk (transitive deps, maintainer abandonment).
- Installation friction (`pip` resolver conflicts, virtualenv requirements).
- Version drift between `GitPython`'s libgit2 bindings and the user's actual Git.

## Decision
Use ONLY the Python standard library. No runtime dependencies.
`pytest` is allowed as a dev/test dependency only.

## Alternatives
| Option | Rejected Because |
|---|---|
| GitPython | Wraps libgit2 — version drift, C extension build failures on some systems |
| click/typer | Adds dependency for marginal ergonomic gain over argparse |
| rich | Beautiful output but 3+ transitive deps; ANSI formatting is ~100 lines of stdlib code |

## Consequences
- Installation is always `pip install git-rescue` with zero resolver conflicts.
- ANSI terminal formatting must be implemented manually (~100 LOC).
- Git interactions use `subprocess` — slightly more boilerplate but exact CLI parity.
