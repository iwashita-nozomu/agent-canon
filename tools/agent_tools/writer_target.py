#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates task-scoped writer checkout targets and rejects same-checkout writer allocation before spawn.
# upstream design ../../agents/COMMUNICATION_PROTOCOL.md owns writer handoff and checkout identity fields.
# upstream implementation ./checkout_identity.py provides the observational checkout readback.
# downstream implementation ./implementation_dispatch.py validates fixed implementation handoffs.
# downstream implementation ./manifest_rendering.py projects the handoff fields into team manifests.
# downstream implementation ../../.codex/hooks/hook_dispatcher.py enforces the active target at mutation time.
# downstream implementation ../../tests/agent_tools/test_writer_target.py validates collision and mutation boundaries.
# @dependency-end
"""Pure writer-target validation for the shared checkout boundary.

The target is an ordinary handoff value, not a lease or registry. Allocation
is checked against the writer packets that are about to be spawned. A reader
packet has no target and remains shareable.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

REMOTE_RE = re.compile(r"^[^/\s]+/[^/\s]+$")
WRITER_TARGET_SCHEMA = "agent-canon.writer-target.v1"


class WriterTargetError(ValueError):
    """Raised when a writer target or pre-spawn allocation is invalid."""


@dataclass(frozen=True, slots=True)
class WriterTarget:
    """Bind one write-capable handoff to one prepared checkout and branch."""

    checkout_root: str
    branch: str
    remote: str
    allowed_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        root = Path(self.checkout_root).expanduser()
        if not root.is_absolute():
            raise WriterTargetError("writer_target:checkout_root_must_be_absolute")
        if not self.branch or self.branch != self.branch.strip() or "\n" in self.branch:
            raise WriterTargetError("writer_target:branch_must_be_named")
        if not REMOTE_RE.fullmatch(self.remote):
            raise WriterTargetError("writer_target:remote_must_be_owner_repository")
        if not self.allowed_paths:
            raise WriterTargetError("writer_target:allowed_paths_required")
        for path in self.allowed_paths:
            candidate = Path(path)
            if (
                not path
                or candidate.is_absolute()
                or ".." in candidate.parts
                or "." in candidate.parts
                or "\\" in path
                or "//" in path
            ):
                raise WriterTargetError(
                    f"writer_target:allowed_path_not_relative:{path}"
                )

    @property
    def normalized_root(self) -> str:
        """Return the lexical absolute checkout root used for collision keys."""
        return str(Path(self.checkout_root).expanduser().resolve(strict=False))

    @property
    def normalized_remote(self) -> str:
        """Return the canonical lower-case owner/repository value."""
        return self.remote.casefold()

    def as_dict(self) -> dict[str, object]:
        """Return the closed handoff projection."""
        return {
            "schema": WRITER_TARGET_SCHEMA,
            "checkout_root": self.normalized_root,
            "branch": self.branch,
            "remote": self.normalized_remote,
            "allowed_paths": list(self.allowed_paths),
        }

    def environment(self) -> dict[str, str]:
        """Return the safe structured environment projection for PreToolUse."""
        return {
            "AGENT_CANON_CHECKOUT_ROOT": self.normalized_root,
            "AGENT_CANON_CHECKOUT_BRANCH": self.branch,
            "AGENT_CANON_WRITER_ALLOWED_PATHS": json.dumps(
                list(self.allowed_paths), separators=(",", ":")
            ),
        }


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WriterTargetError(f"writer_target:{field}_required")
    return value


def _relative_paths(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise WriterTargetError("writer_target:allowed_paths_required")
    result = tuple(_required_text(item, "allowed_path") for item in value)
    for path in result:
        candidate = Path(path)
        if (
            candidate.is_absolute()
            or ".." in candidate.parts
            or "." in candidate.parts
            or "\\" in path
            or "//" in path
        ):
            raise WriterTargetError(f"writer_target:allowed_path_not_relative:{path}")
    return result


def parse_writer_target(value: WriterTarget | Mapping[str, object]) -> WriterTarget:
    """Parse one writer target without creating files or consulting Git."""
    if isinstance(value, WriterTarget):
        return value
    if not isinstance(value, Mapping):
        raise WriterTargetError("writer_target:must_be_mapping")
    allowed_keys = {"schema", "checkout_root", "branch", "remote", "allowed_paths"}
    unknown = sorted(str(key) for key in set(value) - allowed_keys)
    if unknown:
        raise WriterTargetError(f"writer_target:unknown_fields:{','.join(unknown)}")
    schema = value.get("schema", WRITER_TARGET_SCHEMA)
    if schema != WRITER_TARGET_SCHEMA:
        raise WriterTargetError("writer_target:schema_mismatch")
    remote = _required_text(value.get("remote"), "remote").casefold()
    return WriterTarget(
        checkout_root=_required_text(value.get("checkout_root"), "checkout_root"),
        branch=_required_text(value.get("branch"), "branch"),
        remote=remote,
        allowed_paths=_relative_paths(value.get("allowed_paths")),
    )


def validate_writer_target_identity(
    target: WriterTarget | Mapping[str, object],
    checkout_identity: Mapping[str, object],
) -> WriterTarget:
    """Require the observed prepared checkout to match the handoff target."""
    parsed = parse_writer_target(target)
    if not isinstance(checkout_identity, Mapping):
        raise WriterTargetError("writer_target:checkout_identity_required")
    git_root = checkout_identity.get("git_root")
    cwd = checkout_identity.get("cwd")
    branch = checkout_identity.get("branch")
    remote = checkout_identity.get("remote")
    if (
        not isinstance(git_root, str)
        or Path(git_root).resolve(strict=False) != Path(parsed.normalized_root)
        or not isinstance(cwd, str)
        or Path(cwd).resolve(strict=False) != Path(parsed.normalized_root)
    ):
        raise WriterTargetError("writer_target:checkout_root_identity_mismatch")
    if branch != parsed.branch:
        raise WriterTargetError("writer_target:branch_identity_mismatch")
    if remote != parsed.normalized_remote:
        raise WriterTargetError("writer_target:remote_identity_mismatch")
    return parsed


def validate_writer_target_allocations(
    allocations: Sequence[Mapping[str, object] | WriterTarget | None],
) -> tuple[WriterTarget, ...]:
    """Validate writer packets before spawn and reject shared checkout roots.

    Mapping packets use ``write_capable`` and ``writer_target``. A packet with
    ``write_capable=false`` is a reader and may omit its target. A writer must
    carry a target; duplicate normalized checkout roots are rejected before any
    spawn callback can run.
    """
    writers: list[WriterTarget] = []
    owners: dict[str, str] = {}
    for index, allocation in enumerate(allocations):
        if isinstance(allocation, WriterTarget):
            write_capable = True
            value: object = allocation
            owner = str(index)
        elif isinstance(allocation, Mapping):
            write_capable = bool(allocation.get("write_capable", False))
            value = allocation.get("writer_target")
            owner = str(allocation.get("owner", allocation.get("role_id", index)))
        elif allocation is None:
            write_capable = False
            value = None
            owner = str(index)
        else:
            raise WriterTargetError(f"writer_target:allocation_not_mapping:{index}")
        if not write_capable:
            continue
        if value is None:
            raise WriterTargetError(f"writer_target:required_before_spawn:{owner}")
        target = parse_writer_target(value)  # type: ignore[arg-type]
        prior = owners.get(target.normalized_root)
        if prior is not None:
            raise WriterTargetError(
                "writer_target:checkout_root_collision:"
                f"{prior}:{owner}:{target.normalized_root}"
            )
        owners[target.normalized_root] = owner
        writers.append(target)
    return tuple(writers)


def validate_wave_writer_targets(
    slots: Sequence[object],
    writer_targets: Mapping[str, WriterTarget | Mapping[str, object] | None] | None = None,
) -> tuple[WriterTarget, ...]:
    """Validate role-instance slots with targets supplied by the handoff."""
    allocations: list[Mapping[str, object]] = []
    targets = writer_targets or {}
    for slot in slots:
        role_id = str(getattr(slot, "role_id", ""))
        identity = str(getattr(slot, "executable_identity", role_id))
        target = targets.get(
            identity,
            targets.get(role_id, getattr(slot, "writer_target", None)),
        )
        write_capable = bool(getattr(slot, "write_capable", False) or target is not None)
        allocations.append(
            {
                "owner": identity,
                "write_capable": write_capable,
                "writer_target": target,
            }
        )
    return validate_writer_target_allocations(allocations)


__all__ = (
    "WRITER_TARGET_SCHEMA",
    "WriterTarget",
    "WriterTargetError",
    "parse_writer_target",
    "validate_wave_writer_targets",
    "validate_writer_target_allocations",
    "validate_writer_target_identity",
)
