# DATABASE — git-rescue

## Overview

git-rescue has no custom database. It reads and writes to Git's own internal stores.

## Data Stores (Read-Only)

| Store | Location | Accessed Via | Contents |
|---|---|---|---|
| Reflog | `.git/logs/HEAD`, `.git/logs/refs/` | `git reflog` | Operation history (resets, checkouts, commits) |
| Object store | `.git/objects/` | `git cat-file`, `git fsck` | Commits, trees, blobs (including dangling) |
| Refs | `.git/refs/` | `git for-each-ref` | Branch pointers, tags |

## Data Stores (Written)

| Store | Location | Written Via | Contents |
|---|---|---|---|
| Backup refs | `.git/refs/rescue/` | `git update-ref` | Safety snapshots before mutations |
| Recovered blobs | `.git/rescue-recovered/` | Direct file write | Dangling blob content + JSON metadata |

## Schema / Relations

N/A — Git's object model (commit → tree → blob) is the schema.

## Migrations

N/A — no custom schema to migrate.

## PII Flags

No PII is stored or processed. The tool reads only Git metadata and source code
that the user already has access to.
