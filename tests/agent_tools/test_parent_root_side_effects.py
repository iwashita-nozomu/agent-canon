# @dependency-start
# contract test
# responsibility Verifies authenticated parent capabilities, child state, publication, and exact cleanup.
# upstream implementation ../../tools/agent_tools/parent_root_side_effects.py owns parent-local filesystem effects
# downstream implementation ../../tools/agent_tools/fixture_spawn.py owns nested fixture mode selection
# @dependency-end

"""Focused tests for the parent-root side-effect boundary."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
import tools.agent_tools.fixture_spawn as fixture_spawn
import tools.agent_tools.parent_root_side_effects as side_effects
from tools.agent_tools import work_log, workflow_monitor
from tools.agent_tools.fixture_spawn import (
    bootstrap_fixture_public_environment,
    record_environment,
    record_session_from_environment,
    run_fixture_command,
)
from tools.agent_tools.parent_root_side_effects import (
    SCHEMA_SESSION_RECORD_V2,
    ParentRootAttestationRequest,
    ParentRootReject,
    ParentRootSideEffectBoundary,
    ParentRootSideEffectError,
    PublicExecOverrides,
    SessionResolutionError,
    SessionResolutionResult,
    attest_parent_root,
    current_supervisor_issuer,
    parse_session_record_v2,
    public_exec,
    public_session,
    resolve_parent_owned_path,
)

_PARENT_ROOT_SIDE_EFFECTS_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "agent_tools"
    / "parent_root_side_effects.py"
)

_PARENT_BOUNDARY_PATH_KEYS = (
    "TMPDIR",
    "TEMP",
    "TMP",
    "XDG_CACHE_HOME",
    "PYTHONPYCACHEPREFIX",
    "AGENT_CANON_TOOLS_HOME",
    "CARGO_HOME",
    "CARGO_TARGET_DIR",
    "AGENT_CANON_CLI_TARGET_DIR",
    "AGENT_CANON_PARENT_ROOT",
    "AGENT_CANON_PARENT_ROOT_DEV",
    "AGENT_CANON_PARENT_ROOT_INO",
    "AGENT_CANON_CHILD_HANDOFF",
    "AGENT_CANON_CHILD_PURPOSE",
    "AGENT_CANON_HANDOFF_AUDIENCE",
    "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
    "AGENT_CANON_ROOT",
    "AGENT_CANON_SOURCE_ROOT",
)


def _build_clean_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    for key in _PARENT_BOUNDARY_PATH_KEYS:
        env.pop(key, None)
    if overrides:
        env.update(overrides)
    for key in tuple(env):
        if key.startswith("AGENT_CANON_SIDE_EFFECT_"):
            env.pop(key, None)
    return env


@contextmanager
def _authenticated_cli_env(
    root: Path,
    *,
    purpose: str,
    base_env: dict[str, str] | None = None,
    rebase_inherited_temp: bool = False,
) -> Iterator[tuple[ParentRootSideEffectBoundary, SessionResolutionResult, dict[str, str]]]:
    """Build a session-authenticated child environment without ambient identity."""
    if not (root / ".git").exists():
        git_repo(root, remote="https://example.invalid/parent.git")
    invocation_script = root / ".agent-canon" / "cli-runner.py"
    invocation_script.parent.mkdir(parents=True, exist_ok=True)
    invocation_script.write_text("# authenticated CLI runner\n", encoding="utf-8")
    previous_cwd = Path.cwd()
    saved_environment = os.environ.copy()
    clean_environment = _build_clean_env(base_env)
    try:
        os.environ.clear()
        os.environ.update(clean_environment)
        os.chdir(root)
        with public_session(
            invocation_script=invocation_script,
            purpose=purpose,
            independent=True,
            cleanup_state=True,
        ) as session:
            boundary = ParentRootSideEffectBoundary()
            env = boundary.child_environment(
                session.attestation,
                clean_environment,
                issue_handoff=False,
                rebase_inherited_temp=rebase_inherited_temp,
            )
            assert "AGENT_CANON_PARENT_ROOT" not in env
            yield boundary, session, env
    finally:
        os.environ.clear()
        os.environ.update(saved_environment)
        os.chdir(previous_cwd)


def test_authenticated_cli_env_restores_parent_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The clean bootstrap does not leak its temporary process state."""
    git_repo(tmp_path, remote="https://example.invalid/clean-bootstrap.git")
    monkeypatch.setenv("AGENT_CANON_SIDE_EFFECT_PARENT_ROOT", "/ambient/parent")
    monkeypatch.setenv("AGENT_CANON_SIDE_EFFECT_SESSION_REQUIRED", "1")
    before_environment = os.environ.copy()
    before_cwd = Path.cwd()

    with _authenticated_cli_env(tmp_path, purpose="clean-bootstrap") as (_boundary, _session, env):
        assert os.environ != before_environment
        assert Path.cwd() == tmp_path.resolve()
        assert not any(key.startswith("AGENT_CANON_SIDE_EFFECT_") for key in os.environ)
        assert env[side_effects.SIDE_EFFECT_PARENT_ROOT_ENV] != "/ambient/parent"
        assert env[side_effects.SIDE_EFFECT_REQUIRED_ENV] == "1"

    assert os.environ == before_environment
    assert Path.cwd() == before_cwd


