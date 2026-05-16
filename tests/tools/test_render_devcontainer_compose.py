"""Tests for devcontainer Compose rendering helpers."""

# @dependency-start
# responsibility Tests shared devcontainer Compose renderer helper behavior.
# upstream implementation ../../tools/ci/render_devcontainer_compose.py renders devcontainer Compose files.
# upstream implementation ../../tools/ci/container_runtime.py defines runtime pack environment fields.
# @dependency-end

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_CI = PROJECT_ROOT / "tools" / "ci"
SCRIPT = TOOLS_CI / "render_devcontainer_compose.py"


def load_renderer() -> ModuleType:
    """Load the renderer module with its sibling imports on the module path."""
    sys.path.insert(0, str(TOOLS_CI))
    spec = importlib.util.spec_from_file_location("render_devcontainer_compose", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_compose_environment_line_renders_runtime_env_mapping() -> None:
    """Runtime pack env entries are forwarded as Compose environment mappings."""
    renderer = load_renderer()

    assert renderer.compose_environment_line("PYTHONPATH=/workspace/python") == (
        '      PYTHONPATH: "/workspace/python"'
    )


def test_default_project_name_is_repo_specific() -> None:
    """The default Compose project name includes the repo slug and path digest."""
    renderer = load_renderer()
    repo_root = Path("/tmp/Example Repo")
    digest = hashlib.sha1(str(repo_root).encode("utf-8")).hexdigest()[:8]

    assert renderer.default_project_name(repo_root) == f"example-repo-{digest}-devcontainer"
