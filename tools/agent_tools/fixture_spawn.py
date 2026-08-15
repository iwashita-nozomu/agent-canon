#!/usr/bin/env python3
# @dependency-start
# contract test
# responsibility Delegates record-owned fixture-direct production commands to the canonical boundary.
# upstream implementation ./parent_root_side_effects.py owns fixture validation, spawn, readback, and cleanup
# downstream implementation ../../test/testrunner.sh owns record lifecycle and signed child state
# @dependency-end

"""The sole unique-package facade for record-owned fixture-direct commands."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tools.agent_tools.parent_root_side_effects import (
    FixtureExecutionReceipt,
    ParentRootReject,
    ParentRootSideEffectBoundary,
    ParentRootSideEffectError,
    SessionResolutionResult,
    fixture_child_environment,
    fixture_direct_command,
    public_session,
    resolve_parent_side_effect_session_v2,
    validate_fixture_root,
)

FixtureMode = Literal["ordinary_tool", "product_fixture", "synthetic_tool"]


@dataclass(frozen=True)
class FixturePublicEnvironment(Mapping[str, str]):
    """One mode-selected fixture environment and its owned evidence.

    Ordinary and synthetic modes expose a child environment through the mapping
    interface.  Product mode exposes its unchanged direct-command receipt;
    stdout and stderr remain the subprocess streams rather than receipt data.
    """

    mode: FixtureMode
    record: SessionResolutionResult
    fixture_cwd: Path
    environment: Mapping[str, str]
    session: SessionResolutionResult | None = None
    receipt: FixtureExecutionReceipt | None = None

    def __getitem__(self, key: str) -> str:
        """Return one child environment value."""
        return self.environment[key]

    def __iter__(self) -> Iterator[str]:
        """Iterate child environment keys."""
        return iter(self.environment)

    def __len__(self) -> int:
        """Return the child environment size."""
        return len(self.environment)


_FIXTURE_PATH_ENV_KEYS = (
    "AGENT_CANON_PARENT_ROOT", "AGENT_CANON_PARENT_ROOT_DEV",
    "AGENT_CANON_PARENT_ROOT_INO", "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
    "AGENT_CANON_SOURCE_ROOT", "AGENT_CANON_ROOT", "AGENT_CANON_CHILD_HANDOFF",
    "AGENT_CANON_CHILD_PURPOSE", "AGENT_CANON_HANDOFF_AUDIENCE",
    "AGENT_CANON_FIXTURE_ROLE", "AGENT_CANON_REPORT_ROOT",
    "AGENT_CANON_RUN_BUNDLE_ROOT", "AGENT_CANON_CLOSEOUT_ROOT",
    "AGENT_CANON_RECORD_ROOT", "AGENT_CANON_RECORD_ID",
    "AGENT_CANON_TOOLS_HOME", "AGENT_CANON_CLI_TARGET_DIR",
    "AGENT_CANON_DATA_REPOSITORY_ROOT", "AGENT_CANON_DATA_REPOSITORY_DEV",
    "AGENT_CANON_DATA_REPOSITORY_INO", "AGENT_CANON_DATA_SOURCE_ROOT",
    "AGENT_CANON_DATA_ROOT", "PYTHONPATH",
)
_FIXTURE_EXEC_PATH = (
    "/opt/agent-canon-parent/vendor/agent-canon/test",
    "/usr/local/cargo/bin", "/usr/local/sbin", "/usr/local/bin",
    "/usr/sbin", "/usr/bin", "/sbin", "/bin",
)


def _clean_fixture_environment(
    record: SessionResolutionResult,
    local_root: Path,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Construct the product/synthetic environment without inherited identity."""
    environment = fixture_child_environment(record, local_root)
    if base_env is not None:
        for key, value in base_env.items():
            if (
                key not in environment
                and key not in _FIXTURE_PATH_ENV_KEYS
                and not key.startswith("AGENT_CANON_SIDE_EFFECT_")
            ):
                environment[key] = value
    for key in tuple(environment):
        if key.startswith("AGENT_CANON_SIDE_EFFECT_") or key in _FIXTURE_PATH_ENV_KEYS:
            environment.pop(key, None)
    environment["PATH"] = os.pathsep.join(_FIXTURE_EXEC_PATH + (str(local_root / "tools"),))
    return environment


