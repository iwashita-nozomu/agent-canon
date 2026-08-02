# @dependency-start
# contract test
# responsibility Tests AgentCanon latest command TODO routing in small focused fixtures.
# upstream design ../../tools/README.md documents the high-level AgentCanon latest route.
# upstream implementation ../../tools/update_agent_canon.sh routes pending parent-repo TODOs.
# upstream implementation ../../tools/agent_tools/agent_canon_update_todos.py defines TODO tool output.
# upstream implementation ../../tests/tools/test_update_agent_canon.py provides submodule update fixtures.
# @dependency-end

"""Focused tests for AgentCanon latest TODO routing."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from tests.tools.test_update_agent_canon import (
    SubmoduleUpdateAgentCanonTest,
    authorized_test_env,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
from update_lifecycle_contract import materialize_gate_verdict  # noqa: E402


def lifecycle_binding() -> dict[str, object]:
    """Return one fixed G4/G5 consumer identity."""
    return {
        "transaction_id": "tx:" + "1" * 64,
        "snapshot_id": "snapshot:" + "2" * 64,
        "candidate_sha": "3" * 40,
        "tree_sha": "4" * 40,
        "input_digest": "sha256:" + "5" * 64,
        "tool_id": "agent-canon-latest",
        "tool_version": "test.v1",
        "evidence_ref": "evidence:" + "6" * 64,
        "evidence_digest": "sha256:" + "7" * 64,
        "timing": {
            "started_at": "2026-07-18T00:00:00Z",
            "finished_at": "2026-07-18T00:00:00Z",
            "last_attempt_at": "2026-07-18T00:00:00Z",
            "duration_ms": 0,
            "attempt": 1,
            "replayed": False,
        },
    }


def test_latest_consumes_g4_g5_receipts_without_rechecking_source(tmp_path: Path) -> None:
    """The downstream latest gate trusts one ordered projection/readback bundle."""
    binding = lifecycle_binding()
    g4 = materialize_gate_verdict(
        binding=binding,
        gate_id="G4",
        ordered_input_evidence_refs=["evidence:" + "8" * 64],
        invariant="parent_projection_integrity",
        output_digest="sha256:" + "9" * 64,
        owner=str(PROJECT_ROOT / "tools" / "update_agent_canon.sh") + "#accept_dependency_frontier",
        verdict="pass",
    )
    g5 = materialize_gate_verdict(
        binding=binding,
        gate_id="G5",
        ordered_input_evidence_refs=[g4["binding"]["evidence_ref"]],
        invariant="remote_publication_readback",
        output_digest="sha256:" + "a" * 64,
        owner=str(PROJECT_ROOT / "tools" / "agent_tools" / "publication_integrator.py")
        + "#integrate_publication",
        verdict="pass",
    )
    bundle = tmp_path / "g4-g5.json"
    bundle.write_text(json.dumps({"gate_verdicts": [g4, g5]}), encoding="utf-8")

    result = subprocess.run(
        ["bash", "tools/ci/check_agent_canon_latest.sh"],
        cwd=PROJECT_ROOT,
        env={**os.environ, "AGENT_CANON_LATEST_GATE_BUNDLE": str(bundle)},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "AGENT_CANON_LATEST_GATE_ORDER=G4,G5" in result.stdout
    assert "AGENT_CANON_LATEST_ROUTE=lifecycle_readback_receipt" in result.stdout
    assert "agent_canon_plan_route=" not in result.stdout


def test_latest_reports_pending_update_todos_without_failing(tmp_path: Path) -> None:
    """Pending parent-repo update TODOs route work without failing latest."""
    fixture = SubmoduleUpdateAgentCanonTest(
        methodName="test_ensure_latest_reports_already_current_submodule"
    )
    bare_repo, source = fixture.make_agent_canon_remote(tmp_path)
    repo = fixture.make_superproject(tmp_path, bare_repo)
    fixture.materialize_parent_projection_frontier(repo, source)
    todo_tool = repo / "tools" / "agent_tools" / "agent_canon_update_todos.py"
    todo_tool.parent.mkdir(parents=True, exist_ok=True)
    todo_tool.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import sys",
                "if sys.argv[1:] == ['plan', '--write']:",
                "    print('AGENT_CANON_UPDATE_TODO_PENDING_COUNT=1')",
                "    print('AGENT_CANON_UPDATE_TODO_PENDING=ACUT-test')",
                "    raise SystemExit(0)",
                "if sys.argv[1:] == ['acknowledge']:",
                "    print('unexpected acknowledge')",
                "    raise SystemExit(0)",
                "raise SystemExit(1)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    todo_tool.chmod(0o755)

    latest = subprocess.run(
        ["bash", "tools/update_agent_canon.sh", "latest"],
        cwd=repo,
        env=authorized_test_env(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert latest.returncode == 0, latest.stdout + latest.stderr
    assert "AGENT_CANON_UPDATE_TODO_PENDING_COUNT=1" in latest.stdout
    assert "AGENT_CANON_LATEST_TODOS=pending" in latest.stdout
    assert "AGENT_CANON_LATEST_TOOL_RESULT=updated_with_pending_todos" in latest.stdout
    assert "NEXT_ACTION=apply_agent_canon_update_todos_then_rerun_latest" in latest.stdout
    assert "unexpected acknowledge" not in latest.stdout

    frontier = json.loads(
        (
            repo
            / ".agent-canon"
            / "update-lifecycle"
            / "projection-queue"
            / "frontier.accepted.json"
        ).read_text(encoding="utf-8")
    )
    marker = json.loads(
        (
            repo / ".agent-canon" / "update-lifecycle" / "state" / "current-transaction"
        ).read_text(encoding="utf-8")
    )
    assert frontier["frontier_state"] == "accepted"
    assert marker["frontier_id"] == frontier["frontier_id"]


def _run_source_tools_root(repo: Path) -> tuple[int, str]:
    """Return agent-canon source-tools root status and emitted output."""
    command = (
        "source tools/lib/repo_paths.sh; "
        "agent_canon_source_tools_root .; "
        "status=$?; "
        "printf '%s\\n' \"__agent_canon_source_tools_root_status=${status}\";"
    )
    run = subprocess.run(
        ["bash", "-lc", command],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    status = 1
    emitted_lines: list[str] = []
    for line in run.stdout.splitlines():
        if line.startswith("__agent_canon_source_tools_root_status="):
            status = int(line.split("=", 1)[1] or 0)
        else:
            emitted_lines.append(line)
    return status, "\n".join(emitted_lines).strip()


def _copy_files_with_overlay(source_dir: Path, target_dir: Path) -> None:
    """Copy missing files recursively while preserving any existing target overrides."""
    for entry in source_dir.iterdir():
        target_entry = target_dir / entry.name
        if entry.is_dir():
            target_entry.mkdir(parents=True, exist_ok=True)
            _copy_files_with_overlay(entry, target_entry)
        else:
            shutil.copy2(entry, target_entry)


def _build_base_parent_fixture(tmp_root: Path) -> tuple[Path, Path, SubmoduleUpdateAgentCanonTest]:
    """Create a derived parent fixture and return its base paths plus helper object."""
    root = tmp_root / "parent"
    root.mkdir(parents=True, exist_ok=True)
    parent_dir = root
    bare_repo, source = SubmoduleUpdateAgentCanonTest(
        "test_update_modes_require_all_inline_git_authority_before_side_effects"
    ).make_agent_canon_remote(tmp_root / "agent-canon")
    helper = SubmoduleUpdateAgentCanonTest(
        "test_update_modes_require_all_inline_git_authority_before_side_effects"
    )
    repo = helper.make_superproject(parent_dir, bare_repo)
    return repo, source, helper


def _make_parent_with_tools_projection_with_fallback(tmp_root: Path) -> tuple[Path, SubmoduleUpdateAgentCanonTest]:
    """Create a derived parent with parent-local fallback script present."""
    repo, _source, helper = _build_base_parent_fixture(tmp_root)
    parent_tool_root = repo / "tools"
    fallback_sync = parent_tool_root / "sync_agent_canon.sh"
    fallback_sync.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "echo \"AGENT_CANON_SOURCE_TOOLS_ROOT_FALLBACK_EXECUTED\"",
                "exit 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fallback_sync.chmod(0o755)
    return repo, helper


def _make_parent_with_tools_projection_with_submodule(
    tmp_root: Path,
    *,
    init_submodule: bool,
) -> tuple[Path, SubmoduleUpdateAgentCanonTest]:
    """Create a derived parent projection with optional submodule checkout."""
    repo, helper = _make_parent_with_tools_projection_with_fallback(tmp_root)
    if init_submodule:
        init_output = subprocess.run(
            [
                "git",
                "-c",
                "protocol.file.allow=always",
                "submodule",
                "update",
                "--init",
                "--recursive",
                "vendor/agent-canon",
            ],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
        assert init_output.returncode == 0, init_output.stdout + init_output.stderr
        vendor_tool_root = repo / "vendor" / "agent-canon" / "tools"
        vendor_tool_root.mkdir(parents=True, exist_ok=True)
        required_tool_files = [
            "sync_agent_canon.sh",
            "update_agent_canon.sh",
            "rebuild_agent_tools.sh",
        ]
        for required_name in required_tool_files:
            source_file = PROJECT_ROOT / "tools" / required_name
            target_file = vendor_tool_root / required_name
            if not target_file.exists():
                shutil.copy2(source_file, target_file)
        for source_dir_name in ["lib", "ci", "agent_tools", "shared"]:
            source_dir = PROJECT_ROOT / "tools" / source_dir_name
            target_dir = vendor_tool_root / source_dir_name
            if not target_dir.exists():
                shutil.copytree(source_dir, target_dir)
    if not init_submodule:
        shutil.rmtree(repo / "vendor" / "agent-canon")
    return repo, helper


def _make_parent_with_legacy_projection(tmp_root: Path) -> Path:
    """Create a legacy-style symlinked projection fixture."""
    repo, _helper = _make_parent_with_tools_projection_with_submodule(
        tmp_root, init_submodule=True
    )
    shutil.rmtree(repo / "tools", ignore_errors=True)
    (repo / "tools").mkdir()
    os.symlink(
        Path("../vendor/agent-canon/tools"),
        repo / "tools" / "agent-canon",
        target_is_directory=True,
    )
    legacy_ci = repo / "vendor" / "agent-canon" / "tools" / "ci"
    legacy_agent_tools = repo / "vendor" / "agent-canon" / "tools" / "agent_tools"
    shutil.rmtree(legacy_ci, ignore_errors=True)
    shutil.rmtree(legacy_agent_tools, ignore_errors=True)
    shutil.copytree(PROJECT_ROOT / "tools" / "ci", legacy_ci)
    shutil.copytree(PROJECT_ROOT / "tools" / "agent_tools", legacy_agent_tools)
    for asset in [
        "agents",
        "evidence",
        "tests",
        "documents",
        "rust",
        ".github",
        "Makefile",
        "responsibility-scope.toml",
        "validation",
        "tools/validation",
        "AGENTS.md",
        "ROOT_AGENTS.md",
        ".codex",
        "templates",
        "notes",
    ]:
        source_path = PROJECT_ROOT / asset
        target_path = repo / "vendor" / "agent-canon" / asset
        if target_path.exists():
            if target_path.is_dir():
                _copy_files_with_overlay(source_path, target_path)
            else:
                shutil.copy2(source_path, target_path)
            continue
        if source_path.is_dir():
            shutil.copytree(source_path, target_path)
        elif source_path.is_file():
            shutil.copy2(source_path, target_path)
    legacy_contract = repo / "vendor" / "agent-canon" / "documents" / "repo-structure-contract.toml"
    if not legacy_contract.exists():
        legacy_contract.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            PROJECT_ROOT / "documents" / "structure" / "repo-structure-contract.toml",
            legacy_contract,
        )
    legacy_root_file = repo / "AGENTS.md"
    if not legacy_root_file.exists():
        shutil.copy2(PROJECT_ROOT / "AGENTS.md", legacy_root_file)
    legacy_root_file = repo / "ROOT_AGENTS.md"
    if not legacy_root_file.exists():
        shutil.copy2(PROJECT_ROOT / "ROOT_AGENTS.md", legacy_root_file)
    legacy_codex_dir = repo / ".codex"
    if not legacy_codex_dir.exists():
        shutil.copytree(PROJECT_ROOT / ".codex", legacy_codex_dir)
    return repo


def test_source_tools_root_requires_checked_out_vendor_submodule(tmp_path: Path) -> None:
    """Vendor submodule must be checked out before parent-local sync fallback is allowed."""
    repo, _helper = _make_parent_with_tools_projection_with_submodule(
        tmp_path, init_submodule=False
    )
    status, combined = _run_source_tools_root(repo)
    assert status != 0
    assert (
        "AGENT_CANON_SOURCE_TOOLS_ROOT_BLOCKER=submodule_vendor_agent_canon_not_checked_out"
        in combined
    )
    assert "AGENT_CANON_SOURCE_TOOLS_ROOT_PREFIX=vendor/agent-canon" in combined
    assert "AGENT_CANON_SOURCE_TOOLS_ROOT_FALLBACK_EXECUTED" not in combined


def test_source_tools_root_prefers_checked_out_vendor_source_tools(tmp_path: Path) -> None:
    """Checked-out vendor submodule should resolve to vendor/agent-canon/tools."""
    repo, _helper = _make_parent_with_tools_projection_with_submodule(
        tmp_path, init_submodule=True
    )
    status, resolved = _run_source_tools_root(repo)
    assert status == 0
    assert "./vendor/agent-canon/tools" in resolved


def test_source_tools_root_prefers_vendor_tools_in_fresh_clone(tmp_path: Path) -> None:
    """Fresh clones should still resolve vendor/agent-canon/tools over parent fallback."""
    repo, _helper = _make_parent_with_tools_projection_with_submodule(
        tmp_path, init_submodule=True
    )
    fresh_root = tmp_path / "fresh-clone"
    clone = subprocess.run(
        ["git", "clone", "--no-local", str(repo), str(fresh_root)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert clone.returncode == 0, clone.stdout + clone.stderr
    fresh_env = os.environ.copy()
    fresh_env["GIT_ALLOW_PROTOCOL"] = "file"
    init = subprocess.run(
        [
            "git",
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "update",
            "--init",
            "--recursive",
            "vendor/agent-canon",
        ],
        cwd=fresh_root,
        check=False,
        capture_output=True,
        text=True,
        env=fresh_env,
    )
    assert init.returncode == 0, init.stdout + init.stderr
    fresh_vendor_root = fresh_root / "vendor" / "agent-canon"
    fresh_vendor_tools = fresh_vendor_root / "tools"
    if not fresh_vendor_tools.exists() or not (fresh_vendor_tools / "sync_agent_canon.sh").exists():
        fresh_vendor_root.mkdir(parents=True, exist_ok=True)
        fresh_vendor_tools.mkdir(parents=True, exist_ok=True)
        required_tool_files = [
            "sync_agent_canon.sh",
            "update_agent_canon.sh",
            "rebuild_agent_tools.sh",
        ]
        for required_name in required_tool_files:
            source_file = PROJECT_ROOT / "tools" / required_name
            target_file = fresh_vendor_tools / required_name
            if not target_file.exists():
                shutil.copy2(source_file, target_file)
        for source_dir_name in ["lib", "ci", "agent_tools", "shared"]:
            source_dir = PROJECT_ROOT / "tools" / source_dir_name
            target_dir = fresh_vendor_tools / source_dir_name
            if not target_dir.exists():
                shutil.copytree(source_dir, target_dir)
    (fresh_root / "tools").mkdir(parents=True, exist_ok=True)
    fallback_sync = fresh_root / "tools" / "sync_agent_canon.sh"
    fallback_sync.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "echo \"AGENT_CANON_SOURCE_TOOLS_ROOT_FALLBACK_EXECUTED\"",
                "exit 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fallback_sync.chmod(0o755)

    status, resolved = _run_source_tools_root(fresh_root)
    assert status == 0
    assert "AGENT_CANON_SOURCE_TOOLS_ROOT_FALLBACK_EXECUTED" not in resolved
    assert "./vendor/agent-canon/tools" in resolved


def test_latest_entrypoint_reaches_without_legacy_root_lib(tmp_path: Path) -> None:
    """Legacy legacy entrypoint should avoid removed root git_authority path."""
    repo = _make_parent_with_legacy_projection(tmp_path / "latest")
    result = subprocess.run(
        ["bash", "tools/agent-canon/ci/check_agent_canon_latest.sh"],
        cwd=repo,
        env={**os.environ, "PYTHONPATH": f"{repo}/tools/agent-canon/agent_tools"},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    combined = result.stdout + result.stderr
    assert "No such file or directory" not in combined
    assert "AGENT_CANON_LATEST=pass" in combined


def test_run_all_checks_reaches_agent_canon_cli_without_tools_bin(tmp_path: Path) -> None:
    """run_all_checks should resolve agent-canon CLI route without tools/bin dependency."""
    repo = _make_parent_with_legacy_projection(tmp_path / "all_checks")
    result = subprocess.run(
        [
            "bash",
            "tools/agent-canon/ci/run_all_checks.sh",
            "--quick",
            "--skip-docs",
            "--skip-github-workflows",
        ],
        cwd=repo,
        env={**os.environ},
        check=False,
        capture_output=True,
        text=True,
    )
    assert "No such file or directory" not in (result.stdout + result.stderr)
    combined = result.stdout + result.stderr
    assert "AGENT_CANON_CLI_MODE" in combined
    assert "AGENT_CANON_CLI_BLOCKER=agent_canon_cli_unavailable" not in combined
