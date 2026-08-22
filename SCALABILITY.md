# SCALABILITY — git-rescue

## Overview

git-rescue is a local CLI tool. "Scale" means handling large Git repositories,
not user traffic or server load.

## Scaling Considerations

| Users / Repo Size | Bottleneck | Change Required |
|---|---|---|
| Small repos (<1K commits) | None | — |
| Medium repos (1K–10K commits) | Reflog parse time | Limit reflog scan depth with `-n` flag (default: 20) |
| Large repos (10K–100K commits) | `git fsck` can be slow (minutes) | Add progress indicator; consider `--no-fsck` flag |
| Monorepos (100K+ commits) | `git fsck` may take 10+ minutes | Future: incremental fsck, cache dangling object list |
| Very large blob recovery | Disk space for recovered blobs | Warn user of estimated disk usage before recovery |

## Current Limits

- Reflog is scanned with configurable depth (`-n`, default 20). Git reflog default expiry is 90 days.
- `git fsck` scans the entire object store — O(objects). No way to limit this in Git itself.
- Blob previews are capped at 200 bytes to avoid memory issues with large binary objects.
- Subprocess timeout is 30 seconds per call (configurable in future).

## Future Optimizations

- Cache `fsck` results to avoid re-scanning on repeated `files` invocations.
- Parallel subprocess calls for batch `cat-file` operations.
- Streaming output for timeline (don't buffer all entries before display).
