#!/usr/bin/env python3
# @dependency-start
# responsibility Provides registry lib experiment workflow tooling.
# upstream design ../README.md shared automation index
# @dependency-end

"""Shared helpers for experiment registry tooling."""

from __future__ import annotations

import json
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]


DEFAULTS_KEY_ORDER = (
    "managed_runner",
    "report_root",
    "integration_branch",
    "topic_template_dir",
    "required_eval_artifacts",
    "optional_eval_artifacts",
)
TOPIC_KEY_ORDER = (
    "name",
    "status",
    "topic_dir",
    "topic_readme",
    "canonical_entrypoint",
    "result_root",
    "report_root",
    "default_variant",
    "smoke_inner_command",
    "formal_inner_command",
    "required_eval_artifacts",
    "optional_eval_artifacts",
    "primary_note",
    "active_branch",
    "active_worktree",
    "scope_file",
    "branch_note",
)


def load_registry(path: Path) -> dict[str, object]:
    """Load one TOML registry file."""
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError("experiment registry TOML root must be a table")
    return data


def registry_topics(registry: dict[str, object]) -> list[dict[str, object]]:
    """Return the topic table list."""
    raw_topics = registry.get("topics", [])
    if not isinstance(raw_topics, list):
        raise ValueError("experiment registry must contain [[topics]]")
    topics: list[dict[str, object]] = []
    for index, raw_topic in enumerate(raw_topics):
        if not isinstance(raw_topic, dict):
            raise ValueError(f"topics[{index}] must be a table")
        topics.append(raw_topic)
    return topics


def find_topic(registry: dict[str, object], topic_name: str) -> dict[str, object] | None:
    """Return one topic entry by name."""
    for topic in registry_topics(registry):
        if topic.get("name") == topic_name:
            return topic
    return None


def _serialize_scalar(value: object) -> str:
    """Serialize one TOML scalar for the limited registry schema."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    raise TypeError(f"unsupported TOML scalar value: {value!r}")


def _serialize_value(value: object) -> str:
    """Serialize one TOML value for the limited registry schema."""
    if isinstance(value, list):
        return "[" + ", ".join(_serialize_scalar(item) for item in value) + "]"
    return _serialize_scalar(value)


def _ordered_items(data: dict[str, object], preferred_order: tuple[str, ...]) -> list[tuple[str, object]]:
    """Return dictionary items in deterministic order."""
    ordered: list[tuple[str, object]] = []
    seen: set[str] = set()
    for key in preferred_order:
        if key in data:
            ordered.append((key, data[key]))
            seen.add(key)
    for key in sorted(data):
        if key not in seen:
            ordered.append((key, data[key]))
    return ordered


def write_registry(path: Path, registry: dict[str, object]) -> None:
    """Write one registry file in deterministic TOML form."""
    defaults = registry.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ValueError("defaults must be a table")
    topics = registry_topics(registry)

    lines: list[str] = []
    schema_version = registry.get("schema_version", 1)
    if not isinstance(schema_version, int):
        raise ValueError("schema_version must be an integer")
    lines.append(f"schema_version = {schema_version}")
    lines.append("")
    lines.append("[defaults]")
    for key, value in _ordered_items(defaults, DEFAULTS_KEY_ORDER):
        if value is None:
            continue
        lines.append(f"{key} = {_serialize_value(value)}")

    for topic in topics:
        lines.append("")
        lines.append("[[topics]]")
        for key, value in _ordered_items(topic, TOPIC_KEY_ORDER):
            if value is None:
                continue
            lines.append(f"{key} = {_serialize_value(value)}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
