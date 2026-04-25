#!/usr/bin/env python3
# @dependency-start
# upstream design README.md shared automation index
# @dependency-end

"""Legacy entrypoint for the doc-test-implementation triplet validator."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).absolute().parent
sys.path.insert(0, str(SCRIPT_DIR))

from validation.triplet_validator import main as triplet_main


def main(argv: list[str] | None = None) -> int:
    """Run the canonical triplet validator."""
    del argv
    try:
        triplet_main()
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, int):
            return code
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
