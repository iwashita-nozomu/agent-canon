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
import secrets
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tools.agent_tools.parent_root_side_effects import (
    PRIVATE_RECORD_REQUIRED_ENV,
    SIDE_EFFECT_HANDOFF_ENV,
    SIDE_EFFECT_PARENT_ROOT_ENV,
    SIDE_EFFECT_REQUIRED_ENV,
    FixtureChildEnvironment,
    FixtureEnvironmentRequest,
    FixtureExecutionReceipt,
    ParentRootReject,
    ParentRootSideEffectBoundary,
    ParentRootSideEffectError,
    RecordCapability,
    SessionResolutionResult,
    fixture_child_environment_with_receipt,
    fixture_direct_command,
    project_fixture_environment,
    public_session,
    record_session_context,
    resolve_parent_side_effect_session_v2,
    validate_fixture_root,
)

FixtureMode = Literal["ordinary_tool", "product_fixture", "synthetic_tool"]


def build_fixture_environment_request(
    *,
    mode: FixtureMode,
    record_capability: RecordCapability | None,
    ambient_env: Mapping[str, str],
    explicit_target_dir: Path | None,
    explicit_path_entries: tuple[Path, ...],
    fixture_root: Path,
) -> FixtureEnvironmentRequest:
    """Construct the one immutable request consumed by every fixture mode."""
    if mode not in {"ordinary_tool", "product_fixture", "synthetic_tool"}:
        raise ParentRootSideEffectError(ParentRootReject.INPUT_INVALID, "fixture mode is invalid")
    if mode != "ordinary_tool" and record_capability is None:
        raise ParentRootSideEffectError(
            ParentRootReject.HANDOFF_INVALID,
            "fixture mode requires an explicit record capability",
        )
    root = Path(fixture_root).resolve(strict=True)
    if record_capability is not None:
        if not root.is_dir() or not (root / ".git").exists():
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH,
                "fixture root is not an exact nested Git root",
            )
        if not root.is_relative_to(record_capability.parent_root):
            raise ParentRootSideEffectError(
                ParentRootReject.ROOT_MISMATCH,
                "fixture root is outside authenticated parent",
            )
    return FixtureEnvironmentRequest(
        request_id=secrets.token_hex(16),
        mode=mode,
        record_capability=record_capability,
        ambient_env=dict(ambient_env),
        explicit_target_dir=explicit_target_dir,
        explicit_path_entries=tuple(explicit_path_entries),
        fixture_root=root,
    )


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
    child: FixtureChildEnvironment | None = None

    def __getitem__(self, key: str) -> str:
        """Return one child environment value."""
        return self.environment[key]

    def __iter__(self) -> Iterator[str]:
        """Iterate child environment keys."""
        return iter(self.environment)

    def __len__(self) -> int:
        """Return the child environment size."""
        return len(self.environment)


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
    explicit_path_entries: Sequence[str] | None = None,
    record_capability: RecordCapability | None = None,
    ambient_env: Mapping[str, str] | None = None,
    explicit_target_dir: Path | None = None,
    request: FixtureEnvironmentRequest | None = None,
) -> Iterator[FixturePublicEnvironment]:
    """Select the one public boundary for ordinary, product, or synthetic work.

    The enclosing record is resolved at the caller's authenticated source root.
    Fixture validation may temporarily change CWD, but every path—including
    command, exception, and cleanup paths—restores the original physical CWD.
    Product commands delegate to ``run_fixture_command``.  Synthetic tools
    receive an independent fixture-rooted public session after inherited
    authority/import identity has been scrubbed.  ``base_env["PATH"]`` is
    ambient input and is dropped; only ``explicit_path_entries`` is validated
    and projected ahead of the canonical fixture/system path.
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
    if record_capability is not None and type(record_capability) is not RecordCapability:
        raise ParentRootSideEffectError(
            ParentRootReject.HANDOFF_INVALID, "record_capability is invalid"
        )
    if base_env is not None and ambient_env is not None:
        raise ParentRootSideEffectError(
            ParentRootReject.INPUT_INVALID, "ambient environment was provided twice"
        )
    selected_ambient = ambient_env if ambient_env is not None else base_env
    if request is not None:
        if any(
            value is not None
            for value in (record, base_env, ambient_env, record_capability, explicit_target_dir)
        ) or explicit_path_entries is not None:
            raise ParentRootSideEffectError(
                ParentRootReject.INPUT_INVALID,
                "fixture request inputs were duplicated",
            )
        if request.mode != normalized_mode:
            raise ParentRootSideEffectError(
                ParentRootReject.INPUT_INVALID,
                "fixture request mode does not match facade mode",
            )
        record_capability = request.record_capability
        selected_ambient = request.ambient_env
        explicit_target_dir = request.explicit_target_dir
        explicit_path_entries = tuple(str(entry) for entry in request.explicit_path_entries)
    if normalized_mode != "ordinary_tool" and record_capability is None and record is not None:
        raise ParentRootSideEffectError(
            ParentRootReject.HANDOFF_INVALID,
            "product and synthetic modes require an explicit record capability",
        )
    command = None if argv is None else tuple(argv)
    if normalized_mode == "product_fixture" and command is None:
        raise ParentRootSideEffectError(ParentRootReject.INPUT_INVALID, "product fixture argv is required")
    now = time.monotonic_ns() if now_mono_ns is None else now_mono_ns
    if type(now) is not int or now < 0:
        raise ParentRootSideEffectError(ParentRootReject.INPUT_INVALID, "now_mono_ns is invalid")
    invocation_cwd = _physical_identity(Path.cwd())

    @contextmanager
    def record_scope() -> Iterator[tuple[SessionResolutionResult, RecordCapability]]:
        selected_capability = record_capability
        if selected_capability is None and record is not None and normalized_mode == "ordinary_tool":
            selected_capability = RecordCapability.from_record(record)
        if normalized_mode != "ordinary_tool" and selected_capability is None:
            raise ParentRootSideEffectError(
                ParentRootReject.HANDOFF_INVALID,
                "fixture mode requires an explicit record capability",
            )
        if selected_capability is not None:
            if not selected_capability.consumed:
                selected_capability.consume()
            capability_environment = selected_capability.transport_environment()
            with _record_session_from_capability(
                selected_capability, observed_cwd=invocation_cwd[0]
            ) as resolved:
                if record is not None and resolved.record.record_id != record.record.record_id:
                    raise ParentRootSideEffectError(
                        ParentRootReject.HANDOFF_INVALID,
                        "record and record_capability identify different records",
                    )
                # Keep the producer transport local to the adapter.  The
                # mapping is intentionally not merged into a product child.
                del capability_environment
                yield resolved, selected_capability
            return
        with record_session_from_environment(ordinary_only=True) as resolved:
            fallback_capability = (
                record_capability_from_environment(observed_cwd=Path.cwd().resolve())
                if os.environ.get(PRIVATE_RECORD_REQUIRED_ENV) == "1"
                else RecordCapability.from_record(resolved)
            )
            fallback_capability.consume()
            yield resolved, fallback_capability

    with record_scope() as (resolved_record, active_capability):
        safe_cwd = _physical_identity(resolved_record.parent_root)
        if safe_cwd[0] == invocation_cwd[0]:
            safe_cwd = _physical_identity(invocation_cwd[0].parent)
        outer_error: BaseException | None = None
        try:
            with _validated_fixture(resolved_record, fixture_path, now_mono_ns=now) as (
                fixture_root, _fixture_dev, _fixture_ino, source,
            ):
                effective_request = request or build_fixture_environment_request(
                    mode=normalized_mode,  # type: ignore[arg-type]
                    record_capability=active_capability,
                    ambient_env=os.environ if selected_ambient is None else selected_ambient,
                    explicit_target_dir=explicit_target_dir,
                    explicit_path_entries=tuple(
                        Path(entry) for entry in (explicit_path_entries or ())
                    ),
                    fixture_root=fixture_root,
                )
                if normalized_mode == "ordinary_tool":
                    child = project_fixture_environment(
                        resolved_record, request=effective_request
                    )
                    environment = ParentRootSideEffectBoundary().session_environment(
                        resolved_record, child.environment
                    )
                    child.environment = environment
                    _restore_source_cwd(source)
                    yield FixturePublicEnvironment(
                        "ordinary_tool", resolved_record, fixture_root, environment,
                        child=child,
                    )
                    child.close()
                    return

                if normalized_mode == "product_fixture":
                    os.chdir(fixture_root)
                    product_now = time.monotonic_ns() if clock is None else clock()
                    receipt = run_fixture_command(
                        record=resolved_record,
                        fixture_cwd=fixture_root,
                        argv=command or (),
                        now_mono_ns=product_now,
                        clock=clock,
                        ambient_env=selected_ambient,
                        explicit_target_dir=explicit_target_dir,
                        request=effective_request,
                    )
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
                child_environment: FixtureChildEnvironment | None = None
                try:
                    local_root = local_receipt.physical_path
                    child_environment = fixture_child_environment_with_receipt(
                        resolved_record, local_root, request=effective_request
                    )
                    clean_environment = child_environment.environment
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
                        child_environment.receipt.public_projection_record_id = (
                            independent_session.record.record_id
                        )
                        child_environment.receipt.public_projection_provenance = (
                            "fixture_independent"
                        )
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
                                child=child_environment,
                            )
                        except BaseException as exc:
                            body_error = exc
                            raise
                except BaseException as exc:
                    primary_error = exc
                    raise
                finally:
                    if child_environment is not None:
                        try:
                            child_environment.close()
                        except BaseException as exc:
                            cleanup_errors.append(exc)
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
def record_session_from_environment(
    *, ordinary_only: bool = False
) -> Iterator[SessionResolutionResult]:
    """Borrow the runner's signed record capability for one fixture call.

    This does not bootstrap a fixture session or manufacture repository
    identity.  The record channel is resolved from the physical caller CWD,
    and its operation lease is always released before the context exits.
    """
    environment = os.environ
    if ordinary_only and environment.get(SIDE_EFFECT_REQUIRED_ENV) == "1":
        record = resolve_parent_side_effect_session_v2(
            env=environment,
            observed_cwd=Path.cwd().resolve(),
        )
        try:
            yield record
        finally:
            record.close()
        return
    if environment.get(PRIVATE_RECORD_REQUIRED_ENV) == "1":
        capability = RecordCapability.from_environment(
            environment, observed_cwd=Path.cwd().resolve()
        )
        with _record_session_from_capability(
            capability, observed_cwd=Path.cwd().resolve()
        ) as record:
            yield record
        return
    record = resolve_parent_side_effect_session_v2(
        env=environment,
        observed_cwd=Path.cwd().resolve(),
    )
    try:
        yield record
    finally:
        record.close()


@contextmanager
def _record_session_from_capability(
    capability: RecordCapability, *, observed_cwd: Path
) -> Iterator[SessionResolutionResult]:
    """Resolve one explicitly consumed private record transport."""
    record = resolve_parent_side_effect_session_v2(
        env={
            SIDE_EFFECT_PARENT_ROOT_ENV: str(capability.parent_root),
            SIDE_EFFECT_HANDOFF_ENV: capability.handoff,
            SIDE_EFFECT_REQUIRED_ENV: "1",
        },
        observed_cwd=observed_cwd,
    )
    if record.record.record_id != capability.record_id:
        record.close()
        raise ParentRootSideEffectError(
            ParentRootReject.HANDOFF_INVALID,
            "private record capability record_id mismatch",
        )
    if record.parent_root != capability.parent_root:
        record.close()
        raise ParentRootSideEffectError(
            ParentRootReject.ROOT_MISMATCH,
            "private record capability parent root mismatch",
        )
    try:
        yield record
    finally:
        record.close()


def record_capability_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    observed_cwd: Path | None = None,
) -> RecordCapability:
    """Materialize the private runner capability for an explicit adapter call."""
    return RecordCapability.from_environment(
        os.environ if environment is None else environment,
        observed_cwd=observed_cwd,
    )


@contextmanager
def record_environment(
    *,
    cwd: Path,
    base_env: Mapping[str, str] | None = None,
    explicit_target_dir: Path | None = None,
    explicit_path_entries: tuple[Path, ...] = (),
) -> Iterator[FixtureChildEnvironment]:
    """Expose one complete signed record environment at a physical CWD.

    This is for ordinary nested record subprocesses.  Fixture production
    commands must use :func:`run_fixture_command`, which owns channel removal
    and local-path preparation.
    """
    previous_cwd = Path.cwd()
    child: FixtureChildEnvironment | None = None
    try:
        os.chdir(cwd)
        with record_session_from_environment(ordinary_only=True) as record:
            capability = (
                record_capability_from_environment(observed_cwd=Path.cwd().resolve())
                if os.environ.get(PRIVATE_RECORD_REQUIRED_ENV) == "1"
                else RecordCapability.from_record(record)
            )
            capability.consume()
            request = build_fixture_environment_request(
                mode="ordinary_tool",
                record_capability=capability,
                ambient_env=os.environ if base_env is None else base_env,
                explicit_target_dir=explicit_target_dir,
                explicit_path_entries=explicit_path_entries,
                fixture_root=Path(cwd).resolve(strict=True),
            )
            child = project_fixture_environment(record, request=request)
            child.environment = ParentRootSideEffectBoundary().session_environment(
                record, child.environment
            )
            with record_session_context(record):
                yield child
    finally:
        if child is not None:
            child.close()
        os.chdir(previous_cwd)


def run_fixture_command(
    *,
    record: SessionResolutionResult,
    fixture_cwd: Path,
    argv: Sequence[str],
    now_mono_ns: int,
    clock: Callable[[], int] | None = None,
    ambient_env: Mapping[str, str] | None = None,
    explicit_target_dir: Path | None = None,
    request: FixtureEnvironmentRequest | None = None,
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
        ambient_env=ambient_env,
        explicit_target_dir=explicit_target_dir,
        request=request,
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
    "FixtureEnvironmentRequest",
    "RecordCapability",
    "build_fixture_environment_request",
    "bootstrap_fixture_public_environment",
    "record_capability_from_environment",
    "record_environment",
    "record_session_from_environment",
    "run_fixture_command",
]
