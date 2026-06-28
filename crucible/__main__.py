"""``python -m crucible`` entry point."""

from __future__ import annotations

import sys

from crucible.cli import main

if __name__ == "__main__":
    sys.exit(main())