def _physical_identity(path: Path) -> tuple[Path, int, int]:
    """Read one physical path identity for CWD restoration checks."""
    checked = path.resolve(strict=True)
    state = checked.stat()
    return checked, state.st_dev, state.st_ino


def _restore_source_cwd(source: tuple[Path, int, int]) -> None:
    """Restore the caller CWD and fail closed if its physical identity changed."""
    source_path, source_dev, source_ino = source
    os.chdir(source_path)
    restored, dev, ino = _physical_identity(source_path)
    if restored != source_path or (dev, ino) != (source_dev, source_ino):
        raise ParentRootSideEffectError(
            ParentRootReject.ROOT_RACE_DETECTED,
            "fixture source CWD identity changed during bootstrap",
        )


@contextmanager
def _validated_fixture(
    record: SessionResolutionResult,
    fixture_cwd: Path | os.PathLike[str],
    *,
    now_mono_ns: int,
) -> Iterator[tuple[Path, int, int, tuple[Path, int, int]]]:
    """Validate a nested Git root while preserving the authenticated source CWD."""
    source = _physical_identity(Path.cwd())
    try:
        fixture_path = Path(fixture_cwd)
    except (TypeError, ValueError, OSError) as exc:
        raise ParentRootSideEffectError(
            ParentRootReject.INPUT_INVALID, "fixture_cwd is invalid"
        ) from exc
    fixture_path = fixture_path.resolve(strict=True)
    primary_error: BaseException | None = None
    try:
        os.chdir(fixture_path)
        identity = validate_fixture_root(
            record, fixture_path, require_lease=False, now_mono_ns=now_mono_ns
        )
        yield identity[0], identity[1], identity[2], source
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        try:
            _restore_source_cwd(source)
        except BaseException as restore_error:
            if primary_error is None:
                raise
            primary_error.add_note(
                f"fixture source CWD restoration outcome: {restore_error}"
            )


