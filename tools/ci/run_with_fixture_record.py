#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Opens one unit-owned public supervisor and private record before executing fixture-producing validation.
# upstream implementation ../agent_tools/parent_root_side_effects.py owns signed supervisor/record lifecycle and child environment projection
# downstream implementation ./run_standalone_static_gate_unit.sh uses the adapter when no private record capability is inherited
# downstream implementation ../../tests/tools/test_standalone_static_gate_record_bootstrap.py verifies the capability and command boundary
# @dependency-end

"""Execute one validation command with a dedicated fixture record capability.

The adapter is intentionally above individual tests.  It creates one independent
public supervisor for the validation unit, issues one private record bound to the
same physical repository, and projects both channels into the child process.
Ambient public/private channels are inputs to classify and scrub; they are never
reused as repository identity for the new unit.
"""

from __future__ import annotations

import argparse
import os
import secrets
import signal
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from tools.agent_tools.parent_root_side_effects import (
    PRIVATE_RECORD_HANDOFF_ENV,
    PRIVATE_RECORD_PARENT_ROOT_ENV,
    PRIVATE_RECORD_REQUIRED_ENV,
    RUNNER_OWNED_AMBIENT_KEYS,
    SIDE_EFFECT_HANDOFF_ENV,
    SIDE_EFFECT_PARENT_ROOT_ENV,
    SIDE_EFFECT_REQUIRED_ENV,
    ParentRootReject,
    ParentRootSideEffectBoundary,
    ParentRootSideEffectError,
    current_supervisor_issuer,
    public_session,
    session_environment,
)

_CHANNEL_KEYS = (
    SIDE_EFFECT_PARENT_ROOT_ENV,
    SIDE_EFFECT_HANDOFF_ENV,
    SIDE_EFFECT_REQUIRED_ENV,
    PRIVATE_RECORD_PARENT_ROOT_ENV,
    PRIVATE_RECORD_HANDOFF_ENV,
    PRIVATE_RECORD_REQUIRED_ENV,
)
_FORWARDED_SIGNALS = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)


def _validated_command(argv: Sequence[str]) -> tuple[str, ...]:
    """Return one non-empty argv tuple without shell interpretation."""
    command = tuple(argv)
    if command and command[0] == "--":
        command = command[1:]
    if not command or any(not item or "\x00" in item for item in command):
        raise ParentRootSideEffectError(
            ParentRootReject.INPUT_INVALID,
            "fixture-record command argv is invalid",
        )
    return command


def _channel_state(
    environment: Mapping[str, str],
    *,
    parent_key: str,
    handoff_key: str,
    required_key: str,
    label: str,
) -> str:
    """Classify one canonical three-field transport as absent or complete."""
    parent = environment.get(parent_key, "")
    handoff = environment.get(handoff_key, "")
    required = environment.get(required_key, "")
    if not parent and not handoff and not required:
        return "absent"
    if parent and handoff and required == "1":
        return "complete"
    raise ParentRootSideEffectError(
        ParentRootReject.HANDOFF_INVALID,
        f"{label}_channel_incomplete",
    )