def git_repo(path: Path, *, remote: str | None = None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    if remote is not None:
        subprocess.run(["git", "-C", str(path), "remote", "add", "origin", remote], check=True)
    subprocess.run(["git", "-C", str(path), "-c", "user.name=Test", "-c",
                    "user.email=test@example.invalid", "commit", "--allow-empty",
                    "-m", "fixture"], check=True, capture_output=True)


def test_public_exec_typed_overrides_validate_owner_before_side_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Public execution accepts parent-local paths and rejects unsafe aliases early."""
    root = tmp_path / "parent"
    git_repo(root, remote="https://example.invalid/public-exec.git")
    invocation_script = root / ".agent-canon" / "invoke.py"
    invocation_script.parent.mkdir(parents=True)
    invocation_script.write_text("# public-exec test source\n", encoding="utf-8")
    monkeypatch.chdir(root)

    explicit_tools = root / "explicit-tools"
    explicit_cargo_home = root / "explicit-cargo-home"
    explicit_target = root / "explicit-target"
    explicit_cache = root / "explicit-cache"
    explicit_pycache = root / "explicit-pycache"
    for key in (
        "AGENT_CANON_TOOLS_HOME",
        "CARGO_HOME",
        "CARGO_TARGET_DIR",
        "AGENT_CANON_CLI_TARGET_DIR",
        "XDG_CACHE_HOME",
        "PYTHONPYCACHEPREFIX",
    ):
        monkeypatch.setenv(key, str(tmp_path / "runner-owned" / key))
    probe = root / "public-exec-probe.json"
    probe_code = (
        "import json, os, sys; "
        "from pathlib import Path; "
        "Path(sys.argv[1]).write_text(json.dumps({key: os.environ.get(key) for key in ("
        "'AGENT_CANON_TOOLS_HOME', 'CARGO_HOME', 'CARGO_TARGET_DIR', "
        "'AGENT_CANON_CLI_TARGET_DIR', 'XDG_CACHE_HOME', 'PYTHONPYCACHEPREFIX')}))"
    )
    accepted = public_exec(
        invocation_script=invocation_script,
        purpose="public-exec-typed-override",
        argv=(sys.executable, "-c", probe_code, str(probe)),
        explicit_overrides=PublicExecOverrides(
            tools_home=explicit_tools,
            cargo_home=explicit_cargo_home,
            cargo_target_dir=explicit_target,
            cli_target_dir=explicit_target,
            xdg_cache_home=explicit_cache,
            python_pycache_prefix=explicit_pycache,
        ),
    )
    assert accepted == 0
    values = json.loads(probe.read_text(encoding="utf-8"))
    assert Path(values["AGENT_CANON_TOOLS_HOME"]) == explicit_tools
    assert Path(values["CARGO_HOME"]) == explicit_cargo_home
    assert Path(values["CARGO_TARGET_DIR"]) == explicit_target
    assert Path(values["AGENT_CANON_CLI_TARGET_DIR"]) == explicit_target
    assert Path(values["XDG_CACHE_HOME"]) == explicit_cache
    assert Path(values["PYTHONPYCACHEPREFIX"]) == explicit_pycache
    for path in (
        explicit_tools,
        explicit_cargo_home,
        explicit_target,
        explicit_cache,
        explicit_pycache,
    ):
        assert path.is_dir()

    authenticated_parent = Path(
        os.environ.get(
            side_effects.SIDE_EFFECT_PARENT_ROOT_ENV,
            str(root),
        )
    ).resolve()
    outside = authenticated_parent.parent / (
        f"{authenticated_parent.name}-{tmp_path.name}-outside-tools"
    )
    with pytest.raises(ParentRootSideEffectError) as external_error:
        public_exec(
            invocation_script=invocation_script,
            purpose="public-exec-external-override",
            argv=(sys.executable, "-c", "raise SystemExit(99)"),
            explicit_overrides=PublicExecOverrides(tools_home=outside),
        )
    assert external_error.value.reject is ParentRootReject.ROOT_MISMATCH
    assert not outside.exists()

    mismatch_left = root / "mismatch-left"
    mismatch_right = root / "mismatch-right"
    with pytest.raises(ParentRootSideEffectError) as alias_error:
        public_exec(
            invocation_script=invocation_script,
            purpose="public-exec-target-alias",
            argv=(sys.executable, "-c", "raise SystemExit(99)"),
            explicit_overrides=PublicExecOverrides(
                cargo_target_dir=mismatch_left,
                cli_target_dir=mismatch_right,
            ),
        )
    assert alias_error.value.reject is ParentRootReject.ROOT_MISMATCH
    assert not mismatch_left.exists()
    assert not mismatch_right.exists()

    with pytest.raises(TypeError):
        PublicExecOverrides(tools_home=str(root / "string-not-path"))  # type: ignore[arg-type]


@contextmanager
def _record_fixture_session(
    parent: Path, fixture: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[SessionResolutionResult]:
    """Open one record result for the central fixture-direct facade tests."""
    previous_cwd = Path.cwd()
    if os.environ.get(side_effects.SIDE_EFFECT_PARENT_ROOT_ENV) or os.environ.get(
        side_effects.SIDE_EFFECT_HANDOFF_ENV
    ):
        os.chdir(fixture)
        try:
            with record_session_from_environment() as record:
                yield record
        finally:
            os.chdir(previous_cwd)
        return

    with _authenticated_cli_env(parent, purpose="fixture-direct-test") as (_boundary, _session, _env):
        issuer = current_supervisor_issuer()
        assert issuer is not None
        authenticated_cwd = Path.cwd()
        child = issuer.issue_child(
            role="record", record_id=f"fixture-record-{time.monotonic_ns()}",
            physical_root=parent, now_mono_ns=time.monotonic_ns(),
        )
        environment = {
            side_effects.SIDE_EFFECT_PARENT_ROOT_ENV: str(parent.resolve()),
            side_effects.SIDE_EFFECT_HANDOFF_ENV: child.handoff,
            side_effects.SIDE_EFFECT_REQUIRED_ENV: "1",
        }
        os.chdir(fixture)
        try:
            record = side_effects.resolve_parent_side_effect_session_v2(
                env=environment, observed_cwd=fixture.resolve(),
            )
            try:
                yield record
            finally:
                record.close()
        finally:
            os.chdir(authenticated_cwd)
            issuer.revoke_drain_child(
                child=child.child, reason="normal_exit",
                now_mono_ns=time.monotonic_ns(),
            )


def _explicit_fixture_capability(record: SessionResolutionResult) -> side_effects.RecordCapability:
    """Create the explicit adapter capability required by product/synthetic modes."""
    capability = side_effects.RecordCapability.from_record(record)
    capability.consume()
    return capability


def unborn_git_repo(path: Path, *, remote: str) -> None:
    """Create a standalone Git checkout whose owner has no commit yet."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "remote", "add", "origin", remote], check=True)


def commit_gitlink(parent: Path, source: Path, relative: str) -> None:
    """Commit a .gitmodules entry and an exact source gitlink in parent."""
    source_commit = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    subprocess.run(["git", "-C", str(parent), "add", ".gitmodules"], check=True)
    subprocess.run([
        "git", "-C", str(parent), "update-index", "--add", "--cacheinfo",
        f"160000,{source_commit},{relative}",
    ], check=True)
    subprocess.run([
        "git", "-C", str(parent), "-c", "user.name=Test", "-c",
        "user.email=test@example.invalid", "commit", "-m", "gitlink",
    ], check=True, capture_output=True)


def pending_handoff_nonces(root: Path) -> dict[str, object]:
    state = root / ".agent-canon" / "handoff" / "nonces.json"
    if not state.exists():
        return {}
    value = json.loads(state.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_public_session_accepts_unborn_standalone_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unborn standalone checkout remains its own public-session owner."""
    unborn_git_repo(tmp_path, remote="https://example.invalid/unborn.git")
    script = tmp_path / "runner.py"
    script.write_text("# public runner\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with public_session(invocation_script=script, purpose="unborn-standalone") as session:
        assert session.parent_root == tmp_path.resolve()
        assert session.attestation.parent_root == tmp_path.resolve()
        assert session.attestation.source_root is None


def test_public_session_keeps_committed_standalone_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A committed standalone checkout is not promoted to an arbitrary ancestor."""
    git_repo(tmp_path, remote="https://example.invalid/standalone.git")
    script = tmp_path / "runner.py"
    script.write_text("# public runner\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with public_session(invocation_script=script, purpose="committed-standalone") as session:
        assert session.parent_root == tmp_path.resolve()
        assert session.attestation.source_root is None


def test_public_session_promotes_exact_vendored_gitlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only an exact committed .gitmodules/gitlink relation promotes the parent."""
    parent = tmp_path / "parent"
    source = parent / "vendor" / "agent-canon"
    git_repo(parent, remote="https://example.invalid/parent.git")
    git_repo(source, remote="https://example.invalid/source.git")
    module = parent / ".gitmodules"
    module.write_text(
        '[submodule "vendor/agent-canon"]\n'
        '\tpath = vendor/agent-canon\n'
        '\turl = https://example.invalid/source.git\n',
        encoding="utf-8",
    )
    commit_gitlink(parent, source, "vendor/agent-canon")
    script = source / "runner.py"
    script.write_text("# public runner\n", encoding="utf-8")
    monkeypatch.chdir(source)

    with public_session(invocation_script=script, purpose="vendored-exact") as session:
        assert session.parent_root == parent.resolve()
        assert session.attestation.parent_root == parent.resolve()
        assert session.attestation.source_root == source.resolve()


def test_public_session_does_not_promote_unrelated_nested_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unrelated nested checkout remains independent of its outer repository."""
    parent = tmp_path / "parent"
    nested = parent / "nested"
    git_repo(parent, remote="https://example.invalid/parent.git")
    git_repo(nested, remote="https://example.invalid/nested.git")
    (parent / ".gitmodules").write_text(
        '[submodule "vendor/other"]\n'
        '\tpath = vendor/other\n'
        '\turl = https://example.invalid/other.git\n',
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(parent), "add", ".gitmodules"], check=True)
    subprocess.run([
        "git", "-C", str(parent), "-c", "user.name=Test", "-c",
        "user.email=test@example.invalid", "commit", "-m", "manifest",
    ], check=True, capture_output=True)
    script = nested / "runner.py"
    script.write_text("# public runner\n", encoding="utf-8")
    monkeypatch.chdir(nested)

    with public_session(invocation_script=script, purpose="nested-unrelated") as session:
        assert session.parent_root == nested.resolve()
        assert session.attestation.source_root is None


def test_v2_session_record_has_canonical_order_and_hmac(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Public bootstrap writes one signed v2 record with exact field order."""
    git_repo(tmp_path, remote="https://example.invalid/v2.git")
    script = tmp_path / "runner.py"
    script.write_text("# public runner\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with public_session(invocation_script=script, purpose="v2-schema") as session:
        assert session.record is not None
        assert session.record.schema == SCHEMA_SESSION_RECORD_V2
        assert session.record.role == "supervisor"
        key = tmp_path / ".agent-canon" / "runtime" / "side-effect-sessions-v2" / (
            f"issuer-{session.record.issuer_id}.key"
        )
        record = parse_session_record_v2(session.state_path.read_bytes(), key.read_bytes())
        assert tuple(record.as_mapping()) == side_effects.SESSION_RECORD_FIELDS
        assert record.transition_reason is None


def test_v2_parser_rejects_historical_v1_payload() -> None:
    """The superseded v1 transport cannot enter the v2 resolver."""
    with pytest.raises(SessionResolutionError, match="session_record_fields|v1_session_record_rejected"):
        parse_session_record_v2(
            '{"schema":"agent-canon.parent-side-effect-session.v1"}', b"k" * 32
        )


def test_v2_supervisor_horizon_and_nonce_are_immutable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Children inherit one issuer-owned deadline and stable nonce."""
    git_repo(tmp_path, remote="https://example.invalid/v2-horizon.git")
    script = tmp_path / "runner.py"
    script.write_text("# public runner\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with public_session(invocation_script=script, purpose="v2-horizon") as outer:
        issuer = current_supervisor_issuer()
        assert issuer is not None
        child = issuer.issue_child(
            role="record", record_id="horizon-record", physical_root=tmp_path,
            now_mono_ns=outer.record.issued_mono_ns + 1,
        )
        assert child.record.expires_mono_ns == outer.record.expires_mono_ns
        assert child.record.nonce == child.child.nonce
        with pytest.raises(SessionResolutionError, match="SESSION_HORIZON_MISMATCH"):
            side_effects._v2_issue_session(
                tmp_path, role="record", record_id="bad-horizon", root=tmp_path,
                now_mono_ns=outer.record.issued_mono_ns + 1,
                expires_mono_ns=outer.record.expires_mono_ns + 1,
                expected_expires_mono_ns=outer.record.expires_mono_ns,
                issuer_id=outer.record.issuer_id,
                issuer_key=side_effects._v2_read_key(outer.record),
            )
        issuer.revoke_drain_child(
            child=child.child, reason="normal_exit",
            now_mono_ns=child.record.issued_mono_ns + 1,
        )


def test_public_session_keeps_the_short_default_horizon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runner-only factory does not change public_session's 900-second TTL."""
    git_repo(tmp_path, remote="https://example.invalid/public-default-ttl.git")
    script = tmp_path / "runner.py"
    script.write_text("# public runner\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with public_session(invocation_script=script, purpose="public-default-ttl") as session:
        assert session.record.expires_mono_ns - session.record.issued_mono_ns == side_effects.SESSION_TTL_NS


def test_private_runner_factory_requires_marker_and_owns_exact_horizon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the runner marker opens the immutable four-hour supervisor session."""
    git_repo(tmp_path, remote="https://example.invalid/private-runner.git")
    script = tmp_path / "runner.py"
    script.write_text("# runner\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SessionResolutionError) as rejected:
        with side_effects._open_runner_session(object(), script):
            pass
    assert rejected.value.reject is ParentRootReject.INPUT_INVALID

    with side_effects._open_runner_session(side_effects._RUNNER_CALLER_MARKER, script) as (
        session,
        horizon,
    ):
        assert horizon.run_deadline_mono_ns - horizon.run_started_mono_ns == side_effects._RUNNER_HORIZON_NS
        assert session.record.expires_mono_ns == horizon.run_deadline_mono_ns
        issuer = current_supervisor_issuer()
        assert issuer is not None
        assert issuer.session.expires_mono_ns == horizon.run_deadline_mono_ns


def test_private_runner_factory_rejects_locked_horizon_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The private factory fails before yielding if its locked record drifts."""
    git_repo(tmp_path, remote="https://example.invalid/private-runner-mismatch.git")
    script = tmp_path / "runner.py"
    script.write_text("# runner\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    real_bootstrap = side_effects._v2_public_bootstrap

    def drifted_bootstrap(**kwargs: object) -> tuple[SessionResolutionResult, object]:
        result, issuer = real_bootstrap(**kwargs)  # type: ignore[arg-type]
        current = side_effects._v2_read_record(result.state_path, issuer._key)  # type: ignore[attr-defined]
        side_effects._v2_write_record(
            replace(current, expires_mono_ns=current.expires_mono_ns + 1),
            issuer._key,  # type: ignore[attr-defined]
        )
        return result, issuer

    monkeypatch.setattr(side_effects, "_v2_public_bootstrap", drifted_bootstrap)
    with pytest.raises(SessionResolutionError, match="SESSION_HORIZON_MISMATCH"):
        with side_effects._open_runner_session(side_effects._RUNNER_CALLER_MARKER, script):
            pass


def test_public_bootstrap_abort_runs_after_result_close_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed result close cannot skip removal of the issued session/key."""
    git_repo(tmp_path, remote="https://example.invalid/bootstrap-cleanup.git")
    monkeypatch.chdir(tmp_path)
    primary = SessionResolutionError(ParentRootReject.HANDOFF_INVALID, "injected bootstrap failure")

    def fail_open(**_kwargs: object) -> object:
        raise primary

    def fail_close(_result: SessionResolutionResult) -> None:
        raise RuntimeError("injected result close failure")

    monkeypatch.setattr(side_effects, "_open_supervisor_issuer", fail_open)
    monkeypatch.setattr(SessionResolutionResult, "close", fail_close)
    with pytest.raises(SessionResolutionError, match="bootstrap_cleanup_failed") as rejected:
        side_effects._v2_public_bootstrap(
            parent_root=tmp_path,
            purpose="bootstrap-cleanup-test",
            source_root=tmp_path,
        )

    assert rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED
    assert rejected.value.__cause__ is primary
    assert "injected result close failure" in rejected.value.detail
    session_root = side_effects._v2_session_root(tmp_path)
    assert not list(session_root.iterdir())


def test_fixture_direct_adapter_scrubs_identity_and_cleans_owned_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The record adapter binds CWD/root and owns fixture-local cleanup."""
    git_repo(tmp_path, remote="https://example.invalid/outer-v2.git")
    fixture = tmp_path / "fixture"
    git_repo(fixture, remote="https://example.invalid/fixture-v2.git")
    with _record_fixture_session(tmp_path, fixture, monkeypatch) as record:
        receipt = run_fixture_command(
            record=record,
            fixture_cwd=fixture,
            argv=(sys.executable, "-c", "import os; assert not any(k.startswith('AGENT_CANON_SIDE_EFFECT_') for k in os.environ); assert 'PYTHONPATH' not in os.environ"),
            now_mono_ns=time.monotonic_ns(),
        )
        assert receipt.returncode == 0
        assert receipt.cleanup.status == "clean"
        assert receipt.cleanup.created_paths == receipt.cleanup.removed_paths


def test_ordinary_public_projection_scrubs_private_transport_and_returns_mapping_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ordinary projection consumes private transport and exposes a distinct public token."""
    git_repo(tmp_path, remote="https://example.invalid/ordinary-private.git")
    fixture = tmp_path / "fixture"
    git_repo(fixture, remote="https://example.invalid/ordinary-fixture.git")
    with _record_fixture_session(tmp_path, fixture, monkeypatch) as record:
        capability = side_effects.RecordCapability(
            source="runner_private_record",
            record_id=f"{record.record.record_id}-private",
            parent_root=record.parent_root,
            handoff=record.handoff,
        )
        capability.consume()
        ambient = capability.transport_environment()
        request = side_effects.FixtureEnvironmentRequest(
            request_id="ordinary-private-receipt",
            mode="ordinary_tool",
            record_capability=capability,
            ambient_env=ambient,
            fixture_root=fixture,
        )
        child = side_effects.project_fixture_environment(record, request=request)
        try:
            assert isinstance(child, dict | side_effects.FixtureChildEnvironment)
            assert all(name not in child for name in capability.transport_env_names)
            assert child.receipt.public_projection_record_id != capability.record_id
            assert child.receipt.request_id == request.request_id
            assert child.receipt.mode == "ordinary_tool"
            assert child.receipt.capability_type == "runner_private_record_v2"
            assert child.receipt.capability_owner == "fixture_adapter"
            assert child.receipt.capability_scope == "fixture_child_environment"
            assert child.receipt.capability_consumed_exactly_once
            assert child.receipt.private_transport_absent_in_child
            assert child.receipt.public_projection_provenance == "ordinary_record"
            assert any(item.source == "private_transport" for item in child.receipt.input_provenance)
            assert dict(child)["CARGO_TARGET_DIR"] == str(child.receipt.effective_target)
        finally:
            child.close()
        assert child.receipt.sentinel_held_until_child_exit is False
        assert child.receipt.no_residue


def test_product_and_synthetic_modes_require_explicit_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Product and synthetic adapters never rediscover the outer record."""
    git_repo(tmp_path, remote="https://example.invalid/explicit-capability.git")
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    git_repo(source, remote="https://example.invalid/explicit-source.git")
    git_repo(fixture, remote="https://example.invalid/explicit-fixture.git")
    with _record_fixture_session(tmp_path, source, monkeypatch) as record:
        with pytest.raises(ParentRootSideEffectError, match="explicit record capability"):
            with bootstrap_fixture_public_environment(
                mode="product_fixture",
                record=record,
                fixture_cwd=fixture,
                argv=(sys.executable, "-c", "raise SystemExit(99)"),
            ):
                raise AssertionError("product mode unexpectedly yielded")
        with pytest.raises(ParentRootSideEffectError, match="explicit record capability"):
            with bootstrap_fixture_public_environment(
                mode="synthetic_tool", record=record, fixture_cwd=fixture
            ):
                raise AssertionError("synthetic mode unexpectedly yielded")


def test_product_receipt_contains_request_environment_and_cleanup_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Product execution returns the exact projector receipt without reconstruction."""
    git_repo(tmp_path, remote="https://example.invalid/product-receipt.git")
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    git_repo(source, remote="https://example.invalid/product-source.git")
    git_repo(fixture, remote="https://example.invalid/product-fixture.git")
    with _record_fixture_session(tmp_path, source, monkeypatch) as record:
        with bootstrap_fixture_public_environment(
            mode="product_fixture",
            record=record,
            record_capability=_explicit_fixture_capability(record),
            fixture_cwd=fixture,
            argv=(sys.executable, "-c", "import os; assert 'AGENT_CANON_PRIVATE_RECORD_HANDOFF' not in os.environ"),
        ) as product:
            assert product.receipt is not None
            assert product.receipt.environment.mode == "product_fixture"
            assert product.receipt.environment is product.receipt.environment
            assert product.receipt.environment.capability_record_id
            assert product.receipt.environment.private_transport_absent_in_child
            assert product.receipt.environment.cleanup_status == "clean"
            assert product.receipt.environment.sentinel_held_until_child_exit is False


def test_sentinel_identity_is_held_and_preexisting_marker_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The projector validates marker identity and removes only adapter-created state."""
    git_repo(tmp_path, remote="https://example.invalid/sentinel-parent.git")
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    git_repo(source, remote="https://example.invalid/sentinel-source.git")
    git_repo(fixture, remote="https://example.invalid/sentinel-fixture.git")
    marker = fixture / ".agent-canon" / "fixture-sentinel"
    marker.parent.mkdir()
    marker.write_text(f"{fixture.resolve()}\n", encoding="utf-8")
    original = marker.stat()
    with _record_fixture_session(tmp_path, source, monkeypatch) as record:
        request = side_effects.FixtureEnvironmentRequest(
            request_id="preexisting-sentinel",
            mode="synthetic_tool",
            record_capability=_explicit_fixture_capability(record),
            ambient_env={},
            fixture_root=fixture,
        )
        child = side_effects.project_fixture_environment(record, request=request)
        assert child.receipt.sentinel_preexisting
        assert child.receipt.sentinel_device == original.st_dev
        assert child.receipt.sentinel_inode == original.st_ino
        assert child.receipt.sentinel_held_until_child_exit
        child.close()
    assert marker.exists()
    assert marker.stat().st_ino == original.st_ino
    assert not child.receipt.sentinel_removed
    assert child.receipt.no_residue


def test_fixture_adapter_parent_lifecycle_interleaves_two_producers(
    tmp_path: Path,
) -> None:
    """Two independent sessions serialize child cleanup on one fixture parent."""
    fixture = tmp_path / "fixture"
    git_repo(fixture, remote="https://example.invalid/adapter-lifecycle.git")
    sentinel = fixture / ".agent-canon" / "fixture-sentinel"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text(f"{fixture.resolve()}\n", encoding="utf-8")
    runner = fixture / "producer-runner.py"
    runner.write_text("# lifecycle producer\n", encoding="utf-8")
    source_root = Path(__file__).resolve().parents[2]
    wrapper = r'''
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from tools.agent_tools.parent_root_side_effects import (
    FixtureEnvironmentRequest,
    RecordCapability,
    current_supervisor_issuer,
    project_fixture_environment,
    public_session,
    resolve_parent_side_effect_session_v2,
    SIDE_EFFECT_HANDOFF_ENV,
    SIDE_EFFECT_PARENT_ROOT_ENV,
    SIDE_EFFECT_REQUIRED_ENV,
)

fixture = Path(sys.argv[2])
ready = Path(sys.argv[3])
release = Path(sys.argv[4])
index = sys.argv[5]
runner = fixture / "producer-runner.py"
with public_session(
    invocation_script=runner,
    purpose=f"fixture-adapter-producer-{index}",
    independent=True,
    cleanup_state=True,
) as session:
    issuer = current_supervisor_issuer()
    assert issuer is not None
    child_session = issuer.issue_child(
        role="record",
        record_id=f"lifecycle-{index}-{time.monotonic_ns()}",
        physical_root=fixture,
        now_mono_ns=time.monotonic_ns(),
    )
    record = resolve_parent_side_effect_session_v2(
        env={
            SIDE_EFFECT_PARENT_ROOT_ENV: str(fixture),
            SIDE_EFFECT_HANDOFF_ENV: child_session.handoff,
            SIDE_EFFECT_REQUIRED_ENV: "1",
        },
        observed_cwd=fixture,
    )
    capability = RecordCapability.from_record(record)
    capability.consume()
    request = FixtureEnvironmentRequest(
        request_id=f"lifecycle-request-{index}",
        mode="ordinary_tool",
        record_capability=capability,
        ambient_env={},
        fixture_root=fixture,
    )
    projected = project_fixture_environment(record, request=request)
    begin = projected.receipt
    ready.write_text(
        json.dumps({
            "remaining_count": begin.adapter_remaining_count,
            "owned_root": str(begin.local_root),
        }),
        encoding="utf-8",
    )
    deadline = time.monotonic() + 15
    while not release.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("lifecycle release was not signaled")
        time.sleep(0.01)
    projected.close()
    end = projected.receipt
    print(
        json.dumps({
            "remaining_count": end.adapter_remaining_count,
            "shared_parent_absent": end.adapter_shared_parent_absent,
            "owned_root_absent": end.adapter_owned_root_absent,
            "registration_absent": end.adapter_registration_absent,
            "no_residue": end.no_residue,
        }),
        flush=True,
    )
    record.close()
    issuer.revoke_drain_child(
        child=child_session.child,
        reason="normal_exit",
        now_mono_ns=time.monotonic_ns(),
    )
'''

    def run_order(order: tuple[int, int]) -> list[dict[str, object]]:
        run_root = tmp_path / f"run-{order[0]}-{order[1]}"
        run_root.mkdir()
        processes: list[subprocess.Popen[str]] = []
        ready_paths: list[Path] = []
        release_paths: list[Path] = []
        for index in range(2):
            ready = run_root / f"ready-{index}"
            release = run_root / f"release-{index}"
            ready_paths.append(ready)
            release_paths.append(release)
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        wrapper,
                        str(source_root),
                        str(fixture),
                        str(ready),
                        str(release),
                        str(index),
                    ],
                    cwd=fixture,
                    env={
                        key: value
                        for key, value in os.environ.items()
                        if not key.startswith("AGENT_CANON_SIDE_EFFECT_")
                    },
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        try:
            deadline = time.monotonic() + 15
            while not all(path.exists() for path in ready_paths):
                if time.monotonic() >= deadline:
                    raise AssertionError("producer did not reach lifecycle begin")
                time.sleep(0.01)
            results: list[dict[str, object]] = []
            for index in order:
                release_paths[index].write_text("release\n", encoding="utf-8")
                output, error = processes[index].communicate(timeout=15)
                assert processes[index].returncode == 0, error
                lines = [line for line in output.splitlines() if line.strip()]
                results.append(json.loads(lines[-1]))
            return results
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    for order in ((0, 1), (1, 0)):
        results = run_order(order)
        assert results[0]["remaining_count"] == 1
        assert results[0]["shared_parent_absent"] is False
        assert results[0]["owned_root_absent"] is True
        assert results[0]["registration_absent"] is True
        assert results[0]["no_residue"] is True
        assert results[1]["remaining_count"] == 0
        assert results[1]["shared_parent_absent"] is True
        assert results[1]["owned_root_absent"] is True
        assert results[1]["registration_absent"] is True
        assert results[1]["no_residue"] is True
        assert not (fixture / ".agent-canon" / "fixture-adapter").exists()


def test_fixture_adapter_parent_lifecycle_rejects_shared_parent_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A replaced shared parent is preserved and rejected before child removal."""
    fixture = tmp_path / "fixture"
    git_repo(fixture, remote="https://example.invalid/adapter-replacement.git")
    with _record_fixture_session(fixture, fixture, monkeypatch) as record:
        lifecycle = side_effects.FixtureAdapterParentLifecycle(
            side_effects.ParentRootSideEffectBoundary(),
            record,
            fixture / ".agent-canon" / "fixture-adapter",
        )
        receipt = lifecycle.begin()
        shared_parent = receipt.shared_parent.physical_path
        replacement_target = fixture / ".agent-canon" / "fixture-adapter-original"
        shared_parent.rename(replacement_target)
        shared_parent.symlink_to(replacement_target, target_is_directory=True)
        try:
            with pytest.raises(
                ParentRootSideEffectError,
                match="identity changed|outside|symlink",
            ) as error:
                lifecycle.end()
            assert error.value.reject is ParentRootReject.ROOT_RACE_DETECTED
            assert shared_parent.is_symlink()
            assert replacement_target.is_dir()
            assert receipt.owned_root.physical_path.exists()
        finally:
            shared_parent.unlink()
            replacement_target.rename(shared_parent)


def test_fixture_bootstrap_modes_preserve_enclosing_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One record survives ordinary, product, and independent synthetic modes."""
    git_repo(tmp_path, remote="https://example.invalid/mode-parent.git")
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    git_repo(source, remote="https://example.invalid/mode-source.git")
    git_repo(fixture, remote="https://example.invalid/mode-fixture.git")
    with _record_fixture_session(tmp_path, source, monkeypatch) as record:
        source_cwd = Path.cwd()
        with bootstrap_fixture_public_environment(
            mode="ordinary_tool", record=record, fixture_cwd=fixture
        ) as ordinary:
            assert Path.cwd() == source_cwd
            assert ordinary.mode == "ordinary_tool"
            assert ordinary[side_effects.SIDE_EFFECT_HANDOFF_ENV]
        with bootstrap_fixture_public_environment(
            mode="product_fixture",
            record=record,
            record_capability=_explicit_fixture_capability(record),
            fixture_cwd=fixture,
            argv=(
                sys.executable,
                "-c",
                "import os; assert not any(k.startswith('AGENT_CANON_SIDE_EFFECT_') for k in os.environ); assert 'PYTHONPATH' not in os.environ",
            ),
        ) as product:
            assert Path.cwd() == source_cwd
            assert product.receipt is not None
            assert product.receipt.returncode == 0
        with bootstrap_fixture_public_environment(
            mode="synthetic_tool", record=record,
            record_capability=_explicit_fixture_capability(record), fixture_cwd=fixture
        ) as synthetic:
            assert Path.cwd() == source_cwd
            assert synthetic.session is not None
            assert synthetic[side_effects.SIDE_EFFECT_HANDOFF_ENV]
            assert synthetic["CARGO_TARGET_DIR"] == synthetic["AGENT_CANON_CLI_TARGET_DIR"]
            assert Path(synthetic["CARGO_TARGET_DIR"]).resolve().is_relative_to(
                fixture.resolve()
            )
            child = subprocess.run(
                [sys.executable, "-c", "import os; assert os.environ['AGENT_CANON_SIDE_EFFECT_SESSION_REQUIRED'] == '1'"],
                cwd=fixture,
                env=dict(synthetic),
                check=False,
            )
            assert child.returncode == 0
        with bootstrap_fixture_public_environment(
            mode="ordinary_tool", record=record, fixture_cwd=source_cwd
        ) as environment:
            assert environment[side_effects.SIDE_EFFECT_HANDOFF_ENV]


def test_fixture_bootstrap_preserves_contained_explicit_cargo_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing explicit Cargo target is accepted only beneath the fixture root."""
    git_repo(tmp_path, remote="https://example.invalid/explicit-target-parent.git")
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    git_repo(source, remote="https://example.invalid/explicit-target-source.git")
    git_repo(fixture, remote="https://example.invalid/explicit-target-fixture.git")
    explicit_target = fixture / ".agent-canon" / "cache" / "cargo-target"

    with _record_fixture_session(tmp_path, source, monkeypatch) as record:
        with bootstrap_fixture_public_environment(
            mode="synthetic_tool",
            record=record,
            record_capability=_explicit_fixture_capability(record),
            fixture_cwd=fixture,
            base_env={"CARGO_TARGET_DIR": str(explicit_target)},
            explicit_target_dir=explicit_target,
        ) as synthetic:
            assert synthetic["CARGO_TARGET_DIR"] == str(explicit_target)
            assert synthetic["AGENT_CANON_CLI_TARGET_DIR"] == str(explicit_target)
            assert not explicit_target.exists()

    assert not explicit_target.exists()


def test_fixture_environment_uses_contained_fake_bin_before_system_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicit fixture tools win while the environment remains parent-contained."""
    git_repo(tmp_path, remote="https://example.invalid/path-owner.git")
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    git_repo(source, remote="https://example.invalid/path-source.git")
    git_repo(fixture, remote="https://example.invalid/path-fixture.git")
    fake_bin = fixture / "fake-bin"
    fake_bin.mkdir()
    fake = fake_bin / "fixture-tool"
    fake.write_text("#!/bin/sh\nprintf fixture-first\n", encoding="utf-8")
    fake.chmod(0o700)

    with _record_fixture_session(tmp_path, source, monkeypatch) as record:
        with bootstrap_fixture_public_environment(
            mode="synthetic_tool",
            record=record,
            record_capability=_explicit_fixture_capability(record),
            fixture_cwd=fixture,
            explicit_path_entries=(str(fake_bin),),
        ) as environment:
            assert environment.child is not None
            evidence = environment.child.receipt
            assert evidence.accepted_path_entries == (str(fake_bin.resolve()),)
            assert evidence.dropped_path_entries == ()
            assert environment["PATH"].split(os.pathsep)[0] == str(fake_bin.resolve())
            assert subprocess.check_output(
                ["fixture-tool"], env=dict(environment), text=True
            ) == "fixture-first"


def test_fixture_environment_rejects_external_path_and_rebinds_parent_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """External PATH/TMP authority is rejected or rebound before child spawn."""
    git_repo(tmp_path, remote="https://example.invalid/env-owner.git")
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    git_repo(source, remote="https://example.invalid/env-source.git")
    git_repo(fixture, remote="https://example.invalid/env-fixture.git")
    external = tmp_path.parent / "external-fixture-env"
    inherited_tmp = external / "outer-tmp"
    sentinel = inherited_tmp / "sentinel"
    inherited_tmp.mkdir(parents=True)
    sentinel.write_text("keep\n", encoding="utf-8")
    before = os.environ.copy()

    with _record_fixture_session(tmp_path, source, monkeypatch) as record:
        with pytest.raises(SessionResolutionError) as rejected:
            with bootstrap_fixture_public_environment(
                mode="synthetic_tool",
                record=record,
                record_capability=_explicit_fixture_capability(record),
                fixture_cwd=fixture,
                base_env={
                    "AGENT_CANON_PARENT_TMPDIR": str(inherited_tmp),
                    "AGENT_CANON_PARENT_TMP_ROOT": str(inherited_tmp),
                },
                explicit_path_entries=(str(external),),
            ):
                raise AssertionError("external PATH unexpectedly accepted")
        assert rejected.value.reject is ParentRootReject.ROOT_MISMATCH
        assert "PATH_OUTSIDE_FIXTURE" in rejected.value.detail

        with bootstrap_fixture_public_environment(
            mode="synthetic_tool",
            record=record,
            record_capability=_explicit_fixture_capability(record),
            fixture_cwd=fixture,
            base_env={
                "PATH": os.pathsep.join((str(external), "/usr/bin")),
                "AGENT_CANON_PARENT_TMPDIR": str(inherited_tmp),
                "AGENT_CANON_PARENT_TMP_ROOT": str(inherited_tmp),
            },
        ) as environment:
            assert environment.child is not None
            evidence = environment.child.receipt
            assert evidence.outer_sentinel == str(inherited_tmp)
            assert evidence.outer_sentinel_identity is not None
            assert evidence.outer_sentinel_unchanged
            assert evidence.dropped_path_entries == (str(external), "/usr/bin")
            assert "/opt/agent-canon-parent/vendor/agent-canon/test" not in environment["PATH"]
            assert evidence.parent_tmpdir.is_relative_to(fixture.resolve())
            assert environment["AGENT_CANON_PARENT_TMPDIR"] == str(evidence.parent_tmpdir)
            assert environment["TMPDIR"] == str(evidence.parent_tmpdir)
            assert environment["TEMP"] == str(evidence.parent_tmpdir)
            assert environment["TMP"] == str(evidence.parent_tmpdir)
            assert str(external) not in environment["PATH"].split(os.pathsep)

    assert os.environ == before
    assert sentinel.read_text(encoding="utf-8") == "keep\n"
    assert not (fixture / ".agent-canon" / "fixture-bootstrap").exists()


def test_fixture_bootstrap_rejects_external_cargo_target_before_synthetic_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An external target fails before synthetic publication or child-session spawn."""
    git_repo(tmp_path, remote="https://example.invalid/external-target-parent.git")
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    git_repo(source, remote="https://example.invalid/external-target-source.git")
    git_repo(fixture, remote="https://example.invalid/external-target-fixture.git")
    external_target = tmp_path / "external-cargo-target"
    write_calls: list[object] = []
    session_calls: list[object] = []
    original_write = fixture_spawn.ParentRootSideEffectBoundary.write_parent_owned_file
    original_session = fixture_spawn.public_session

    def track_write(*args: object, **kwargs: object) -> object:
        write_calls.append((args, kwargs))
        return original_write(*args, **kwargs)  # type: ignore[arg-type]

    def track_session(*args: object, **kwargs: object) -> object:
        session_calls.append((args, kwargs))
        return original_session(*args, **kwargs)  # type: ignore[arg-type]

    with _record_fixture_session(tmp_path, source, monkeypatch) as record:
        monkeypatch.setattr(
            fixture_spawn.ParentRootSideEffectBoundary,
            "write_parent_owned_file",
            track_write,
        )
        monkeypatch.setattr(fixture_spawn, "public_session", track_session)
        with pytest.raises(ParentRootSideEffectError) as rejected:
            with bootstrap_fixture_public_environment(
                mode="synthetic_tool",
                record=record,
                record_capability=_explicit_fixture_capability(record),
                fixture_cwd=fixture,
                base_env={"CARGO_TARGET_DIR": str(external_target)},
                explicit_target_dir=external_target,
            ):
                raise AssertionError("external target unexpectedly accepted")

    assert rejected.value.reject is ParentRootReject.ROOT_MISMATCH
    assert "outside fixture root" in rejected.value.detail
    assert not external_target.exists()
    assert not write_calls
    assert not session_calls
    assert not (fixture / ".agent-canon" / "fixture-bootstrap").exists()


def test_record_environment_reuses_testrunner_record_when_inherited() -> None:
    """The runner-provided record channel remains available to ordinary tools."""
    if not (
        os.environ.get(side_effects.SIDE_EFFECT_PARENT_ROOT_ENV)
        and os.environ.get(side_effects.SIDE_EFFECT_HANDOFF_ENV)
    ):
        pytest.skip("requires a testrunner-inherited record channel")
    with record_environment(cwd=Path.cwd()) as environment:
        assert environment[side_effects.SIDE_EFFECT_HANDOFF_ENV]


def test_fixture_bootstrap_accepts_pathlike_fixture_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The public facade accepts both concrete and os.PathLike fixture paths."""
    git_repo(tmp_path, remote="https://example.invalid/pathlike-parent.git")
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    git_repo(source, remote="https://example.invalid/pathlike-source.git")
    git_repo(fixture, remote="https://example.invalid/pathlike-fixture.git")

    class FixturePathLike:
        def __fspath__(self) -> str:
            return str(fixture)

    with _record_fixture_session(tmp_path, source, monkeypatch) as record:
        with bootstrap_fixture_public_environment(
            mode="ordinary_tool", record=record, fixture_cwd=FixturePathLike()
        ) as environment:
            assert environment.fixture_cwd == fixture.resolve()
            assert environment[side_effects.SIDE_EFFECT_HANDOFF_ENV]


def test_fixture_bootstrap_missing_invocation_cleans_local_residue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing synthetic invocation cannot strand its fixture bootstrap tree."""
    git_repo(tmp_path, remote="https://example.invalid/missing-parent.git")
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    git_repo(source, remote="https://example.invalid/missing-source.git")
    git_repo(fixture, remote="https://example.invalid/missing-fixture.git")
    missing = fixture / "missing-invocation.py"

    with _record_fixture_session(tmp_path, source, monkeypatch) as record:
        before_environment = os.environ.copy()
        before_cwd = Path.cwd()
        with pytest.raises(ParentRootSideEffectError, match="invocation script is missing"):
            with bootstrap_fixture_public_environment(
                mode="synthetic_tool", record=record,
                record_capability=_explicit_fixture_capability(record), fixture_cwd=fixture,
                invocation_script=missing,
            ):
                raise AssertionError("missing invocation unexpectedly yielded")
        assert Path.cwd() == before_cwd
        assert os.environ == before_environment
    assert not (fixture / ".agent-canon" / "fixture-bootstrap").exists()


def test_fixture_bootstrap_environment_failure_cleans_local_residue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Environment construction failure still removes the local bootstrap tree."""
    git_repo(tmp_path, remote="https://example.invalid/environment-parent.git")
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    git_repo(source, remote="https://example.invalid/environment-source.git")
    git_repo(fixture, remote="https://example.invalid/environment-fixture.git")

    def fail_environment(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("injected environment construction failure")

    monkeypatch.setattr(
        fixture_spawn, "fixture_child_environment_with_receipt", fail_environment
    )
    with _record_fixture_session(tmp_path, source, monkeypatch) as record:
        before_environment = os.environ.copy()
        before_cwd = Path.cwd()
        with pytest.raises(RuntimeError, match="environment construction failure"):
            with bootstrap_fixture_public_environment(
                mode="synthetic_tool", record=record,
                record_capability=_explicit_fixture_capability(record), fixture_cwd=fixture
            ):
                raise AssertionError("environment failure unexpectedly yielded")
        assert Path.cwd() == before_cwd
        assert os.environ == before_environment
    assert not (fixture / ".agent-canon" / "fixture-bootstrap").exists()


def test_fixture_bootstrap_write_failure_cleans_local_residue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invocation write failure still removes the local bootstrap tree."""
    git_repo(tmp_path, remote="https://example.invalid/write-parent.git")
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    git_repo(source, remote="https://example.invalid/write-source.git")
    git_repo(fixture, remote="https://example.invalid/write-fixture.git")

    def fail_write(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("injected invocation write failure")

    monkeypatch.setattr(
        fixture_spawn.ParentRootSideEffectBoundary,
        "write_parent_owned_file",
        fail_write,
    )
    with _record_fixture_session(tmp_path, source, monkeypatch) as record:
        before_environment = os.environ.copy()
        before_cwd = Path.cwd()
        with pytest.raises(RuntimeError, match="invocation write failure"):
            with bootstrap_fixture_public_environment(
                mode="synthetic_tool", record=record,
                record_capability=_explicit_fixture_capability(record), fixture_cwd=fixture
            ):
                raise AssertionError("write failure unexpectedly yielded")
        assert Path.cwd() == before_cwd
        assert os.environ == before_environment
    assert not (fixture / ".agent-canon" / "fixture-bootstrap").exists()


def test_fixture_bootstrap_session_failure_cleans_local_residue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Independent session failure cannot strand a clean synthetic bootstrap."""
    git_repo(tmp_path, remote="https://example.invalid/session-parent.git")
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    git_repo(source, remote="https://example.invalid/session-source.git")
    git_repo(fixture, remote="https://example.invalid/session-fixture.git")

    @contextmanager
    def fail_session(**_kwargs: object) -> Iterator[SessionResolutionResult]:
        raise RuntimeError("injected independent session failure")
        yield  # pragma: no cover

    monkeypatch.setattr(fixture_spawn, "public_session", fail_session)
    with _record_fixture_session(tmp_path, source, monkeypatch) as record:
        before_environment = os.environ.copy()
        before_cwd = Path.cwd()
        with pytest.raises(RuntimeError, match="independent session failure"):
            with bootstrap_fixture_public_environment(
                mode="synthetic_tool", record=record,
                record_capability=_explicit_fixture_capability(record), fixture_cwd=fixture
            ):
                raise AssertionError("session failure unexpectedly yielded")
        assert Path.cwd() == before_cwd
        assert os.environ == before_environment
    assert not (fixture / ".agent-canon" / "fixture-bootstrap").exists()


def test_fixture_bootstrap_yield_failure_cleans_local_residue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A consumer failure after yield still cleans the synthetic bootstrap."""
    git_repo(tmp_path, remote="https://example.invalid/yield-parent.git")
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    git_repo(source, remote="https://example.invalid/yield-source.git")
    git_repo(fixture, remote="https://example.invalid/yield-fixture.git")
    with _record_fixture_session(tmp_path, source, monkeypatch) as record:
        before_environment = os.environ.copy()
        before_cwd = Path.cwd()
        with pytest.raises(RuntimeError, match="injected yield failure"):
            with bootstrap_fixture_public_environment(
                mode="synthetic_tool", record=record,
                record_capability=_explicit_fixture_capability(record), fixture_cwd=fixture
            ):
                raise RuntimeError("injected yield failure")
        assert Path.cwd() == before_cwd
        assert os.environ == before_environment
    assert not (fixture / ".agent-canon" / "fixture-bootstrap").exists()


def test_fixture_bootstrap_source_cwd_replacement_reports_cleanup_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A replaced source CWD still cleans fixture state and reports both outcomes."""
    git_repo(tmp_path, remote="https://example.invalid/cwd-race-parent.git")
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    git_repo(source, remote="https://example.invalid/cwd-race-source.git")
    git_repo(fixture, remote="https://example.invalid/cwd-race-fixture.git")
    original_public_session = fixture_spawn.public_session

    @contextmanager
    def replacing_public_session(
        **kwargs: object,
    ) -> Iterator[SessionResolutionResult]:
        with original_public_session(**kwargs) as session:
            moved = source.with_name("source-replaced")
            source.rename(moved)
            source.mkdir()
            yield session

    with _record_fixture_session(tmp_path, source, monkeypatch) as record:
        monkeypatch.setattr(fixture_spawn, "public_session", replacing_public_session)
        with pytest.raises(
            ParentRootSideEffectError,
            match="fixture bootstrap restoration/cleanup outcome",
        ) as rejected:
            with bootstrap_fixture_public_environment(
                mode="synthetic_tool", record=record,
                record_capability=_explicit_fixture_capability(record), fixture_cwd=fixture
            ):
                raise AssertionError("replaced source CWD unexpectedly yielded")
        assert rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED
        assert "restoration=" in rejected.value.detail
        assert "cleanup=clean" in rejected.value.detail
    assert not (fixture / ".agent-canon" / "fixture-bootstrap").exists()
    assert Path.cwd() == Path(__file__).resolve().parents[2]


def test_fixture_bootstrap_refreshes_product_expiry_before_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Product mode rechecks expiry after fixture validation and before spawn."""
    git_repo(tmp_path, remote="https://example.invalid/expiry-parent.git")
    source = tmp_path / "source"
    fixture = tmp_path / "fixture"
    git_repo(source, remote="https://example.invalid/expiry-source.git")
    git_repo(fixture, remote="https://example.invalid/expiry-fixture.git")
    with _record_fixture_session(tmp_path, source, monkeypatch) as record:
        expires = record.record.expires_mono_ns
        before_cwd = Path.cwd()
        with pytest.raises(SessionResolutionError, match="FIXTURE_DIRECT_SESSION_EXPIRED"):
            with bootstrap_fixture_public_environment(
                mode="product_fixture", record=record,
                record_capability=_explicit_fixture_capability(record), fixture_cwd=fixture,
                argv=(sys.executable, "-c", "raise SystemExit(99)"),
                now_mono_ns=expires - 1,
                clock=lambda: expires,
            ):
                raise AssertionError("expired product unexpectedly yielded")
        assert Path.cwd() == before_cwd
    assert not (fixture / ".agent-canon" / "fixture-direct").exists()


def test_fixture_direct_adapter_rejects_missing_record_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fixture command requires the record capability and physical CWD."""
    git_repo(tmp_path, remote="https://example.invalid/outer-v2-exception.git")
    fixture = tmp_path / "fixture"
    git_repo(fixture, remote="https://example.invalid/fixture-v2-exception.git")
    with pytest.raises(SessionResolutionError, match="FIXTURE_DIRECT_SESSION_REQUIRED"):
        run_fixture_command(
            record=object(),  # type: ignore[arg-type]
            fixture_cwd=fixture,
            argv=(sys.executable, "-c", "raise SystemExit(99)"),
            now_mono_ns=time.monotonic_ns(),
        )


def attest(root: Path, **kwargs: object):
    git_repo(root, remote="https://example.invalid/parent.git")
    return ParentRootSideEffectBoundary().attest(
        ParentRootAttestationRequest(cwd=root, explicit_root=root, purpose="test", **kwargs)
    )


@contextmanager
def session_child_environment(
    root: Path,
    *,
    base_env: dict[str, str] | None = None,
    purpose: str = "child-test",
    rebase_inherited_temp: bool = False,
) -> Iterator[tuple[ParentRootSideEffectBoundary, SessionResolutionResult, dict[str, str]]]:
    """Bind child environment tests to one v2 session for their full lifetime."""
    if not (root / ".git").exists():
        git_repo(root)
    invocation_script = root / ".agent-canon" / "session-child-runner.py"
    invocation_script.parent.mkdir(parents=True, exist_ok=True)
    invocation_script.write_text("# authenticated fixture runner\n", encoding="utf-8")
    previous_cwd = Path.cwd()
    os.chdir(root)
    try:
        with public_session(invocation_script=invocation_script, purpose=purpose) as session:
            boundary = ParentRootSideEffectBoundary()
            environment = boundary.child_environment(
                session.attestation,
                base_env if base_env is not None else _build_clean_env(),
                issue_handoff=False,
                rebase_inherited_temp=rebase_inherited_temp,
            )
            yield boundary, session, environment
    finally:
        os.chdir(previous_cwd)


def test_attestation_binds_parent_source_and_clone_identities(tmp_path: Path) -> None:
    source = tmp_path / "vendor" / "agent-canon"
    clone = tmp_path / "workspace" / "topic" / "agent-canon"
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    git_repo(source, remote="https://example.invalid/source.git")
    git_repo(clone, remote="https://example.invalid/clone.git")
    module = tmp_path / ".gitmodules"
    module.write_text(
        "[submodule \"vendor/agent-canon\"]\n"
        "\tpath = vendor/agent-canon\n"
        "\turl = https://example.invalid/source.git\n", encoding="utf-8"
    )
    module_sha = hashlib.sha256(module.read_bytes()).hexdigest()
    source_commit = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    source_tree = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD^{tree}"], check=True, capture_output=True, text=True).stdout.strip()
    parent_repo_id = hashlib.sha256(
        f"{tmp_path.resolve()}\0https://example.invalid/parent.git".encode()
    ).hexdigest()
    subprocess.run([
        "git", "-C", str(tmp_path), "update-index", "--add", "--cacheinfo",
        f"160000,{source_commit},vendor/agent-canon",
    ], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c",
                    "user.email=test@example.invalid", "commit", "-m", "gitlink"],
                   check=True, capture_output=True)
    owner = tmp_path / "owner.json"
    owner_body = {
        "schema": "agent-canon.owner-evidence.v1", "parent_repo_id": parent_repo_id,
        "physical_parent": str(tmp_path), "module_path": "vendor/agent-canon",
        "remote_url": "https://example.invalid/parent.git", "observed_commit": source_commit,
        "observed_tree": source_tree,
    }
    owner_body["evidence_sha256"] = hashlib.sha256(
        json.dumps(owner_body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    owner.write_text(json.dumps({**owner_body}, sort_keys=True), encoding="utf-8")
    owner_sha = hashlib.sha256(owner.read_bytes()).hexdigest()
    marker = tmp_path / "marker.json"
    marker.write_text(json.dumps({
        "schema": "agent-canon.repository-topic.v2", "parent_repo_id": parent_repo_id,
        "topic_slug": "topic", "repo_name": "agent-canon", "clone_path": str(clone),
        "remote_url": "https://example.invalid/clone.git", "branch": "main",
        "owner_evidence_sha256": owner_sha, "source_commit": source_commit,
        "source_tree": source_tree, "created_at": "2026-08-10T00:00:00Z", "nonce": "nonce",
    }), encoding="utf-8")
    receipt = ParentRootSideEffectBoundary().attest(
        ParentRootAttestationRequest(
            cwd=tmp_path,
            explicit_root=tmp_path,
            source_root=source,
            clone_root=clone,
            topic_marker=marker,
            gitmodules=module,
            owner_evidence=owner,
            expected_module_digest=module_sha,
            purpose="test",
        )
    )
    assert receipt.status == "attested"
    assert receipt.root_kind == "topic"
    assert receipt.parent_root == tmp_path.resolve()
    assert (receipt.parent_dev, receipt.parent_ino) != (0, 0)
    request = ParentRootAttestationRequest(
        cwd=tmp_path, explicit_root=tmp_path, source_root=source, clone_root=clone,
        topic_marker=marker, gitmodules=module, owner_evidence=owner, purpose="test",
        expected_module_digest=module_sha,
    )
    marker_value = json.loads(marker.read_text(encoding="utf-8"))
    marker_value["branch"] = "tampered"
    marker.write_text(json.dumps(marker_value), encoding="utf-8")
    with pytest.raises(ParentRootSideEffectError) as marker_tamper:
        ParentRootSideEffectBoundary().attest(request)
    assert marker_tamper.value.reject is ParentRootReject.MARKER_INVALID
    marker.write_text(json.dumps({**marker_value, "branch": "main"}), encoding="utf-8")
    module.write_text(
        "[submodule \"vendor/agent-canon\"]\n"
        "\tpath = vendor/agent-canon\n"
        "\turl = https://example.invalid/tampered.git\n", encoding="utf-8"
    )
    with pytest.raises(ParentRootSideEffectError) as module_tamper:
        ParentRootSideEffectBoundary().attest(request)
    assert module_tamper.value.reject is ParentRootReject.MODULE_INVALID


def test_missing_and_spoofed_roots_are_typed(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    with pytest.raises(ParentRootSideEffectError) as missing:
        boundary.attest(
            ParentRootAttestationRequest(
                cwd=tmp_path / "missing", explicit_root=tmp_path / "missing", purpose="test"
            )
        )
    assert missing.value.reject is ParentRootReject.ROOT_MISSING
    outside = tmp_path.parent / "outside"
    outside.mkdir()
    with pytest.raises(ParentRootSideEffectError) as spoofed:
        boundary.attest(
            ParentRootAttestationRequest(
                cwd=outside, explicit_root=tmp_path, purpose="test"
            )
        )
    assert spoofed.value.reject is ParentRootReject.ROOT_SPOOFED


def test_arbitrary_directory_and_remote_spoof_are_rejected(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    with pytest.raises(ParentRootSideEffectError) as arbitrary:
        boundary.attest(ParentRootAttestationRequest(cwd=tmp_path, explicit_root=tmp_path, purpose="test"))
    assert arbitrary.value.reject is ParentRootReject.ROOT_MISMATCH
    git_repo(tmp_path, remote="https://example.invalid/actual.git")
    with pytest.raises(ParentRootSideEffectError) as remote:
        boundary.attest(ParentRootAttestationRequest(
            cwd=tmp_path, explicit_root=tmp_path, expected_remote="https://example.invalid/expected.git", purpose="test"
        ))
    assert remote.value.reject is ParentRootReject.MARKER_INVALID


def test_missing_module_digest_and_exact_bound_schema_are_rejected(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    module = tmp_path / ".gitmodules"
    module.write_text("[submodule \"vendor/agent-canon\"]\n", encoding="utf-8")
    digest = hashlib.sha256(module.read_bytes()).hexdigest()
    boundary = ParentRootSideEffectBoundary()
    with pytest.raises(ParentRootSideEffectError) as missing:
        boundary.attest(ParentRootAttestationRequest(
            cwd=tmp_path, explicit_root=tmp_path, gitmodules=module,
            expected_module_digest="0" * 64, purpose="test"
        ))
    assert missing.value.reject is ParentRootReject.MODULE_INVALID
    with pytest.raises(ParentRootSideEffectError) as absent:
        boundary.attest(ParentRootAttestationRequest(
            cwd=tmp_path, explicit_root=tmp_path,
            expected_module_digest=digest, purpose="test"
        ))
    assert absent.value.reject is ParentRootReject.MODULE_INVALID
    marker = tmp_path / "marker.json"
    marker.write_text('{"schema":"agent-canon.repository-topic.v2","schema":"duplicate"}', encoding="utf-8")
    with pytest.raises(ParentRootSideEffectError) as malformed:
        boundary.attest(ParentRootAttestationRequest(
            cwd=tmp_path, explicit_root=tmp_path, topic_marker=marker, purpose="test"
        ))
    assert malformed.value.reject is ParentRootReject.MARKER_INVALID
    assert digest != "0" * 64


def test_regular_nested_git_is_not_a_submodule_gitlink(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    nested = tmp_path / "vendor" / "nested"
    git_repo(nested, remote="https://example.invalid/nested.git")
    module = tmp_path / ".gitmodules"
    module.write_text(
        "[submodule \"vendor/nested\"]\n"
        "\tpath = vendor/nested\n"
        "\turl = https://example.invalid/nested.git\n", encoding="utf-8"
    )
    with pytest.raises(ParentRootSideEffectError) as rejected:
        ParentRootSideEffectBoundary().attest(ParentRootAttestationRequest(
            cwd=tmp_path, explicit_root=tmp_path, source_root=nested,
            gitmodules=module, purpose="module-check",
        ))
    assert rejected.value.reject is ParentRootReject.MODULE_INVALID


def test_handoff_forgery_and_cross_instance_replay_are_rejected(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    boundary = ParentRootSideEffectBoundary()
    token = boundary.issue_child_handoff(tmp_path, audience="test")
    request = ParentRootAttestationRequest(cwd=tmp_path, explicit_root=tmp_path, purpose="test", child_handoff_token=token)
    boundary.attest(request)
    with pytest.raises(ParentRootSideEffectError) as replay:
        ParentRootSideEffectBoundary().attest(request)
    assert replay.value.reject is ParentRootReject.HANDOFF_INVALID
    forged = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    with pytest.raises(ParentRootSideEffectError) as forgery:
        ParentRootSideEffectBoundary().attest(
            ParentRootAttestationRequest(cwd=tmp_path, explicit_root=tmp_path, purpose="test", child_handoff_token=forged)
        )
    assert forgery.value.reject is ParentRootReject.HANDOFF_INVALID


def test_handoff_nonce_receipt_survives_a_new_process(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    boundary = ParentRootSideEffectBoundary()
    token = boundary.issue_child_handoff(tmp_path, audience="process-test")
    code = (
        "from pathlib import Path; import sys; "
        "from tools.agent_tools.parent_root_side_effects import *; "
        "request=ParentRootAttestationRequest(cwd=Path(sys.argv[1]), explicit_root=Path(sys.argv[1]), "
        "purpose='process-test', child_handoff_token=sys.argv[2]); "
        "ParentRootSideEffectBoundary().attest(request)"
    )
    env = {
        **os.environ,
        "PYTHONPATH": str(Path.cwd()),
        "PYTHONPYCACHEPREFIX": str(Path.cwd().parent / "test-tmp" / "pycache"),
    }
    accepted = subprocess.run([sys.executable, "-c", code, str(tmp_path), token], env=env, check=False)
    assert accepted.returncode == 0
    replayed = subprocess.run([sys.executable, "-c", code, str(tmp_path), token], env=env, check=False)
    assert replayed.returncode != 0


def test_handoff_source_and_clone_bindings_are_symmetric(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    source = tmp_path / "source"
    git_repo(source, remote="https://example.invalid/source.git")
    boundary = ParentRootSideEffectBoundary()
    token_with_source = boundary.issue_child_handoff(
        tmp_path, audience="test", source_root=source
    )
    with pytest.raises(ParentRootSideEffectError) as unexpected_source:
        boundary.attest(ParentRootAttestationRequest(
            cwd=tmp_path,
            explicit_root=tmp_path,
            purpose="test",
            child_handoff_token=token_with_source,
        ))
    assert unexpected_source.value.reject is ParentRootReject.HANDOFF_INVALID

    token_without_source = boundary.issue_child_handoff(tmp_path, audience="test")
    with pytest.raises(ParentRootSideEffectError) as missing_source:
        boundary.attest(ParentRootAttestationRequest(
            cwd=tmp_path,
            explicit_root=tmp_path,
            source_root=source,
            purpose="test",
            child_handoff_token=token_without_source,
        ))
    assert missing_source.value.reject is ParentRootReject.HANDOFF_INVALID


def test_clone_target_is_exclusively_reserved_and_fd_bound(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "workspace" / "topic" / "agent-canon"
    handle = boundary.open_parent_owned_target(receipt, target, "clone-target")
    try:
        assert handle.physical_path == target
        assert handle.proc_path == f"/proc/self/fd/{handle.target_fd}"
        assert os.fstat(handle.target_fd).st_ino == handle.target_ino
        assert os.listdir(handle.target_fd) == []
        with pytest.raises(ParentRootSideEffectError) as collision:
            boundary.open_parent_owned_target(receipt, target, "clone-target")
        assert collision.value.reject is ParentRootReject.ROOT_RACE_DETECTED
    finally:
        handle.close()
    published = boundary.resolve_parent_owned_path(receipt, target, "clone-target")
    boundary.remove_parent_owned_tree(receipt, published, "clone-target-cleanup")
    assert not target.exists()


def test_tree_copy_uses_parent_owned_operations_and_preserves_exclusions(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    source = tmp_path / "source-tree"
    source.mkdir()
    (source / "keep.txt").write_text("keep\n", encoding="utf-8")
    (source / ".git").mkdir()
    (source / ".git" / "private").write_text("private\n", encoding="utf-8")
    target = tmp_path / "target-tree"
    target.mkdir()
    (target / "stale.txt").write_text("stale\n", encoding="utf-8")
    boundary.copy_parent_owned_tree(
        receipt, source, target, "tree-copy", exclude=(".git",)
    )
    assert (target / "keep.txt").read_text(encoding="utf-8") == "keep\n"
    assert not (target / "stale.txt").exists()
    assert not (target / ".git").exists()


def test_git_config_add_uses_inherited_boundary_file_and_reads_back(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    config = tmp_path / "config" / "safe.directory.gitconfig"
    published = boundary.git_config_add(
        receipt, config, "safe.directory", str(tmp_path / "child"), "git-config-test"
    )
    value = subprocess.run(
        ["git", "config", "--file", str(config), "--get", "safe.directory"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert value == str(tmp_path / "child")
    assert published.target_dev is not None
    assert published.target_ino is not None


def test_checkout_index_uses_boundary_staging_and_atomic_publish(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("from-index\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "tracked.txt"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "tracked",
        ],
        check=True,
        capture_output=True,
    )
    destination = tmp_path / "materialized" / "tracked.txt"
    published = boundary.checkout_index_parent_owned(
        receipt, tmp_path, "tracked.txt", destination, "checkout-index-test"
    )
    assert destination.read_text(encoding="utf-8") == "from-index\n"
    assert published.target_dev is not None
    assert published.target_ino is not None


def test_path_capability_accepts_in_root_symlink_and_rejects_escape(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "inside.txt"
    target.write_text("before", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    inside = boundary.resolve_parent_owned_path(receipt, link, "test")
    assert inside.physical_path == target
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("sentinel", encoding="utf-8")
    escaping = tmp_path / "escape.txt"
    escaping.symlink_to(outside)
    with pytest.raises(ParentRootSideEffectError) as rejected:
        resolve_parent_owned_path(receipt, escaping, "test")
    assert rejected.value.reject is ParentRootReject.SYMLINK_ESCAPE
    outside.unlink()


def test_remove_parent_owned_file_unlinks_directory_symlink_and_preserves_target(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "target-directory"
    target.mkdir()
    link = tmp_path / "tools-agent-canon"
    link.symlink_to(target, target_is_directory=True)
    capability = boundary.resolve_parent_owned_path(receipt, link, "lexical-link")

    boundary.remove_parent_owned_file(capability)

    assert not os.path.lexists(link)
    assert target.is_dir()


def test_remove_parent_owned_file_unlinks_direct_root_regular_file(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    regular = tmp_path / "direct-root-file"
    regular.write_text("remove me\n", encoding="utf-8")
    capability = boundary.resolve_parent_owned_path(receipt, regular, "regular-file")

    boundary.remove_parent_owned_file(capability)

    assert not regular.exists()


def test_remove_parent_owned_file_unlinks_broken_in_root_symlink(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    link = tmp_path / "broken-link"
    link.symlink_to("missing-target")
    capability = boundary.resolve_parent_owned_path(receipt, link, "broken-link")
    assert capability.target_dev is None
    assert capability.lexical_link_target == "missing-target"

    boundary.remove_parent_owned_file(capability)

    assert not os.path.lexists(link)


def test_external_missing_target_symlink_is_rejected_and_preserved(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    outside = tmp_path.parent / "missing-outside-target"
    link = tmp_path / "external-broken-link"
    link.symlink_to(outside)
    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.resolve_parent_owned_path(receipt, link, "external-broken-link")
    assert rejected.value.reject is ParentRootReject.SYMLINK_ESCAPE
    assert os.path.lexists(link)


def test_lexical_symlink_replacement_is_rejected_without_removing_replacement(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    first_target = tmp_path / "first-target"
    second_target = tmp_path / "second-target"
    first_target.mkdir()
    second_target.mkdir()
    link = tmp_path / "replaced-link"
    link.symlink_to(first_target, target_is_directory=True)
    capability = boundary.resolve_parent_owned_path(receipt, link, "replacement-link")
    link.unlink()
    link.symlink_to(second_target, target_is_directory=True)

    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.remove_parent_owned_file(capability)

    assert rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED
    assert link.is_symlink()
    assert link.resolve() == second_target


def test_atomic_publish_and_child_environment_keep_home_unchanged(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    path = boundary.resolve_parent_owned_path(receipt, "reports/result.json", "report")
    boundary.atomic_publish(path, b"ok\n")
    assert path.physical_path.read_text(encoding="utf-8") == "ok\n"
    assert path.target_dev is None
    published = boundary.atomic_publish(path, b"updated\n")
    assert published.target_dev is not None
    assert published.target_ino is not None
    assert published.physical_path.read_text(encoding="utf-8") == "updated\n"
    original_home = os.environ.get("HOME")
    with session_child_environment(
        tmp_path,
        base_env={"HOME": original_home or ""},
        purpose="atomic-child-environment",
    ) as (_session_boundary, _session, env):
        assert env["HOME"] == (original_home or "")
        expected_tmp = (tmp_path / ".agent-canon" / "tmp").resolve()
        assert env["TMPDIR"] == str(expected_tmp)
        assert env["TEMP"] == str(expected_tmp)
        assert env["TMP"] == str(expected_tmp)
        for name in (
            "TMPDIR", "TEMP", "TMP",
            "XDG_CACHE_HOME", "PYTHONPYCACHEPREFIX", "AGENT_CANON_TOOLS_HOME",
            "CARGO_HOME", "CARGO_TARGET_DIR", "AGENT_CANON_CLI_TARGET_DIR",
        ):
            assert Path(env[name]).resolve().is_relative_to(tmp_path.resolve())
        assert env["CARGO_TARGET_DIR"] == env["AGENT_CANON_CLI_TARGET_DIR"]
        for name in (
            "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
            "AGENT_CANON_PARENT_ROOT",
            "AGENT_CANON_PARENT_ROOT_DEV",
            "AGENT_CANON_PARENT_ROOT_INO",
            "AGENT_CANON_SOURCE_ROOT",
            "AGENT_CANON_ROOT",
        ):
            assert name not in env
        assert env["AGENT_CANON_SIDE_EFFECT_PARENT_ROOT"] == str(tmp_path.resolve())
        assert env["AGENT_CANON_SIDE_EFFECT_HANDOFF"]


def test_path_only_helpers_release_resolution_leases_before_revoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Path validation helpers release receipts before the session is revoked."""
    git_repo(tmp_path, remote="https://example.invalid/v2-path-only.git")
    script = tmp_path / "runner.py"
    script.write_text("# runner\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with public_session(invocation_script=script, purpose="path-only") as session:
        work_path = work_log._parent_path(
            tmp_path / "work" / "work_log.md", "work-log", create=True
        )
        monitor_path = workflow_monitor._parent_path(
            tmp_path / "monitor" / "workflow_monitoring.md",
            "workflow-monitoring",
            create=True,
        )
        assert work_path == tmp_path / "work" / "work_log.md"
        assert monitor_path == tmp_path / "monitor" / "workflow_monitoring.md"
        assert not tuple(side_effects._v2_lease_dir(session.record).glob("*.json"))


def test_side_effect_session_revoke_drains_held_operation_lease(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/v2-drain.git")
    script = tmp_path / "runner.py"
    script.write_text("# runner\n", encoding="utf-8")
    boundary = ParentRootSideEffectBoundary()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    try:
        with public_session(invocation_script=script, purpose="drain-owner") as session:
            issuer = current_supervisor_issuer()
            assert issuer is not None
            child = issuer.issue_child(
                role="record", record_id="drain", physical_root=tmp_path,
                now_mono_ns=session.record.issued_mono_ns + 1,
            )
            held = side_effects.resolve_parent_side_effect_session_v2(
                env={
                    side_effects.SIDE_EFFECT_PARENT_ROOT_ENV: str(tmp_path),
                    side_effects.SIDE_EFFECT_HANDOFF_ENV: child.handoff,
                    side_effects.SIDE_EFFECT_REQUIRED_ENV: "1",
                },
                observed_cwd=tmp_path,
                now_mono_ns=child.record.issued_mono_ns + 1,
            )
            path = boundary.resolve_parent_owned_path(
                held.attestation, "drain-output.txt", "drain-write"
            )
            completed = threading.Event()

            def revoke() -> None:
                issuer.revoke_drain_child(
                    child=child.child, reason="normal_exit",
                    now_mono_ns=child.record.issued_mono_ns + 2,
                )
                completed.set()

            worker = threading.Thread(target=revoke)
            worker.start()
            time.sleep(0.05)
            assert not completed.is_set()
            boundary.atomic_publish(path, b"drain\n")
            worker.join(timeout=2)
            assert completed.is_set()
            held.close()
            assert not tuple(side_effects._v2_lease_dir(child.record).glob("*.json"))
    finally:
        monkeypatch.undo()


def test_legacy_authority_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    git_repo(tmp_path, remote="https://example.invalid/v2-legacy.git")
    for key in (
        "AGENT_CANON_SIDE_EFFECT_PARENT_ROOT",
        "AGENT_CANON_SIDE_EFFECT_HANDOFF",
        "AGENT_CANON_SIDE_EFFECT_SESSION_REQUIRED",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AGENT_CANON_PARENT_ROOT", str(tmp_path))
    request = ParentRootAttestationRequest(
        cwd=tmp_path, explicit_root=tmp_path, purpose="trusted-legacy-test"
    )
    with pytest.raises(ParentRootSideEffectError, match="v1_attest_parent_root_rejected"):
        attest_parent_root(request)
    child_environment = _build_clean_env({"AGENT_CANON_PARENT_ROOT": str(tmp_path)})
    child_environment["PYTHONPATH"] = str(Path(__file__).parents[2])
    rejected_subprocess = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; import os; "
                "from tools.agent_tools.parent_root_side_effects import "
                "ParentRootAttestationRequest, attest_parent_root; "
                "attest_parent_root(ParentRootAttestationRequest("
                "cwd=Path(os.environ['AGENT_CANON_PARENT_ROOT']), "
                "explicit_root=Path(os.environ['AGENT_CANON_PARENT_ROOT'])))"
            ),
        ],
        cwd=Path(__file__).parents[2],
        env=child_environment,
        capture_output=True,
        text=True,
    )
    assert rejected_subprocess.returncode != 0
    assert "v1_attest_parent_root_rejected" in rejected_subprocess.stderr
    child_environment.pop("AGENT_CANON_PARENT_ROOT")
    rejected_explicit_request = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "from tools.agent_tools.parent_root_side_effects import "
                "ParentRootAttestationRequest, attest_parent_root; "
                f"attest_parent_root(ParentRootAttestationRequest(cwd=Path({str(tmp_path)!r}), "
                f"explicit_root=Path({str(tmp_path)!r})))"
            ),
        ],
        cwd=Path(__file__).parents[2],
        env=child_environment,
        capture_output=True,
        text=True,
    )
    assert rejected_explicit_request.returncode != 0
    assert "v1_attest_parent_root_rejected" in rejected_explicit_request.stderr


def test_v2_canonical_channel_ignores_conflicting_legacy_selectors_and_scrubs_them(
    tmp_path: Path,
) -> None:
    """A valid signed channel wins over unsigned selectors and re-emits scrubbed state."""
    git_repo(tmp_path, remote="https://example.invalid/v2-conflicting-selectors.git")
    foreign_root = tmp_path / "foreign-root"
    foreign_root.mkdir()
    with session_child_environment(tmp_path, purpose="conflicting-selectors") as (
        _boundary, _session, environment
    ):
        environment.update(
            {
                "AGENT_CANON_PARENT_ROOT": str(foreign_root),
                "AGENT_CANON_PARENT_ROOT_DEV": "999",
                "AGENT_CANON_PARENT_ROOT_INO": "999",
                "AGENT_CANON_ACTIVE_REPOSITORY_ROOT": str(foreign_root),
                "AGENT_CANON_SOURCE_ROOT": str(foreign_root),
                "AGENT_CANON_ROOT": str(foreign_root),
                "AGENT_CANON_CHILD_HANDOFF": "unsigned-child-handoff",
                "AGENT_CANON_CHILD_PURPOSE": "unsigned-purpose",
                "AGENT_CANON_HANDOFF_AUDIENCE": "unsigned-audience",
            }
        )
        resolved = side_effects.resolve_parent_side_effect_session_v2(
            observed_cwd=tmp_path, env=environment
        )
        try:
            assert resolved.parent_root == tmp_path.resolve()
            scrubbed = side_effects._v2_session_environment(resolved, environment)
            assert scrubbed[side_effects.SIDE_EFFECT_PARENT_ROOT_ENV] == str(tmp_path.resolve())
            for key in (
                "AGENT_CANON_PARENT_ROOT",
                "AGENT_CANON_PARENT_ROOT_DEV",
                "AGENT_CANON_PARENT_ROOT_INO",
                "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
                "AGENT_CANON_SOURCE_ROOT",
                "AGENT_CANON_ROOT",
                "AGENT_CANON_CHILD_HANDOFF",
                "AGENT_CANON_CHILD_PURPOSE",
                "AGENT_CANON_HANDOFF_AUDIENCE",
            ):
                assert key not in scrubbed
        finally:
            resolved.close()


def test_v2_unsigned_legacy_and_partial_channels_have_typed_rejections(
    tmp_path: Path,
) -> None:
    """Legacy-only and incomplete canonical inputs never enter v2 auth."""
    git_repo(tmp_path, remote="https://example.invalid/v2-channel-classification.git")
    with pytest.raises(SessionResolutionError) as legacy:
        side_effects.resolve_parent_side_effect_session_v2(
            observed_cwd=tmp_path,
            env={"AGENT_CANON_PARENT_ROOT": str(tmp_path)},
        )
    assert legacy.value.reject is ParentRootReject.HANDOFF_INVALID
    assert legacy.value.detail == "legacy_authority_forbidden"

    with pytest.raises(SessionResolutionError) as partial:
        side_effects.resolve_parent_side_effect_session_v2(
            observed_cwd=tmp_path,
            env={
                side_effects.SIDE_EFFECT_PARENT_ROOT_ENV: str(tmp_path),
                "AGENT_CANON_PARENT_ROOT": str(tmp_path),
            },
        )
    assert partial.value.reject is ParentRootReject.HANDOFF_INVALID
    assert partial.value.detail == "session_channel_incomplete"


def test_cli_bootstraps_from_physical_cwd_when_channel_is_unset(tmp_path: Path) -> None:
    """A supported public CLI derives authority from its physical cwd."""
    git_repo(tmp_path, remote="https://example.invalid/v2-cli.git")
    target = tmp_path / "chosen-by-untrusted-cli.txt"
    env = _build_clean_env({"PYTHONPATH": str(Path(__file__).parents[2])})
    source_script = _PARENT_ROOT_SIDE_EFFECTS_SCRIPT
    result = subprocess.run(
            [
                sys.executable,
                str(source_script),
                "public-exec",
                "--invocation-script",
                str(source_script),
                "--purpose",
                "cli-unset-channel",
                "--",
                sys.executable,
                str(source_script),
                "write",
                "--root",
                str(tmp_path),
                "--candidate",
                str(target),
                "--purpose",
                "cli-write",
            ],
            cwd=tmp_path,
            input="must-not-write\n",
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    assert result.returncode == 0, result.stderr
    assert target.read_text(encoding="utf-8") == "must-not-write\n"


def test_stale_recovery_rejects_symlinked_session_directories(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/v2-symlink.git")
    script = tmp_path / "runner.py"
    script.write_text("# runner\n", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-side-effect-recovery-outside"
    outside.mkdir()
    marker = outside / "marker.json"
    marker.write_text("untouched", encoding="utf-8")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    with public_session(invocation_script=script, purpose="symlink-recovery") as _session:
        sessions_root = side_effects._v2_session_root(tmp_path)
        (sessions_root / "evil").symlink_to(outside, target_is_directory=True)
        assert side_effects.recover_v2_stale_sessions(tmp_path) == 0
        assert marker.read_text(encoding="utf-8") == "untouched"
    monkeypatch.undo()
    marker.unlink()
    outside.rmdir()


def test_all_inventory_writers_use_the_central_attestation_route() -> None:
    repo_root = Path(__file__).parents[2]
    inventory = frozenset(
        {
            "tools/agent_tools/agent_canon_update_todos.py",
            "tools/agent_tools/bootstrap_agent_run.py",
            "tools/agent_tools/check_agent_canon_log_policy.py",
            "tools/agent_tools/check_agent_runtime_alignment.py",
            "tools/agent_tools/dependency_module_change.py",
            "tools/agent_tools/devcontainer_dependencies.py",
            "tools/agent_tools/eval_accumulation_check.py",
            "tools/agent_tools/evaluate_agent_run.py",
            "tools/agent_tools/evaluate_codex_agent_roles.py",
            "tools/agent_tools/evaluate_report_quality.py",
            "tools/agent_tools/evaluate_skill_workflow_prompts.py",
            "tools/agent_tools/evaluate_workflow_selection.py",
            "tools/agent_tools/export_codex_runtime_summary.py",
            "tools/agent_tools/generate_agent_runtime_dashboard.py",
            "tools/agent_tools/git_dependency_diff_summary.py",
            "tools/agent_tools/github_publish.py",
            "tools/agent_tools/issue_sync.py",
            "tools/agent_tools/log_surface_inventory.py",
            "tools/agent_tools/manifest_rendering.py",
            "tools/agent_tools/prose_reasoning_graph.py",
            "tools/agent_tools/publication_integrator.py",
            "tools/agent_tools/reference_materializer.py",
            "tools/agent_tools/report_artifact_checks.py",
            "tools/agent_tools/repository_topic_clone.py",
            "tools/agent_tools/run_accumulated_agent_evals.py",
            "tools/agent_tools/runtime_log_archive_git.py",
            "tools/agent_tools/runtime_log_paths.py",
            "tools/agent_tools/search_index.py",
            "tools/agent_tools/skill_shim_evaluation.py",
            "tools/agent_tools/skill_shim_materializer.py",
            "tools/agent_tools/smoke_test_research_perspective_pack.py",
            "tools/agent_tools/task_authority.py",
            "tools/agent_tools/task_close.py",
            "tools/agent_tools/wiki_publish.py",
            "tools/agent_tools/work_log.py",
            "tools/agent_tools/workflow_monitor.py",
            "tools/agent_tools/workspace_scope.py",
            "tools/ci/agent_canon_pr_graph_selector.py",
            "tools/ci/check_agent_canon_pr.py",
            "tools/ci/container_config.py",
            "tools/ci/container_runtime.py",
        }
    )

    def call_name(node: ast.Call) -> str | None:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return None

    actual: set[str] = set()
    trees: dict[str, ast.AST] = {}
    for path in sorted((repo_root / "tools").rglob("*.py")):
        relative = str(path.relative_to(repo_root))
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        trees[relative] = tree
        if any(
            isinstance(node, ast.Call)
            and call_name(node) == "resolve_parent_writer_attestation"
            for node in ast.walk(tree)
        ):
            actual.add(relative)
    assert frozenset(actual) == inventory

    forbidden = {
        "ParentRootAttestationRequest",
        "attest_parent_root",
        "issue_record_session",
        "session_environment",
        "revoke_record_session",
        "recover_stale_record_sessions",
    }
    for relative in sorted(inventory):
        tree = trees[relative]
        resolver_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and call_name(node) == "resolve_parent_writer_attestation"
        ]
        assert resolver_calls, f"{relative} has no central parent attestation route"
        for call in resolver_calls:
            assert not call.args
            assert {keyword.arg for keyword in call.keywords} == {"purpose"}
        assert not any(
            isinstance(node, ast.Call) and call_name(node) in forbidden
            for node in ast.walk(tree)
        )


@pytest.mark.parametrize(
    "name",
    (
        "TMPDIR",
        "TEMP",
        "TMP",
        "XDG_CACHE_HOME",
        "PYTHONPYCACHEPREFIX",
        "AGENT_CANON_TOOLS_HOME",
        "AGENT_CANON_CLI_TARGET_DIR",
        "CARGO_HOME",
        "CARGO_TARGET_DIR",
    ),
)
def test_child_environment_rejects_external_override_before_creating_directories(
    tmp_path: Path,
    name: str,
) -> None:
    external = tmp_path.parent / f"external-child-{name.lower()}"

    with pytest.raises(ParentRootSideEffectError) as rejected, session_child_environment(
        tmp_path,
        base_env={"HOME": "/unchanged/home", name: str(external)},
        purpose="external-child-environment",
    ):
        pass

    assert rejected.value.reject is ParentRootReject.SYMLINK_ESCAPE
    assert not (tmp_path / ".agent-canon" / "tmp").exists()
    assert not (tmp_path / ".agent-canon" / "cache").exists()
    assert not external.exists()


def test_abort_reserved_target_failure_leaves_target_absent(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    sibling = tmp_path / "workspace" / "topic" / "sibling"
    sibling.mkdir(parents=True)
    (sibling / "keep.txt").write_text("keep\n", encoding="utf-8")
    target = tmp_path / "workspace" / "topic" / "agent-canon"
    handle = boundary.open_parent_owned_target(receipt, target, "clone-target")
    (target / "partial" / "nested").mkdir(parents=True)
    (target / "partial" / "nested" / "residue.txt").write_text(
        "residue\n", encoding="utf-8"
    )

    boundary._abort_reserved_target(receipt, handle, "clone-failure")

    assert not target.exists()
    assert (sibling / "keep.txt").read_text(encoding="utf-8") == "keep\n"
    with pytest.raises(ParentRootSideEffectError):
        boundary._abort_reserved_target(receipt, handle, "clone-failure-reuse")


def test_abort_reserved_target_closes_fds_on_validation_error(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "workspace" / "topic" / "validation-error"
    handle = boundary.open_parent_owned_target(receipt, target, "validation-error")
    parent_fd, target_fd = handle.parent_fd, handle.target_fd
    handle.parent_dev += 1
    with pytest.raises(ParentRootSideEffectError):
        boundary._abort_reserved_target(receipt, handle, "validation-error")
    with pytest.raises(OSError):
        os.fstat(parent_fd)
    with pytest.raises(OSError):
        os.fstat(target_fd)
    published = boundary.resolve_parent_owned_path(receipt, target, "validation-error")
    boundary.remove_parent_owned_tree(receipt, published, "validation-error-cleanup")


def test_read_parent_owned_file_reads_exact_large_payload(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    payload = (b"0123456789abcdef" * ((16 * 1024 * 1024) // 16 + 1))[: 16 * 1024 * 1024 + 17]
    target = boundary.resolve_parent_owned_path(receipt, "reports/large.bin", "large-read")
    published = boundary.atomic_publish(target, payload)

    assert boundary.read_parent_owned_file(published) == payload


def test_read_parent_owned_bytes_returns_exact_capability_payload(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    payload = b"authenticated-parent-payload\x00\xff\n"
    target = boundary.resolve_parent_owned_path(receipt, "reports/result.bin", "bytes-read")
    boundary.atomic_publish(target, payload)

    assert boundary.read_parent_owned_bytes(
        receipt, target.physical_path, "bytes-read"
    ) == payload


def test_read_presence_cli_has_typed_present_missing_and_reject_results(
    tmp_path: Path,
) -> None:
    attest(tmp_path)
    target = tmp_path / "reports" / "present.json"
    target.parent.mkdir()
    target.write_bytes(b"{}\n")
    cli = Path(side_effects.__file__).resolve()
    base = [sys.executable, str(cli), "read-presence", "--root", str(tmp_path)]
    env = _build_clean_env()

    present = subprocess.run(
        [*base, "--candidate", str(target), "--purpose", "presence-test"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert (present.returncode, present.stdout, present.stderr) == (0, "present\n", "")

    missing = subprocess.run(
        [*base, "--candidate", str(tmp_path / "reports" / "missing.json"), "--purpose", "presence-test"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert (missing.returncode, missing.stdout, missing.stderr) == (1, "missing\n", "")

    outside = tmp_path.parent / "presence-outside.json"
    outside.write_bytes(b"outside\n")
    escaping = tmp_path / "reports" / "escaping.json"
    escaping.symlink_to(outside)
    rejected = subprocess.run(
        [*base, "--candidate", str(escaping), "--purpose", "presence-test"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert rejected.returncode == 2
    assert rejected.stdout == ""
    assert "PARENT_ROOT_SIDE_EFFECT_ERROR=" in rejected.stderr


def test_read_parent_owned_file_rejects_in_root_inode_replacement(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = boundary.resolve_parent_owned_path(receipt, "reports/result.txt", "inode-race")
    published = boundary.atomic_publish(target, b"original\n")
    replacement = target.physical_path.with_name("replacement.txt")
    replacement.write_bytes(b"replacement\n")
    target.physical_path.unlink()
    replacement.rename(target.physical_path)

    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.read_parent_owned_file(published)
    assert rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED


def test_read_parent_owned_file_rejects_intermediate_and_root_replacement(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = boundary.resolve_parent_owned_path(receipt, "reports/nested/result.txt", "component-race")
    published = boundary.atomic_publish(target, b"original\n")
    reports = tmp_path / "reports"
    moved_reports = tmp_path / "reports-moved"
    reports.rename(moved_reports)
    reports.mkdir()
    with pytest.raises(ParentRootSideEffectError) as intermediate_rejected:
        boundary.read_parent_owned_file(published)
    assert intermediate_rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED
    shutil.rmtree(reports)
    moved_reports.rename(reports)

    replacement_root = tmp_path.with_name(f"{tmp_path.name}-root-replaced")
    tmp_path.rename(replacement_root)
    tmp_path.mkdir()
    try:
        with pytest.raises(ParentRootSideEffectError) as root_rejected:
            boundary.read_parent_owned_file(published)
        assert root_rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED
    finally:
        shutil.rmtree(tmp_path)
        replacement_root.rename(tmp_path)


@pytest.mark.parametrize("replacement_kind", ["fifo", "directory"])
def test_read_parent_owned_file_rejects_nonregular_replacement_without_blocking(
    tmp_path: Path,
    replacement_kind: str,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = boundary.resolve_parent_owned_path(receipt, "reports/result.txt", "nonregular-race")
    published = boundary.atomic_publish(target, b"original\n")
    target.physical_path.unlink()
    if replacement_kind == "fifo":
        os.mkfifo(target.physical_path)
    else:
        target.physical_path.mkdir()

    started = time.monotonic()
    try:
        with pytest.raises(ParentRootSideEffectError) as rejected:
            boundary.read_parent_owned_file(published)
    finally:
        if target.physical_path.is_dir() and not target.physical_path.is_symlink():
            target.physical_path.rmdir()
        else:
            target.physical_path.unlink()
    assert time.monotonic() - started < 1.0
    assert rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED


def test_optional_missing_then_concurrent_create_preserves_winner_bytes(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "reports" / "winner.json"
    assert boundary.read_parent_owned_bytes(
        receipt, target, "concurrent-create", allow_missing=True
    ) is None
    target.parent.mkdir()
    target.write_bytes(b"winner\n")

    outcome, detail = boundary.publish_parent_owned_file_noreplace(
        receipt, target, b"loser\n", "concurrent-create"
    )
    assert (outcome, detail) == ("failed", "spool_conflict")
    assert boundary.read_parent_owned_bytes(receipt, target, "concurrent-create") == b"winner\n"


def test_read_parent_owned_bytes_releases_lease_on_missing_success_and_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every authenticated read branch releases its internally-owned lease."""
    with session_child_environment(tmp_path) as (boundary, session, _environment):
        target = tmp_path / "reports" / "optional.json"
        lease_dir = side_effects._v2_lease_dir(session.record)

        def assert_no_operation_leases() -> None:
            assert not tuple(lease_dir.glob("*.json"))

        for _ in range(2):
            assert boundary.read_parent_owned_bytes(
                session.attestation,
                target,
                "optional-read",
                allow_missing=True,
            ) is None
            assert_no_operation_leases()

        with pytest.raises(ParentRootSideEffectError) as missing:
            boundary.read_parent_owned_bytes(
                session.attestation, target, "optional-read"
            )
        assert missing.value.reject is ParentRootReject.ROOT_MISSING
        assert_no_operation_leases()

        boundary.write_parent_owned_file(
            session.attestation, target, b"stable\n", "optional-read"
        )
        assert boundary.read_parent_owned_bytes(
            session.attestation, target, "optional-read"
        ) == b"stable\n"
        assert_no_operation_leases()

        replacement = target.with_name("replacement.json")
        replacement.write_bytes(b"replacement\n")

        def replace_before_read(receipt: object) -> bytes:
            target.unlink()
            replacement.rename(target)
            return original_read(receipt)  # type: ignore[arg-type]

        original_read = boundary.read_parent_owned_file
        monkeypatch.setattr(boundary, "read_parent_owned_file", replace_before_read)
        with pytest.raises(ParentRootSideEffectError) as raced:
            boundary.read_parent_owned_bytes(
                session.attestation, target, "optional-read"
            )
        assert raced.value.reject is ParentRootReject.ROOT_RACE_DETECTED
        assert_no_operation_leases()


def test_child_environment_rejects_target_alias_mismatch_before_creating_directories(
    tmp_path: Path,
) -> None:
    with pytest.raises(ParentRootSideEffectError) as rejected, session_child_environment(
        tmp_path,
        base_env={
            "CARGO_TARGET_DIR": str(tmp_path / "target-a"),
            "AGENT_CANON_CLI_TARGET_DIR": str(tmp_path / "target-b"),
        },
        purpose="target-alias-mismatch",
    ):
        pass

    assert rejected.value.reject is ParentRootReject.ROOT_MISMATCH
    assert rejected.value.detail == "target_alias_mismatch"
    assert not (tmp_path / ".agent-canon" / "tmp").exists()
    assert not (tmp_path / ".agent-canon" / "cache").exists()


def test_file_read_and_remove_reject_replaced_capability(tmp_path: Path) -> None:
    """A capability cannot be reused after its target inode is replaced."""
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = boundary.resolve_parent_owned_path(receipt, "reports/result.txt", "report")
    published = boundary.atomic_publish(target, b"original\n")
    replacement = tmp_path / "reports" / "replacement.txt"
    replacement.write_text("replacement\n", encoding="utf-8")
    (tmp_path / "reports" / "result.txt").unlink()
    (tmp_path / "reports" / "result.txt").symlink_to(replacement)
    with pytest.raises(ParentRootSideEffectError) as read_rejected:
        boundary.read_parent_owned_file(published)
    assert read_rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED
    with pytest.raises(ParentRootSideEffectError) as remove_rejected:
        boundary.remove_parent_owned_file(published)
    assert remove_rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED
    assert replacement.exists()


def test_temp_directory_capability_is_exclusive_and_parent_bound(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    base = boundary.ensure_parent_owned_directory(receipt, ".agent-canon/tmp", "temp-base")
    temporary = boundary.create_parent_owned_temp_directory(
        receipt, base.physical_path, "temp-dir", "operation"
    )
    assert temporary.physical_path.is_dir()
    assert temporary.physical_path.parent == base.physical_path
    target = boundary.resolve_parent_owned_path(
        receipt, temporary.physical_path / "result.txt", "temp-result"
    )
    boundary.atomic_publish(target, b"owned\n")
    assert target.physical_path.read_text(encoding="utf-8") == "owned\n"
    boundary.remove_parent_owned_tree(receipt, temporary, "temp-dir-cleanup")
    assert not temporary.physical_path.exists()
    assert boundary.remove_empty_parent_owned_directory(receipt, base, "temp-base-cleanup")
    assert not base.physical_path.exists()


def test_temp_directory_replacement_is_typed_race(tmp_path: Path) -> None:
    """A replaced temporary-directory inode is rejected by its receipt."""
    boundary = ParentRootSideEffectBoundary()
    attestation = attest(tmp_path)
    temporary = boundary.create_parent_owned_temp_directory(
        attestation, tmp_path / "replacement", "replacement", "replacement"
    )
    original = temporary.physical_path
    moved = original.with_name(original.name + "-moved")
    os.rename(original, moved)
    os.mkdir(original)
    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.remove_parent_owned_tree(attestation, temporary, "replacement")
    assert rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED

    replacement_receipt = boundary.resolve_parent_owned_path(
        attestation, original, "replacement-cleanup", create=False
    )
    boundary.remove_parent_owned_tree(
        attestation, replacement_receipt, "replacement-cleanup"
    )
    moved_receipt = boundary.resolve_parent_owned_path(
        attestation, moved, "replacement-moved-cleanup", create=False
    )
    boundary.remove_parent_owned_tree(attestation, moved_receipt, "replacement-moved-cleanup")


def test_symlink_replacement_after_capability_is_typed_race(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "race" / "result.txt"
    capability = boundary.resolve_parent_owned_path(receipt, target, "race")
    outside = tmp_path.parent / "outside-race"
    outside.mkdir()
    (tmp_path / "race").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.atomic_publish(capability, b"must-not-escape")
    assert rejected.value.reject is ParentRootReject.SYMLINK_ESCAPE


def test_create_capability_uses_openat_and_rejects_final_symlink(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    created = boundary.resolve_parent_owned_path(receipt, "created/nested.txt", "create", create=True)
    assert created.physical_path.is_file()
    outside = tmp_path.parent / "create-outside.txt"
    outside.write_text("sentinel", encoding="utf-8")
    escaped = tmp_path / "escaped.txt"
    escaped.symlink_to(outside)
    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.resolve_parent_owned_path(receipt, escaped, "create", create=True)
    assert rejected.value.reject in {ParentRootReject.ROOT_RACE_DETECTED, ParentRootReject.SYMLINK_ESCAPE}


def test_open_parent_owned_file_a_plus_creates_and_locks(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "monitor" / "workflow_monitoring.md"
    with boundary.open_parent_owned_file(
        receipt, target, "workflow-monitoring", create=True, mode="a+"
    ) as handle:
        handle.write("created\n")
        handle.seek(0)
        assert handle.read() == "created\n"
    assert target.read_text(encoding="utf-8") == "created\n"


def test_open_parent_owned_file_r_plus_requires_existing_file_and_does_not_truncate(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "monitor" / "workflow_monitoring.md"
    target.parent.mkdir()
    target.write_text("existing\n", encoding="utf-8")
    with boundary.open_parent_owned_file(
        receipt, target, "workflow-monitoring", create=False, mode="r+"
    ) as handle:
        handle.seek(0)
        assert handle.read() == "existing\n"
    assert target.read_text(encoding="utf-8") == "existing\n"
    with pytest.raises(ParentRootSideEffectError) as missing:
        boundary.open_parent_owned_file(
            receipt,
            tmp_path / "monitor" / "missing.md",
            "workflow-monitoring",
            create=False,
            mode="r+",
        )
    assert missing.value.reject is ParentRootReject.ROOT_MISSING


def test_open_parent_owned_file_rejects_replaced_component(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    outside = tmp_path.parent / "outside-monitor"
    outside.mkdir()
    replaced = tmp_path / "monitor"
    replaced.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.open_parent_owned_file(
            receipt,
            replaced / "workflow_monitoring.md",
            "workflow-monitoring",
            create=True,
            mode="a+",
        )
    assert rejected.value.reject is ParentRootReject.SYMLINK_ESCAPE
    assert not (outside / "workflow_monitoring.md").exists()


def test_open_parent_owned_file_lock_blocks_until_release(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "monitor" / "workflow_monitoring.md"
    first = boundary.open_parent_owned_file(
        receipt, target, "workflow-monitoring", create=True, mode="a+"
    )
    started = threading.Event()
    acquired = threading.Event()
    failures: list[BaseException] = []

    def acquire_second_handle() -> None:
        try:
            started.set()
            with boundary.open_parent_owned_file(
                receipt, target, "workflow-monitoring", create=False, mode="r+"
            ):
                acquired.set()
        except BaseException as exc:  # pragma: no cover - assertion below reports it
            failures.append(exc)

    worker = threading.Thread(target=acquire_second_handle)
    worker.start()
    assert started.wait(2)
    assert not acquired.wait(0.1)
    first.close()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert not failures
    assert acquired.is_set()


def test_open_parent_owned_file_rolls_back_new_file_after_open_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "monitor" / "workflow_monitoring.md"

    def fail_fdopen(*args: object, **kwargs: object) -> object:
        raise OSError("injected text-wrapper failure")

    monkeypatch.setattr(side_effects.os, "fdopen", fail_fdopen)
    with pytest.raises(ParentRootSideEffectError):
        boundary.open_parent_owned_file(
            receipt, target, "workflow-monitoring", create=True, mode="a+"
        )
    assert not target.exists()


def test_remove_parent_owned_tree_handles_deep_tree_without_recursion(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    temporary = boundary.create_parent_owned_temp_directory(
        receipt, tmp_path / "deep", "deep-tree", "deep-tree"
    )
    current = temporary.physical_path
    for _ in range(sys.getrecursionlimit() + 25):
        current = current / "x"
        os.mkdir(current)
    boundary.remove_parent_owned_tree(receipt, temporary, "deep-tree-cleanup")
    assert not temporary.physical_path.exists()


def test_handoff_is_single_use_and_rejects_mutation_or_expiry(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    boundary = ParentRootSideEffectBoundary()
    token = boundary.issue_child_handoff(tmp_path, audience="test", ttl_seconds=30)
    request = ParentRootAttestationRequest(
        cwd=tmp_path, explicit_root=tmp_path, purpose="test", child_handoff_token=token
    )
    receipt = boundary.attest(request)
    assert receipt.handoff is not None
    with pytest.raises(ParentRootSideEffectError) as replay:
        boundary.attest(request)
    assert replay.value.reject is ParentRootReject.HANDOFF_INVALID
    expired = boundary.issue_child_handoff(tmp_path, audience="test", ttl_seconds=1)
    time.sleep(1.05)
    with pytest.raises(ParentRootSideEffectError) as stale:
        ParentRootSideEffectBoundary().attest(
            ParentRootAttestationRequest(
                cwd=tmp_path, explicit_root=tmp_path, purpose="test", child_handoff_token=expired
            )
        )
    assert stale.value.reject is ParentRootReject.HANDOFF_INVALID


def test_child_reattest_requires_handoff_even_when_root_env_is_present(tmp_path: Path) -> None:
    """Dropping the handoff token cannot be replaced by ambient root variables."""
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    with session_child_environment(
        tmp_path,
        base_env={"HOME": "/unchanged/home"},
        purpose="child-reattest",
    ) as (boundary, _session, environment):
        resolved = side_effects.resolve_parent_side_effect_session_v2(
            observed_cwd=tmp_path, env=environment
        )
        try:
            assert resolved.parent_root == tmp_path.resolve()
        finally:
            resolved.close()
        environment.pop("AGENT_CANON_SIDE_EFFECT_HANDOFF")
        with pytest.raises(ParentRootSideEffectError) as dropped:
            side_effects.resolve_parent_side_effect_session_v2(
                observed_cwd=tmp_path, env=environment
            )
    assert dropped.value.reject is ParentRootReject.HANDOFF_INVALID


def test_self_check_cli_reports_no_external_sentinel(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    sentinel = tmp_path.parent / ".pbr-sentinel-not-created"
    with _authenticated_cli_env(tmp_path, purpose="self-check") as (_boundary, _session, env):
        result = subprocess.run(
            [sys.executable, str(_PARENT_ROOT_SIDE_EFFECTS_SCRIPT), "self-check",
             "--root", str(tmp_path), "--sentinel-outside", str(sentinel)],
            check=False, capture_output=True, text=True, env=env,
        )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert payload["home_unchanged"] is True
    assert payload["outside_sentinel_absent"] is True


def test_atomic_publish_handles_short_writes_and_rejects_zero_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    real_write = side_effects.os.write

    def short_write(fd: int, data: bytes) -> int:
        return real_write(fd, data[:2])

    monkeypatch.setattr(side_effects.os, "write", short_write)
    published = boundary.atomic_publish(
        boundary.resolve_parent_owned_path(receipt, "short/result.txt", "short"),
        b"short-write-payload",
    )
    assert boundary.read_parent_owned_file(published) == b"short-write-payload"

    def no_progress(_fd: int, _data: bytes) -> int:
        return 0

    monkeypatch.setattr(side_effects.os, "write", no_progress)
    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.atomic_publish(
            boundary.resolve_parent_owned_path(receipt, "zero/result.txt", "zero"),
            b"must-fail",
        )
    assert rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED
    assert not list((tmp_path / "zero").glob("*.tmp"))


def test_receipt_rejects_replaced_intermediate_real_directory(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    nested = boundary.ensure_parent_owned_directory(receipt, "nested", "nested")
    capability = boundary.resolve_parent_owned_path(
        receipt, nested.physical_path / "result.txt", "nested-file"
    )
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    old = tmp_path / "nested-old"
    os.rename(tmp_path / "nested", old)
    os.rename(replacement, tmp_path / "nested")
    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.atomic_publish(capability, b"must-not-publish")
    assert rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED
    assert not (tmp_path / "nested" / "result.txt").exists()


def test_atomic_publish_surfaces_cleanup_failure_and_keeps_readback_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    real_unlink = side_effects.os.unlink

    def failing_temp_unlink(path: object, *args: object, **kwargs: object) -> None:
        if isinstance(path, str) and path.endswith(".tmp"):
            raise OSError(13, "injected cleanup failure")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(side_effects.os, "unlink", failing_temp_unlink)
    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.atomic_publish(
            boundary.resolve_parent_owned_path(receipt, "cleanup/result.txt", "cleanup"),
            b"published-before-cleanup-error",
        )
    assert "cleanup failed" in str(rejected.value)
    assert (tmp_path / "cleanup" / "result.txt").read_bytes() == b"published-before-cleanup-error"


def test_capture_subprocess_publishes_and_replays_stdout(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    target = tmp_path / "reports" / "captured.txt"
    with _authenticated_cli_env(tmp_path, purpose="capture-test") as (_boundary, _session, env):
        result = subprocess.run(
            [
                sys.executable,
                str(_PARENT_ROOT_SIDE_EFFECTS_SCRIPT),
                "capture-subprocess",
                "--root",
                str(tmp_path),
                "--candidate",
                str(target),
                "--purpose",
                "capture-test",
                "--",
                sys.executable,
                "-c",
                "print('captured')",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "captured\n"
    assert target.read_text(encoding="utf-8") == "captured\n"
    assert pending_handoff_nonces(tmp_path) == {}


def test_exec_parent_bound_preserves_home_and_bindings(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    preserved_home = tmp_path / "outside-home"
    preserved_home.mkdir()
    env = _build_clean_env(
        {
            "HOME": str(preserved_home),
            "PYTHONPATH": os.getcwd(),
        }
    )
    code = (
        "import json, os; "
        "print(json.dumps({"
        "\"home\": os.environ.get(\"HOME\"), "
        "\"tmpdir\": os.environ.get(\"TMPDIR\"), "
        "\"temp\": os.environ.get(\"TEMP\"), "
        "\"tmp\": os.environ.get(\"TMP\"), "
        "\"cache\": os.environ.get(\"XDG_CACHE_HOME\"), "
        "\"tools\": os.environ.get(\"AGENT_CANON_TOOLS_HOME\"), "
        "\"cargo_target\": os.environ.get(\"CARGO_TARGET_DIR\"), "
        "\"cli_target\": os.environ.get(\"AGENT_CANON_CLI_TARGET_DIR\"), "
        "\"handoff\": os.environ.get(\"AGENT_CANON_CHILD_HANDOFF\"), "
        "\"purpose\": os.environ.get(\"AGENT_CANON_CHILD_PURPOSE\")"
        "}))"
    )
    with _authenticated_cli_env(
        tmp_path, purpose="exec-test", base_env=env
    ) as (_boundary, _session, env):
        env.update(
            {
                "AGENT_CANON_CHILD_HANDOFF": "untrusted-inherited-token",
                "AGENT_CANON_HANDOFF_AUDIENCE": "untrusted-audience",
                "AGENT_CANON_CHILD_PURPOSE": "untrusted-purpose",
            }
        )
        result = subprocess.run(
            [
                sys.executable,
                str(_PARENT_ROOT_SIDE_EFFECTS_SCRIPT),
                "exec-parent-bound",
                "--root",
                str(tmp_path),
                "--purpose",
                "exec-test",
                "--",
                sys.executable,
                "-c",
                code,
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout.strip())
    assert data["home"] == str(preserved_home)
    expected_tmp = str((tmp_path / ".agent-canon" / "tmp").resolve())
    assert data["tmpdir"] == expected_tmp
    assert data["temp"] == expected_tmp
    assert data["tmp"] == expected_tmp
    assert Path(data["cache"]).resolve().is_relative_to(tmp_path.resolve())
    assert Path(data["tools"]).resolve().is_relative_to(tmp_path.resolve())
    assert data["cargo_target"] == data["cli_target"]
    assert data["handoff"] is None
    assert data["purpose"] is None
    assert pending_handoff_nonces(tmp_path) == {}


def test_exec_parent_bound_rebases_inherited_runner_temp(tmp_path: Path) -> None:
    """Update/sync handoffs rebase runner temp variables before path checks."""
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    inherited_tmp = tmp_path.parent / "outer-runner-tmp"
    base_env = _build_clean_env(
        {
            "TMPDIR": str(inherited_tmp),
            "TEMP": str(inherited_tmp),
            "TMP": str(inherited_tmp),
        }
    )
    code = (
        "import json, os; "
        "print(json.dumps({name: os.environ.get(name) for name in "
        "('TMPDIR', 'TEMP', 'TMP')}))"
    )
    with _authenticated_cli_env(
        tmp_path,
        purpose="agent-canon-update-script",
        base_env=base_env,
        rebase_inherited_temp=True,
    ) as (_boundary, _session, env):
        result = subprocess.run(
            [
                sys.executable,
                str(_PARENT_ROOT_SIDE_EFFECTS_SCRIPT),
                "exec-parent-bound",
                "--root",
                str(tmp_path),
                "--purpose",
                "agent-canon-update-script",
                "--rebase-inherited-temp",
                "--",
                sys.executable,
                "-c",
                code,
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout.strip())
    expected = str((tmp_path / ".agent-canon" / "tmp").resolve())
    assert data == {"TMPDIR": expected, "TEMP": expected, "TMP": expected}
    assert not inherited_tmp.exists()


def test_exec_parent_bound_failure_does_not_leave_pending_handoff(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    with _authenticated_cli_env(tmp_path, purpose="exec-failure-test") as (
        _boundary, _session, env
    ):
        result = subprocess.run(
            [
                sys.executable,
                str(_PARENT_ROOT_SIDE_EFFECTS_SCRIPT),
                "exec-parent-bound",
                "--root",
                str(tmp_path),
                "--purpose",
                "exec-failure-test",
                "--",
                sys.executable,
                "-c",
                "raise SystemExit(17)",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    assert result.returncode == 17
    assert pending_handoff_nonces(tmp_path) == {}


def test_exec_parent_bound_rejects_external_target_before_side_effects(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    external = tmp_path.parent / "external-target"
    script = tmp_path / ".agent-canon" / "cli-runner.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("# authenticated CLI runner\n", encoding="utf-8")
    previous_cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        with public_session(invocation_script=script, purpose="exec-test") as session:
            env = side_effects._v2_session_environment(
                session,
                _build_clean_env({"AGENT_CANON_CLI_TARGET_DIR": str(external)}),
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(_PARENT_ROOT_SIDE_EFFECTS_SCRIPT),
                    "exec-parent-bound",
                    "--root",
                    str(tmp_path),
                    "--purpose",
                    "exec-test",
                    "--",
                    "echo",
                    "should-not-run",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
    finally:
        os.chdir(previous_cwd)
    assert result.returncode == 2
    assert external.exists() is False
    assert not (tmp_path / ".agent-canon" / "tmp").exists()


def test_child_environment_rejection_preserves_preexisting_entries(tmp_path: Path) -> None:
    preexisting_tmp = tmp_path / ".agent-canon" / "tmp"
    preexisting_cache = tmp_path / ".agent-canon" / "cache"
    preexisting_tmp.mkdir(parents=True)
    preexisting_cache.mkdir(parents=True)
    pre_token = json.dumps({"marker": "preexisting"})
    token_file = preexisting_tmp / "preexisting.txt"
    token_file.write_text(pre_token, encoding="utf-8")

    with pytest.raises(ParentRootSideEffectError), session_child_environment(
        tmp_path,
        base_env={"AGENT_CANON_CLI_TARGET_DIR": str(tmp_path.parent / "external-target")},
        purpose="child-environment-preserve",
    ):
        pass

    assert token_file.read_text(encoding="utf-8") == pre_token


def test_copy_mode_external_read_and_symlink_replacement_are_boundary_owned(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    source = tmp_path / "build" / "agent-canon"
    source.parent.mkdir()
    source.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    source.chmod(0o755)
    installed = tmp_path / ".agent-canon" / "tools" / "agent-canon" / "bin" / "agent-canon"

    published = boundary.copy_parent_owned_file(
        receipt,
        source,
        installed,
        "executable-copy-test",
        preserve_mode=True,
    )
    assert published.physical_path == installed
    assert installed.stat().st_mode & 0o777 == 0o755

    link = tmp_path / ".agent-canon" / "tools" / "bin" / "agent-canon"
    link.parent.mkdir(parents=True)
    link.symlink_to("obsolete")
    assert boundary.replace_parent_owned_symlink(
        receipt, str(installed), link, "symlink-replacement-test"
    ) == link
    assert link.is_symlink()
    assert os.readlink(link) == str(installed)

    external = tmp_path.parent / "read-only-input.txt"
    external.write_text("external input\n", encoding="utf-8")
    snapshot = tmp_path / ".agent-canon" / "tmp" / "snapshot.txt"
    boundary.copy_read_only_file(
        receipt, external, snapshot, "read-only-copy-test"
    )
    assert snapshot.read_text(encoding="utf-8") == "external input\n"
    assert external.read_text(encoding="utf-8") == "external input\n"


def test_verify_child_rejects_forged_purpose_without_handoff(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    result = subprocess.run(
        [
            sys.executable,
            str(_PARENT_ROOT_SIDE_EFFECTS_SCRIPT),
            "verify-child",
            "--root",
            str(tmp_path),
            "--purpose",
            "forged-child",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=_build_clean_env({"AGENT_CANON_CHILD_PURPOSE": "forged-child"}),
    )
    assert result.returncode == 2
    assert "handoff_invalid" in result.stderr