@contextmanager
def bootstrap_fixture_public_environment(
    *,
    mode: FixtureMode | str,
    fixture_cwd: Path | os.PathLike[str],
    record: SessionResolutionResult | None = None,
    base_env: Mapping[str, str] | None = None,
    argv: Sequence[str] | None = None,
    now_mono_ns: int | None = None,
    clock: Callable[[], int] | None = None,
    purpose: str | None = None,
    invocation_script: Path | None = None,
) -> Iterator[FixturePublicEnvironment]:
    """Select the one public boundary for ordinary, product, or synthetic work.

    The enclosing record is resolved at the caller's authenticated source root.
    Fixture validation may temporarily change CWD, but every path—including
    command, exception, and cleanup paths—restores the original physical CWD.
    Product commands delegate to ``run_fixture_command``.  Synthetic tools
    receive an independent fixture-rooted public session after inherited
    authority/import identity has been scrubbed.
    """
    aliases = {
        "ordinary": "ordinary_tool", "tool": "ordinary_tool",
        "product": "product_fixture", "synthetic": "synthetic_tool",
    }
    normalized_mode = aliases.get(str(mode), str(mode))
    if normalized_mode not in {"ordinary_tool", "product_fixture", "synthetic_tool"}:
        raise ParentRootSideEffectError(ParentRootReject.INPUT_INVALID, "fixture mode is invalid")
    try:
        fixture_path = Path(fixture_cwd)
    except (TypeError, ValueError, OSError) as exc:
        raise ParentRootSideEffectError(
            ParentRootReject.INPUT_INVALID, "fixture_cwd is invalid"
        ) from exc
    if record is not None and type(record) is not SessionResolutionResult:
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, "record is invalid")
    command = None if argv is None else tuple(argv)
    if normalized_mode == "product_fixture" and command is None:
        raise ParentRootSideEffectError(ParentRootReject.INPUT_INVALID, "product fixture argv is required")
    now = time.monotonic_ns() if now_mono_ns is None else now_mono_ns
    if type(now) is not int or now < 0:
        raise ParentRootSideEffectError(ParentRootReject.INPUT_INVALID, "now_mono_ns is invalid")
    invocation_cwd = _physical_identity(Path.cwd())

    @contextmanager
    def record_scope() -> Iterator[SessionResolutionResult]:
        if record is not None:
            yield record
            return
        with record_session_from_environment() as resolved:
            yield resolved

    with record_scope() as resolved_record:
        safe_cwd = _physical_identity(resolved_record.parent_root)
        if safe_cwd[0] == invocation_cwd[0]:
            safe_cwd = _physical_identity(invocation_cwd[0].parent)
        outer_error: BaseException | None = None
        try:
            with _validated_fixture(resolved_record, fixture_path, now_mono_ns=now) as (
                fixture_root, _fixture_dev, _fixture_ino, source,
            ):
                if normalized_mode == "ordinary_tool":
                    environment = ParentRootSideEffectBoundary().session_environment(
                        resolved_record,
                        os.environ if base_env is None else base_env,
                    )
                    _restore_source_cwd(source)
                    yield FixturePublicEnvironment(
                        "ordinary_tool", resolved_record, fixture_root, environment
                    )
                    return

                if normalized_mode == "product_fixture":
                    os.chdir(fixture_root)
                    try:
                        product_now = time.monotonic_ns() if clock is None else clock()
                        receipt = run_fixture_command(
                            record=resolved_record,
                            fixture_cwd=fixture_root,
                            argv=command or (),
                            now_mono_ns=product_now,
                            clock=clock,
                        )
                    finally:
                        _restore_source_cwd(source)
                    yield FixturePublicEnvironment(
                        "product_fixture", resolved_record, fixture_root, {}, receipt=receipt
                    )
                    return

                boundary = ParentRootSideEffectBoundary()
                saved_environment = os.environ.copy()
                local_receipt = boundary.create_parent_owned_temp_directory(
                    resolved_record.attestation,
                    fixture_root / ".agent-canon" / "fixture-bootstrap",
                    "fixture-bootstrap-local",
                    "fixture-bootstrap",
                )
                restoration_errors: list[BaseException] = []
                cleanup_errors: list[BaseException] = []
                primary_error: BaseException | None = None
                body_error: BaseException | None = None
                try:
                    local_root = local_receipt.physical_path
                    clean_environment = _clean_fixture_environment(
                        resolved_record, local_root, base_env
                    )
                    script = invocation_script or (local_root / "synthetic-tool.py")
                    script = script if script.is_absolute() else fixture_root / script
                    if invocation_script is None:
                        boundary.write_parent_owned_file(
                            resolved_record.attestation,
                            script,
                            b"# synthetic fixture tool\n",
                            "fixture-bootstrap-invocation",
                        )
                    elif not script.is_file():
                        raise ParentRootSideEffectError(
                            ParentRootReject.INPUT_INVALID,
                            "synthetic invocation script is missing",
                        )
                    os.environ.clear()
                    os.environ.update(clean_environment)
                    os.chdir(fixture_root)
                    with public_session(
                        invocation_script=script,
                        purpose=purpose or "fixture-synthetic-tool",
                        independent=True,
                        cleanup_state=True,
                    ) as independent_session:
                        environment = ParentRootSideEffectBoundary().session_environment(
                            independent_session, clean_environment
                        )
                        try:
                            _restore_source_cwd(source)
                        except BaseException as exc:
                            restoration_errors.append(exc)
                            raise
                        os.environ.clear()
                        os.environ.update(saved_environment)
                        try:
                            yield FixturePublicEnvironment(
                                "synthetic_tool", resolved_record, fixture_root,
                                environment, session=independent_session,
                            )
                        except BaseException as exc:
                            body_error = exc
                            raise
                except BaseException as exc:
                    primary_error = exc
                    raise
                finally:
                    try:
                        os.environ.clear()
                        os.environ.update(saved_environment)
                    except BaseException as exc:
                        restoration_errors.append(exc)
                    try:
                        _restore_source_cwd(source)
                    except BaseException as exc:
                        restoration_errors.append(exc)
                    try:
                        boundary.remove_parent_owned_tree(
                            resolved_record.attestation,
                            local_receipt,
                            "fixture-bootstrap-local-cleanup",
                        )
                    except BaseException as exc:
                        cleanup_errors.append(exc)
                    try:
                        boundary.remove_empty_parent_owned_directory(
                            resolved_record.attestation,
                            fixture_root / ".agent-canon" / "fixture-bootstrap",
                            "fixture-bootstrap-root-cleanup",
                        )
                    except BaseException as exc:
                        cleanup_errors.append(exc)
                    errors = restoration_errors + cleanup_errors
                    if errors:
                        restoration_detail = (
                            "clean"
                            if not restoration_errors
                            else "; ".join(str(error) for error in restoration_errors)
                        )
                        cleanup_detail = (
                            "clean"
                            if not cleanup_errors
                            else "; ".join(str(error) for error in cleanup_errors)
                        )
                        detail = "; ".join(
                            (
                                f"restoration={restoration_detail}",
                                f"cleanup={cleanup_detail}",
                            )
                        )
                        combined_error = ParentRootSideEffectError(
                            ParentRootReject.ROOT_RACE_DETECTED,
                            f"fixture bootstrap restoration/cleanup outcome: {detail}",
                        )
                        if body_error is not None:
                            body_error.add_note(str(combined_error))
                        elif primary_error is not None and not restoration_errors:
                            primary_error.add_note(str(combined_error))
                        else:
                            raise combined_error from primary_error
        except BaseException as exc:
            outer_error = exc
            raise
        finally:
            try:
                _restore_source_cwd(invocation_cwd)
            except BaseException as restore_error:
                try:
                    _restore_source_cwd(safe_cwd)
                except BaseException as fallback_error:
                    restore_error.add_note(
                        f"safe CWD fallback restoration failed: {fallback_error}"
                    )
                if outer_error is not None:
                    outer_error.add_note(
                        f"invocation CWD restoration outcome: {restore_error}; "
                        f"safe fallback={safe_cwd[0]}"
                    )
                else:
                    raise


