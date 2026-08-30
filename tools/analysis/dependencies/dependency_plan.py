#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Exposes the shared dependency planner under its neutral public name.
# upstream implementation ./devcontainer_dependencies.py contains the legacy-compatible implementation
# downstream implementation ../../bootstrap/container/image/Dockerfile installs the image plan
# downstream implementation ../../tools/validation/dependencies/docker_dependency_validator.sh validates the image plan
# @dependency-end
"""Public neutral name for the shared image dependency planner.

``devcontainer_dependencies`` remains an import-compatible implementation for
older integrations. New bootstrap, image, and LSP callers import this neutral
module so the public API does not imply ownership of a project editor or
development container. The implementation is deliberately re-exported rather
than copied.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

try:
    from tools.runtime.container import devcontainer_dependencies as _implementation
    from tools.runtime.container.devcontainer_dependencies import *  # noqa: F401,F403
except ImportError:  # direct script execution
    import tools.runtime.container.devcontainer_dependencies as _implementation  # type: ignore[no-redef]
    from tools.runtime.container.devcontainer_dependencies import *  # type: ignore[F401,F403]


def main(argv: list[str] | None = None) -> int:
    """Delegate CLI compatibility to the single planner implementation."""
    return _implementation.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
