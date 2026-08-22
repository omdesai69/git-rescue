"""Argparse CLI and ANSI terminal formatter for git-rescue.

Handles argument parsing, color output, and command dispatch.
Supports Windows VT100 terminal sequences and NO_COLOR convention.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from git_rescue import __version__
from git_rescue.core.git_client import GitClient, GitError, GitNotFound, NotAGitRepo
from git_rescue.core.reflog_parser import parse_reflog, find_deleted_branches
from git_rescue.core.recovery import (
    create_backup_snapshot,
    list_deleted_branches,
    recover_files,
    restore_branch,
    undo_last_destructive,
)


class Color:
    """ANSI color codes with graceful degradation."""

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

    _enabled = True

    @classmethod
    def disable(cls) -> None:
        for attr in dir(cls):
            if attr.isupper() and isinstance(getattr(cls, attr), str) and attr != "_enabled":
                setattr(cls, attr, "")
        cls._enabled = False


def _enable_windows_ansi() -> None:
    """Enable VT100 escape sequences on Windows 10+."""
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        Color.disable()


def _should_use_color() -> bool:
    """Respect NO_COLOR convention and detect terminal capability."""
    if os.environ.get("NO_COLOR"):
        return False
    if not hasattr(sys.stdout, "isatty"):
        return False
    return sys.stdout.isatty()


def _box(title: str, lines: list[str], color: str = Color.CYAN) -> str:
    """Draw a bordered card around content."""
    all_lines = [title] + lines
    width = max(len(_strip_ansi(l)) for l in all_lines) + 4
    width = max(width, 40)

    top = f"{color}╭{'─' * (width - 2)}╮{Color.RESET}"
    bottom = f"{color}╰{'─' * (width - 2)}╯{Color.RESET}"

    result = [top]
    for line in all_lines:
        visible_len = len(_strip_ansi(line))
        padding = width - visible_len - 4
        result.append(f"{color}│{Color.RESET} {line}{' ' * max(0, padding)} {color}│{Color.RESET}")
    result.append(bottom)

    return "\n".join(result)


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences for width calculation."""
    import re
    return re.sub(r"\033\[[0-9;]*m", "", text)


def _header() -> str:
    """Git-rescue header banner."""
    return (
        f"\n{Color.BOLD}{Color.BRIGHT_CYAN}"
        f"  ╔══════════════════════════════════════╗\n"
        f"  ║         🛟  git-rescue v{__version__}         ║\n"
        f"  ║     Zero-dependency Git recovery     ║\n"
        f"  ╚══════════════════════════════════════╝"
        f"{Color.RESET}\n"
    )


def cmd_timeline(client: GitClient, limit: int = 20) -> int:
    """Display colorized reflog timeline."""
    print(_header())
    print(f"  {Color.DIM}Scanning reflog for recent activity...{Color.RESET}\n")

    raw = client.reflog(limit=limit)
    if not raw:
        print(f"  {Color.YELLOW}No reflog entries found.{Color.RESET}")
        return 0

    entries = parse_reflog(raw)
    if not entries:
        print(f"  {Color.YELLOW}No parseable reflog entries.{Color.RESET}")
        return 0

    for i, entry in enumerate(entries):
        if entry.is_destructive:
            color = Color.BRIGHT_RED
            marker = "▸"
        elif entry.category in ("commit", "commit_amend"):
            color = Color.BRIGHT_GREEN
            marker = "●"
        elif entry.category in ("checkout",):
            color = Color.BRIGHT_CYAN
            marker = "◆"
        elif entry.category in ("rebase", "rebase_abort"):
            color = Color.BRIGHT_YELLOW
            marker = "◈"
        elif entry.category in ("merge", "merge_commit"):
            color = Color.MAGENTA
            marker = "◉"
        else:
            color = Color.WHITE
            marker = "○"

        idx_str = f"{Color.DIM}[{i}]{Color.RESET}"
        hash_str = f"{Color.DIM}{entry.hash[:8]}{Color.RESET}"
        summary_str = f"{color}{Color.BOLD}{entry.human_summary}{Color.RESET}"
        time_str = f"{Color.DIM}{entry.timestamp}{Color.RESET}"

        print(f"  {color}{marker}{Color.RESET} {idx_str} {hash_str}  {summary_str}")
        print(f"    {time_str}")

        if i < len(entries) - 1:
            print(f"  {Color.DIM}│{Color.RESET}")

    destructive_count = sum(1 for e in entries if e.is_destructive)
    if destructive_count:
        print(
            f"\n  {Color.BRIGHT_RED}{Color.BOLD}"
            f"⚠  {destructive_count} destructive operation(s) detected. "
            f"Run `git-rescue undo` to recover.{Color.RESET}"
        )

    print()
    return 0


