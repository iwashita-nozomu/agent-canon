#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Owns the canonical v2 experiment identity tuple and path/ref grammar.
# upstream design ../../documents/experiments/experiment-registry.md defines experiment identity.
# downstream implementation ./run_managed_experiment.py, ./save_experiment_result_annex.py, ./update_latest_result.py consume this owner.
# @dependency-end
"""Canonical identity and path helpers for managed experiment runs.

The identity is deliberately kept in one small owner.  Filesystem, report,
branch, manifest, and latest-result consumers must all compare this value
instead of independently parsing individual path components.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

IDENTITY_SCHEMA = "agentcanon.experiment-run-identity/v2"
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ExperimentIdentityError(ValueError):
    """Raised when an experiment identity or identity-bearing path is invalid."""


class DuplicateJSONKeyError(ValueError):
    """Raised when a JSON object repeats one key."""


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build one JSON object while rejecting duplicate keys at every depth."""
    object_value: dict[str, object] = {}
    for key, value in pairs:
        if key in object_value:
            raise DuplicateJSONKeyError(f"duplicate JSON object key: {key!r}")
        object_value[key] = value
    return object_value


def load_json_text(text: str | bytes) -> object:
    """Decode JSON with duplicate-key rejection before mapping consumers run."""
    return json.loads(text, object_pairs_hook=_reject_duplicate_pairs)


def load_json_file(path: Path) -> object:
    """Read and decode one JSON file through the canonical strict decoder."""
    return load_json_text(path.read_bytes())


def validate_segment(value: object, field: str = "segment") -> str:
    """Validate and return one safe identity path/ref segment."""
    if not isinstance(value, str) or not value:
        raise ExperimentIdentityError(f"{field} must be a non-empty string")
    if value in {".", ".."}:
        raise ExperimentIdentityError(f"{field} must not be . or ..")
    if any(char in value for char in ("/", "\\", "\x00")):
        raise ExperimentIdentityError(f"{field} must not contain a path separator or NUL")
    if any(char.isspace() for char in value):
        raise ExperimentIdentityError(f"{field} must not contain whitespace")
    if unicodedata.normalize("NFKC", value) != value:
        raise ExperimentIdentityError(f"{field} must not change under normalization")
    if _SAFE_SEGMENT.fullmatch(value) is None:
        raise ExperimentIdentityError(
            f"{field} must match [A-Za-z0-9][A-Za-z0-9._-]*"
        )
    return value


@dataclass(frozen=True, order=True)
class ExperimentIdentity:
    """The immutable ordered identity tuple ``(topic, variant, run_name)``."""

    topic: str
    variant: str
    run_name: str

    def __post_init__(self) -> None:
        """Validate every identity component at value construction time."""
        validate_segment(self.topic, "topic")
        validate_segment(self.variant, "variant")
        validate_segment(self.run_name, "run_name")

    def _inner_dict(self) -> dict[str, str]:
        return {
            "schema": IDENTITY_SCHEMA,
            "topic": self.topic,
            "variant": self.variant,
            "run_name": self.run_name,
        }

    def to_dict(self) -> dict[str, object]:
        """Return the one canonical nested wire representation."""
        return {"identity": self._inner_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> ExperimentIdentity:
        """Parse the canonical nested representation, rejecting duplicates."""
        if not isinstance(payload, Mapping):
            raise ExperimentIdentityError("identity payload must be an object")
        nested = payload.get("identity")
        if not isinstance(nested, Mapping):
            raise ExperimentIdentityError("identity payload must contain an identity object")
        if any(key in payload for key in ("topic", "variant", "run_name")):
            raise ExperimentIdentityError("identity fields must not be duplicated at top level")
        if set(nested) != {"schema", "topic", "variant", "run_name"}:
            raise ExperimentIdentityError("identity object has missing or extra fields")
        if nested.get("schema") != IDENTITY_SCHEMA:
            raise ExperimentIdentityError("identity schema must be agentcanon.experiment-run-identity/v2")
        return cls(
            topic=validate_segment(nested.get("topic"), "topic"),
            variant=validate_segment(nested.get("variant"), "variant"),
            run_name=validate_segment(nested.get("run_name"), "run_name"),
        )


def result_relative_path(identity: ExperimentIdentity) -> Path:
    """Return the canonical repository-relative compact result directory."""
    return Path("experiments") / identity.topic / "result" / identity.variant / identity.run_name


def raw_relative_path(identity: ExperimentIdentity) -> Path:
    """Return the canonical repository-relative bulky raw directory."""
    return Path("experiments") / identity.topic / "raw" / identity.variant / identity.run_name


def identity_from_raw_relative_path(path: Path) -> ExperimentIdentity:
    """Invert one canonical raw path through the sole identity grammar owner."""
    if path.is_absolute() or ".." in path.parts:
        raise ExperimentIdentityError("raw path must be repository-relative and contained")
    parts = path.parts
    if len(parts) != 5 or parts[0] != "experiments" or parts[2] != "raw":
        raise ExperimentIdentityError(
            "raw path must be experiments/<topic>/raw/<variant>/<run_name>"
        )
    identity = ExperimentIdentity(parts[1], parts[3], parts[4])
    if path != raw_relative_path(identity):
        raise ExperimentIdentityError("raw path is not canonical for its identity")
    return identity


def report_relative_path(identity: ExperimentIdentity) -> Path:
    """Return the canonical repository-relative reader report path."""
    return (
        Path("experiments")
        / "report"
        / identity.topic
        / identity.variant
        / f"{identity.run_name}.md"
    )


def contained_path(repo_root: Path, path: Path) -> Path:
    """Resolve a path and require that it remains inside ``repo_root``."""
    root = repo_root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ExperimentIdentityError(f"path is outside repository: {path}") from exc
    return resolved


def identity_from_manifest(payload: Mapping[str, object]) -> ExperimentIdentity:
    """Parse an identity envelope from a manifest or lifecycle payload."""
    return ExperimentIdentity.from_dict(payload)


__all__ = [
    "IDENTITY_SCHEMA",
    "DuplicateJSONKeyError",
    "ExperimentIdentity",
    "ExperimentIdentityError",
    "contained_path",
    "identity_from_manifest",
    "identity_from_raw_relative_path",
    "load_json_file",
    "load_json_text",
    "raw_relative_path",
    "report_relative_path",
    "result_relative_path",
    "validate_segment",
]
