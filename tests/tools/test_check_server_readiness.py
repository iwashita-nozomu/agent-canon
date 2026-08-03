# @dependency-start
# contract test
# responsibility Verifies server readiness does not assume a machine-local workspace path.
# upstream implementation ../../tools/ci/check_server_readiness.py host readiness collector
# upstream design ../../documents/contracts/server-host-contract.md explicit path/layout contract
# @dependency-end

"""Focused tests for optional host workspace readiness."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "ci" / "check_server_readiness.py"


def load_module():
    """Load the readiness module without relying on a repository package import."""
    spec = importlib.util.spec_from_file_location("check_server_readiness", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_workspace_readiness_is_skipped_without_explicit_host_path(monkeypatch) -> None:
    """No fixed /mnt/l/workspace path is probed by default."""
    module = load_module()
    monkeypatch.delenv("AGENT_CANON_HOST_WORKSPACE_ROOT", raising=False)
    monkeypatch.setattr(module, "parse_mounts", lambda: {})
    monkeypatch.setattr(module, "command_exists", lambda _name: False)
    monkeypatch.setattr(module, "run_optional", lambda _command: None)

    findings, _summary = module.collect_findings(None)

    assert not any("workspace_root" in finding.message for finding in findings)
    assert not any("/mnt/l/workspace" in finding.message for finding in findings)


def test_workspace_readiness_uses_explicit_environment_path(monkeypatch, tmp_path: Path) -> None:
    """An explicitly selected host workspace path remains observable."""
    module = load_module()
    monkeypatch.setenv("AGENT_CANON_HOST_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(module, "parse_mounts", lambda: {})
    monkeypatch.setattr(module, "command_exists", lambda _name: False)
    monkeypatch.setattr(module, "run_optional", lambda _command: None)

    findings, _summary = module.collect_findings(None)

    assert any("workspace_root exists" in finding.message for finding in findings)
