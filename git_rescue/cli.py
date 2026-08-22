"""Argparse CLI and ANSI terminal formatter for git-rescue."""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Optional

from git_rescue import __version__
from git_rescue.core.git_client import GitClient, GitError, GitNotFound, NotAGitRepo
from git_rescue.core.reflog_parser import parse_reflog, find_deleted_branches
from git_rescue.core.recovery import (
    list_deleted_branches,
    recover_files,
    restore_branch,
    undo_last_destructive,
)

ANSI_RE = re.compile(r"\033\[[0-9;]*m")


class Color:
    """ANSI color codes with instant zeroing for non-color terminals."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_CYAN = "\033[96m"

    _ALL = ("RESET", "BOLD", "DIM", "RED", "GREEN", "YELLOW", "BLUE",
            "MAGENTA", "CYAN", "WHITE", "BRIGHT_RED", "BRIGHT_GREEN",
            "BRIGHT_YELLOW", "BRIGHT_CYAN")

    @classmethod
    def disable(cls) -> None:
        for attr in cls._ALL:
            setattr(cls, attr, "")


def _enable_windows_ansi() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        Color.disable()


def _should_use_color() -> bool:
    return not os.environ.get("NO_COLOR") and hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def _box(title: str, lines: list[str], color: str = Color.CYAN) -> str:
    all_lines = [title] + lines
    width = max(max((len(_strip_ansi(l)) for l in all_lines), default=0) + 4, 40)
    top = f"{color}╭{'─' * (width - 2)}╮{Color.RESET}"
    bottom = f"{color}╰{'─' * (width - 2)}╯{Color.RESET}"
    body = [f"{color}│{Color.RESET} {l}{' ' * max(0, width - len(_strip_ansi(l)) - 4)} {color}│{Color.RESET}" for l in all_lines]
    return "\n".join([top, *body, bottom])


def _header() -> str:
    return (
        f"\n{Color.BOLD}{Color.BRIGHT_CYAN}"
        f"  ╔══════════════════════════════════════╗\n"
        f"  ║         🛟  git-rescue v{__version__}         ║\n"
        f"  ║     Zero-dependency Git recovery     ║\n"
        f"  ╚══════════════════════════════════════╝"
        f"{Color.RESET}\n"
    )


TIMELINE_STYLES = {
    "commit": (Color.BRIGHT_GREEN, "●"),
    "commit_amend": (Color.BRIGHT_GREEN, "●"),
    "checkout": (Color.BRIGHT_CYAN, "◆"),
    "rebase": (Color.BRIGHT_YELLOW, "◈"),
    "rebase_abort": (Color.BRIGHT_YELLOW, "◈"),
    "merge": (Color.MAGENTA, "◉"),
    "merge_commit": (Color.MAGENTA, "◉"),
}


def cmd_timeline(client: GitClient, limit: int = 20) -> int:
    print(_header())
    print(f"  {Color.DIM}Scanning reflog for recent activity...{Color.RESET}\n")
    raw = client.reflog(limit=limit)
    entries = parse_reflog(raw) if raw else []
    if not entries:
        print(f"  {Color.YELLOW}No reflog entries found.{Color.RESET}\n")
        return 0

    destructive_count = 0
    for i, entry in enumerate(entries):
        if entry.is_destructive:
            destructive_count += 1
            color, marker = Color.BRIGHT_RED, "▸"
        else:
            color, marker = TIMELINE_STYLES.get(entry.category, (Color.WHITE, "○"))

        idx = f"{Color.DIM}[{i}]{Color.RESET}"
        h = f"{Color.DIM}{entry.hash[:8]}{Color.RESET}"
        summary = f"{color}{Color.BOLD}{entry.human_summary}{Color.RESET}"
        print(f"  {color}{marker}{Color.RESET} {idx} {h}  {summary}\n    {Color.DIM}{entry.timestamp}{Color.RESET}")
        if i < len(entries) - 1:
            print(f"  {Color.DIM}│{Color.RESET}")

    if destructive_count:
        print(f"\n  {Color.BRIGHT_RED}{Color.BOLD}⚠  {destructive_count} destructive operation(s) detected. Run `git-rescue undo` to recover.{Color.RESET}")
    print()
    return 0


def cmd_undo(client: GitClient) -> int:
    print(_header())
    print(f"  {Color.DIM}Scanning for destructive operations...{Color.RESET}\n")
    result = undo_last_destructive(client)
    print(f"  {Color.DIM}Backup created: {result.backup_ref}{Color.RESET}")
    if not result.success:
        print(f"\n  {Color.YELLOW}ℹ  {result.message}{Color.RESET}\n")
        return 1

    lines = [
        f"{Color.BOLD}{result.message}{Color.RESET}", "",
        f"  Restored to: {Color.GREEN}{result.restored_to[:12]}{Color.RESET}",
        f"  Backup ref:  {Color.DIM}{result.backup_ref}{Color.RESET}",
    ]
    if result.diff_summary:
        lines += ["", f"  {Color.BOLD}Changes recovered:{Color.RESET}"] + [
            f"    {l}" for l in result.diff_summary.splitlines()[:10]
        ]
    print(_box("🛟  Recovery Complete", lines, Color.GREEN))
    print(f"\n  {Color.DIM}To undo this recovery, run: git reset --hard {result.backup_ref}{Color.RESET}\n")
    return 0


def cmd_branches(client: GitClient) -> int:
    print(_header())
    print(f"  {Color.DIM}Scanning for deleted branches...{Color.RESET}\n")
    deleted = list_deleted_branches(client)
    if not deleted:
        print(f"  {Color.YELLOW}ℹ  No deleted branches found in reflog.{Color.RESET}\n")
        return 0

    print(f"  {Color.BOLD}Found {len(deleted)} deleted branch(es):{Color.RESET}\n")
    for i, (name, hash_val, summary) in enumerate(deleted):
        lines = [
            f"  Branch:  {Color.BOLD}{Color.BRIGHT_CYAN}{name}{Color.RESET}",
            f"  Commit:  {Color.DIM}{hash_val[:12]}{Color.RESET}",
            f"  Info:    {summary}", "",
            f"  {Color.DIM}Restore with: git-rescue branches --restore {name}{Color.RESET}",
        ]
        print(_box(f"🌿 Deleted Branch [{i}]", lines, Color.YELLOW))
        print()
    return 0


def cmd_branches_restore(client: GitClient, branch_name: str) -> int:
    print(_header())
    target = next((h for name, h in find_deleted_branches(client) if name == branch_name), None)
    if target is None:
        print(f"  {Color.RED}✗ Branch '{branch_name}' not found in deleted branches.{Color.RESET}\n")
        return 1

    result = restore_branch(client, branch_name, target)
    print(f"  {Color.DIM}Backup created: {result.backup_ref}{Color.RESET}")
    if not result.success:
        print(f"\n  {Color.RED}✗ {result.message}{Color.RESET}\n")
        return 1

    lines = [
        f"  Branch:  {Color.BOLD}{Color.GREEN}{result.branch_name}{Color.RESET}",
        f"  Commit:  {Color.DIM}{result.commit_hash[:12]}{Color.RESET}",
        f"  Info:    {result.commit_summary}",
    ]
    print(_box("🛟  Branch Restored", lines, Color.GREEN))
    print()
    return 0


def cmd_files(client: GitClient) -> int:
    print(_header())
    print(f"  {Color.DIM}Running git fsck to find lost files...{Color.RESET}\n")
    result = recover_files(client)
    print(f"  {Color.DIM}Backup created: {result.backup_ref}{Color.RESET}")
    if not result.success:
        print(f"\n  {Color.YELLOW}ℹ  {result.message}{Color.RESET}\n")
        return 0

    print(f"\n  {Color.GREEN}{Color.BOLD}🛟  Recovered {len(result.recovered_files)} file(s){Color.RESET}\n")
    for r in result.recovered_files:
        lines = [
            f"  Hash:    {Color.DIM}{r['hash'][:12]}{Color.RESET}",
            f"  Size:    {r['size']} bytes",
            f"  Saved:   {Color.CYAN}{r['path']}{Color.RESET}",
        ]
        if r.get("preview"):
            lines += ["", f"  {Color.BOLD}Preview:{Color.RESET}"] + [
                f"    {Color.DIM}{pl}{Color.RESET}" for pl in r["preview"].splitlines()[:5]
            ]
        print(_box("📄 Recovered File", lines, Color.CYAN))
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="git-rescue", description="🛟  Zero-dependency Git disaster recovery tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"git-rescue {__version__}")
    parser.add_argument("--no-color", action="store_true", default=False, help="Disable colorized output")

    sub = parser.add_subparsers(dest="command")
    tl = sub.add_parser("timeline", help="Show colorized reflog timeline (default)")
    tl.add_argument("-n", "--limit", type=int, default=20, help="Number of entries (default: 20)")
    sub.add_parser("undo", help="Revert the last destructive git operation")
    br = sub.add_parser("branches", help="List and restore deleted branches")
    br.add_argument("--restore", metavar="BRANCH", help="Restore a specific deleted branch")
    sub.add_parser("files", help="Recover lost staged files from dangling blobs")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    if sys.platform == "win32":
        for s in (sys.stdout, sys.stderr):
            if hasattr(s, "reconfigure"):
                try:
                    s.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass

    args = build_parser().parse_args(argv)
    if args.no_color or not _should_use_color():
        Color.disable()
    else:
        _enable_windows_ansi()

    try:
        client = GitClient()
    except GitNotFound as exc:
        print(f"{Color.RED}Error: {exc}{Color.RESET}", file=sys.stderr)
        return 128
    except NotAGitRepo as exc:
        print(f"{Color.RED}Error: {exc}{Color.RESET}", file=sys.stderr)
        return 2
    except GitError as exc:
        print(f"{Color.RED}Error: {exc}{Color.RESET}", file=sys.stderr)
        return 1

    cmd = args.command or "timeline"
    try:
        if cmd == "timeline":
            return cmd_timeline(client, limit=getattr(args, "limit", 20))
        elif cmd == "undo":
            return cmd_undo(client)
        elif cmd == "branches":
            return cmd_branches_restore(client, args.restore) if args.restore else cmd_branches(client)
        elif cmd == "files":
            return cmd_files(client)
        return 0
    except GitError as exc:
        print(f"\n  {Color.RED}Git error: {exc}{Color.RESET}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(f"\n  {Color.DIM}Interrupted.{Color.RESET}")
        return 130


def cli_entry() -> None:
    sys.exit(main())