def cmd_undo(client: GitClient) -> int:
    """Undo the last destructive operation."""
    print(_header())
    print(f"  {Color.DIM}Scanning for destructive operations...{Color.RESET}\n")

    result = undo_last_destructive(client)

    print(f"  {Color.DIM}Backup created: {result.backup_ref}{Color.RESET}")

    if not result.success:
        print(f"\n  {Color.YELLOW}ℹ  {result.message}{Color.RESET}\n")
        return 1

    card_lines = [
        f"{Color.BOLD}{result.message}{Color.RESET}",
        "",
        f"  Restored to: {Color.GREEN}{result.restored_to[:12]}{Color.RESET}",
        f"  Backup ref:  {Color.DIM}{result.backup_ref}{Color.RESET}",
    ]

    if result.diff_summary:
        card_lines.append("")
        card_lines.append(f"  {Color.BOLD}Changes recovered:{Color.RESET}")
        for diff_line in result.diff_summary.splitlines()[:10]:
            card_lines.append(f"    {diff_line}")

    print(_box("🛟  Recovery Complete", card_lines, Color.GREEN))
    print(
        f"\n  {Color.DIM}To undo this recovery, run: "
        f"git reset --hard {result.backup_ref}{Color.RESET}\n"
    )
    return 0


def cmd_branches(client: GitClient) -> int:
    """List and restore deleted branches."""
    print(_header())
    print(f"  {Color.DIM}Scanning for deleted branches...{Color.RESET}\n")

    deleted = list_deleted_branches(client)

    if not deleted:
        print(f"  {Color.YELLOW}ℹ  No deleted branches found in reflog.{Color.RESET}\n")
        return 0

    print(f"  {Color.BOLD}Found {len(deleted)} deleted branch(es):{Color.RESET}\n")

    for i, (name, hash_val, summary) in enumerate(deleted):
        card_lines = [
            f"  Branch:  {Color.BOLD}{Color.BRIGHT_CYAN}{name}{Color.RESET}",
            f"  Commit:  {Color.DIM}{hash_val[:12]}{Color.RESET}",
            f"  Info:    {summary}",
            "",
            f"  {Color.DIM}Restore with: git-rescue branches --restore {name}{Color.RESET}",
        ]
        print(_box(f"🌿 Deleted Branch [{i}]", card_lines, Color.YELLOW))
        print()

    return 0


def cmd_branches_restore(client: GitClient, branch_name: str) -> int:
    """Restore a specific deleted branch."""
    print(_header())

    deleted = find_deleted_branches(client)
    target = None
    for name, hash_val in deleted:
        if name == branch_name:
            target = (name, hash_val)
            break

    if target is None:
        print(
            f"  {Color.RED}✗ Branch '{branch_name}' not found in deleted branches.{Color.RESET}\n"
        )
        return 1

    result = restore_branch(client, target[0], target[1])

    print(f"  {Color.DIM}Backup created: {result.backup_ref}{Color.RESET}")

    if not result.success:
        print(f"\n  {Color.RED}✗ {result.message}{Color.RESET}\n")
        return 1

    card_lines = [
        f"  Branch:  {Color.BOLD}{Color.GREEN}{result.branch_name}{Color.RESET}",
        f"  Commit:  {Color.DIM}{result.commit_hash[:12]}{Color.RESET}",
        f"  Info:    {result.commit_summary}",
    ]
    print(_box("🛟  Branch Restored", card_lines, Color.GREEN))
    print()
    return 0


