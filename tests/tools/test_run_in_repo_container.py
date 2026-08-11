"""Focused tests for the repository-container lifecycle wrapper."""

# @dependency-start
# contract test
# responsibility Verifies repository-container parsing preserves parent workspace ownership and rejects retained task images.
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md parent-owned container lifecycle boundary
# upstream implementation ../../tools/ci/run_in_repo_container.py owns repository-container orchestration
# upstream implementation ../../tools/ci/container_runtime.py owns lifecycle receipts, scoped images, and cleanup
# @dependency-end

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
from tools.ci import container_runtime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER = PROJECT_ROOT / "tools/ci/run_in_repo_container.py"


def load_runner() -> Any:
    """Load the runner with the same local runtime import as the CLI."""
    sys.modules["container_runtime"] = container_runtime
    spec = importlib.util.spec_from_file_location("test_run_in_repo_container", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parser_exposes_parent_workspace_and_rejects_keep_image() -> None:
    """Repository execution always cleans task-created images."""
    runner = load_runner()
    args = runner.build_parser().parse_args(["--workspace-root", "/workspace/parent", "--", "true"])

    assert args.workspace_root == "/workspace/parent"
    assert args.command == ["--", "true"]
    with pytest.raises(SystemExit):
        runner.build_parser().parse_args(["--keep-image"])