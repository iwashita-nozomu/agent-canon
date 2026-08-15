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
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from tools.agent_tools.parent_root_side_effects import (
    FixtureExecutionReceipt,
    ParentRootReject,
    ParentRootSideEffectBoundary,
    ParentRootSideEffectError,
    SessionResolutionResult,
    fixture_direct_command,
    resolve_parent_side_effect_session_v2,
)


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


__all__ = ["record_environment", "record_session_from_environment", "run_fixture_command"]