def cmd_files(client: GitClient) -> int:
    """Recover dangling blobs."""
    print(_header())
    print(f"  {Color.DIM}Running git fsck to find lost files...{Color.RESET}\n")

    result = recover_files(client)

    print(f"  {Color.DIM}Backup created: {result.backup_ref}{Color.RESET}")

    if not result.success:
        print(f"\n  {Color.YELLOW}ℹ  {result.message}{Color.RESET}\n")
        return 0

    print(
        f"\n  {Color.GREEN}{Color.BOLD}"
        f"🛟  Recovered {len(result.recovered_files)} file(s){Color.RESET}\n"
    )

    for record in result.recovered_files:
        preview = record.get("preview", "")
        card_lines = [
            f"  Hash:    {Color.DIM}{record['hash'][:12]}{Color.RESET}",
            f"  Size:    {record['size']} bytes",
            f"  Saved:   {Color.CYAN}{record['path']}{Color.RESET}",
        ]
        if preview:
            card_lines.append("")
            card_lines.append(f"  {Color.BOLD}Preview:{Color.RESET}")
            for preview_line in preview.splitlines()[:5]:
                card_lines.append(f"    {Color.DIM}{preview_line}{Color.RESET}")

        print(_box("📄 Recovered File", card_lines, Color.CYAN))
        print()

    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="git-rescue",
        description="🛟  Zero-dependency Git disaster recovery tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  git-rescue                    Show recent timeline\n"
            "  git-rescue timeline -n 30     Show 30 most recent events\n"
            "  git-rescue undo               Revert last destructive operation\n"
            "  git-rescue branches            Find and restore deleted branches\n"
            "  git-rescue files              Recover lost staged files\n"
        ),
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"git-rescue {__version__}",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        default=False,
        help="Disable colorized output",
    )

    subparsers = parser.add_subparsers(dest="command")

    timeline_parser = subparsers.add_parser(
        "timeline",
        help="Show colorized reflog timeline (default)",
    )
    timeline_parser.add_argument(
        "-n", "--limit",
        type=int,
        default=20,
        help="Number of entries to display (default: 20)",
    )

    subparsers.add_parser(
        "undo",
        help="Revert the last destructive git operation",
    )

    branches_parser = subparsers.add_parser(
        "branches",
        help="List and restore deleted branches",
    )
    branches_parser.add_argument(
        "--restore",
        metavar="BRANCH",
        help="Restore a specific deleted branch",
    )

    subparsers.add_parser(
        "files",
        help="Recover lost staged files from dangling blobs",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entrypoint."""
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                try:
                    stream.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass

    parser = build_parser()
    args = parser.parse_args(argv)

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

    command = args.command or "timeline"

    try:
        if command == "timeline":
            limit = getattr(args, "limit", 20)
            return cmd_timeline(client, limit=limit)
        elif command == "undo":
            return cmd_undo(client)
        elif command == "branches":
            restore_name = getattr(args, "restore", None)
            if restore_name:
                return cmd_branches_restore(client, restore_name)
            return cmd_branches(client)
        elif command == "files":
            return cmd_files(client)
        else:
            parser.print_help()
            return 0
    except GitError as exc:
        print(f"\n  {Color.RED}Git error: {exc}{Color.RESET}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(f"\n  {Color.DIM}Interrupted.{Color.RESET}")
        return 130


def cli_entry() -> None:
    """Entry point for the console_scripts setuptools hook."""
    sys.exit(main())