def _bootstrap_process_environment(
    ambient: Mapping[str, str],
) -> dict[str, str]:
    """Classify and remove inherited identity before opening an owner session."""
    public_state = _channel_state(
        ambient,
        parent_key=SIDE_EFFECT_PARENT_ROOT_ENV,
        handoff_key=SIDE_EFFECT_HANDOFF_ENV,
        required_key=SIDE_EFFECT_REQUIRED_ENV,
        label="public",
    )
    private_state = _channel_state(
        ambient,
        parent_key=PRIVATE_RECORD_PARENT_ROOT_ENV,
        handoff_key=PRIVATE_RECORD_HANDOFF_ENV,
        required_key=PRIVATE_RECORD_REQUIRED_ENV,
        label="private_record",
    )
    if private_state == "complete":
        if public_state != "complete":
            raise ParentRootSideEffectError(
                ParentRootReject.HANDOFF_INVALID,
                "private_record_without_public_supervisor",
            )
        raise ParentRootSideEffectError(
            ParentRootReject.HANDOFF_INVALID,
            "fixture_record_capability_already_present",
        )

    environment = dict(ambient)
    for key in _CHANNEL_KEYS:
        environment.pop(key, None)
    return environment


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    """Bound cleanup of the exact child process group owned by this adapter."""
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def run_with_fixture_record(
    *,
    invocation_script: Path,
    purpose: str,
    argv: Sequence[str],
) -> int:
    """Run argv beneath one independently owned supervisor/record product."""
    command = _validated_command(argv)
    if not purpose or purpose != purpose.strip():
        raise ParentRootSideEffectError(
            ParentRootReject.INPUT_INVALID,
            "fixture-record purpose is invalid",
        )
    script = invocation_script.resolve(strict=True)
    if not script.is_file():
        raise ParentRootSideEffectError(
            ParentRootReject.INPUT_INVALID,
            "fixture-record invocation script is not a file",
        )

    ambient = os.environ.copy()
    bootstrap_environment = _bootstrap_process_environment(ambient)
    os.environ.clear()
    os.environ.update(bootstrap_environment)
    process: subprocess.Popen[bytes] | None = None
    interrupted_signal: int | None = None
    previous_handlers: dict[int, object] = {}

    try:
        with public_session(
            invocation_script=script,
            purpose=purpose,
            independent=True,
            cleanup_state=True,
        ) as supervisor:
            issuer = current_supervisor_issuer()
            if issuer is None:
                raise ParentRootSideEffectError(
                    ParentRootReject.HANDOFF_INVALID,
                    "fixture-record supervisor issuer is missing",
                )
            child = issuer.issue_child(
                role="record",
                record_id=f"fixture-{secrets.token_hex(16)}",
                physical_root=supervisor.parent_root,
                now_mono_ns=time.monotonic_ns(),
            )

            child_base = session_environment(supervisor, ambient)
            child_base = {
                key: value
                for key, value in child_base.items()
                if key not in RUNNER_OWNED_AMBIENT_KEYS
            }
            environment = ParentRootSideEffectBoundary().child_environment(
                supervisor.attestation,
                child_base,
                explicit_overrides=None,
                issue_handoff=False,
                rebase_inherited_temp=True,
            )
            environment[PRIVATE_RECORD_PARENT_ROOT_ENV] = str(supervisor.parent_root)
            environment[PRIVATE_RECORD_HANDOFF_ENV] = child.handoff
            environment[PRIVATE_RECORD_REQUIRED_ENV] = "1"

            def forward_signal(signum: int, _frame: object) -> None:
                nonlocal interrupted_signal
                if interrupted_signal is None:
                    interrupted_signal = signum
                if process is not None and process.poll() is None:
                    try:
                        os.killpg(process.pid, signum)
                    except ProcessLookupError:
                        pass

            previous_handlers = {
                signum: signal.getsignal(signum) for signum in _FORWARDED_SIGNALS
            }
            for signum in _FORWARDED_SIGNALS:
                signal.signal(signum, forward_signal)

            process = subprocess.Popen(
                command,
                cwd=Path.cwd(),
                env=environment,
                start_new_session=True,
            )
            returncode = process.wait()
            if interrupted_signal is not None:
                return 128 + interrupted_signal
            return returncode
    finally:
        if process is not None:
            _terminate_process_group(process)
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)  # pyright: ignore[reportArgumentType]
        os.environ.clear()
        os.environ.update(ambient)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="run one validation command with a private fixture record"
    )
    parser.add_argument("--invocation-script", required=True, type=Path)
    parser.add_argument("--purpose", required=True)
    parser.add_argument("argv", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return run_with_fixture_record(
            invocation_script=args.invocation_script,
            purpose=args.purpose,
            argv=args.argv,
        )
    except (OSError, ValueError, ParentRootSideEffectError) as error:
        print(
            "FIXTURE_RECORD_BOOTSTRAP=fail "
            f"error={type(error).__name__} detail={error}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