@contextmanager
def record_session_from_environment() -> Iterator[SessionResolutionResult]:
    """Borrow the runner's signed record capability for one fixture call.

    This does not bootstrap a fixture session or manufacture repository
    identity.  The record channel is resolved from the physical caller CWD,
    and its operation lease is always released before the context exits.
    """
    record = resolve_parent_side_effect_session_v2(
        env=os.environ,
        observed_cwd=Path.cwd().resolve(),
    )
    try:
        yield record
    finally:
        record.close()


@contextmanager
def record_environment(
    *, cwd: Path, base_env: dict[str, str] | None = None
) -> Iterator[dict[str, str]]:
    """Expose one complete signed record environment at a physical CWD.

    This is for ordinary nested record subprocesses.  Fixture production
    commands must use :func:`run_fixture_command`, which owns channel removal
    and local-path preparation.
    """
    previous_cwd = Path.cwd()
    try:
        os.chdir(cwd)
        with record_session_from_environment() as record:
            yield ParentRootSideEffectBoundary().session_environment(
                record, os.environ if base_env is None else base_env
            )
    finally:
        os.chdir(previous_cwd)


def run_fixture_command(
    *,
    record: SessionResolutionResult,
    fixture_cwd: Path,
    argv: Sequence[str],
    now_mono_ns: int,
    clock: Callable[[], int] | None = None,
) -> FixtureExecutionReceipt:
    """Run one production command from a physical fixture Git root.

    Security decisions, process invocation, physical-root readback, and
    receipt-owned cleanup remain in the source-owned boundary.  This facade
    only supplies the opaque route marker and forwards the typed arguments.
    """
    receipt = fixture_direct_command(
        record=record,
        fixture_cwd=fixture_cwd,
        argv=argv,
        now_mono_ns=now_mono_ns,
        clock=time.monotonic_ns if clock is None else clock,
    )
    if receipt.cleanup.status != "clean":
        raise ParentRootSideEffectError(
            ParentRootReject.ROOT_RACE_DETECTED,
            receipt.cleanup.detail or "fixture cleanup failed",
        )
    return receipt


__all__ = [
    "FixtureMode",
    "FixturePublicEnvironment",
    "bootstrap_fixture_public_environment",
    "record_environment",
    "record_session_from_environment",
    "run_fixture_command",
]
