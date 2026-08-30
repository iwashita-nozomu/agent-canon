"""Regression tests for fail-closed graph selector runtime ownership."""

# @dependency-start
# contract test
# responsibility Verifies graph selector staging and receipts use explicit external roots.
# upstream implementation ../../tools/validation/ci/checks/agent_canon_pr_graph_selector.py owns graph selector boundaries
# upstream implementation ../../tools/runtime/artifacts/runtime_artifacts.py owns runtime artifact paths
# @dependency-end

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from tools.validation.ci.checks import agent_canon_pr_graph_selector as selector

ROOT = Path(__file__).resolve().parents[2]


def test_graph_staging_requires_explicit_runtime_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing runtime capability fails before any source-local staging."""
    monkeypatch.delenv("AGENT_CANON_RUNTIME_ROOT", raising=False)
    with pytest.raises(selector.ParentRootSideEffectError) as raised:
        selector._selector_temp_dir(ROOT)  # pyright: ignore[reportPrivateUsage]
    assert raised.value.reject is selector.ParentRootReject.RUNTIME_ROOT_REQUIRED


def test_graph_staging_is_below_explicit_runtime_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Staging is published only under the caller-selected runtime root."""
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("AGENT_CANON_RUNTIME_ROOT", str(runtime))
    staging = Path(selector._selector_temp_dir(ROOT))  # pyright: ignore[reportPrivateUsage]
    assert staging.is_relative_to(runtime)
    assert not staging.is_relative_to(ROOT)


def test_graph_cli_emits_fail_closed_receipt_when_runtime_is_missing() -> None:
    """Boundary errors are typed graph receipts rather than tracebacks."""
    base = subprocess.check_output(
        ["git", "rev-parse", "HEAD^"], cwd=ROOT, text=True
    ).strip()
    environment = os.environ.copy()
    environment.pop("AGENT_CANON_RUNTIME_ROOT", None)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/validation/ci/checks/agent_canon_pr_graph_selector.py"),
            "--root",
            str(ROOT),
            "--source-root",
            str(ROOT),
            "--trusted-base-sha",
            base,
            "--changed-path-packet",
            str(ROOT.parent / "graph-runtime-boundary-packet.json"),
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "AGENT_CANON_PR_DEPENDENCY_GRAPH=fail" in result.stdout
    assert "parent_boundary_runtime_root_required" in result.stdout
