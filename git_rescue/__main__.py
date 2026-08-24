"""Allow running as `python -m git_rescue`."""

import sys

from git_rescue.cli import main

if __name__ == "__main__":
    # sys.exit is required: without it the return value of main() is discarded and
    # `python -m git_rescue` always exits 0, hiding failures from scripts and CI.
    sys.exit(main())
