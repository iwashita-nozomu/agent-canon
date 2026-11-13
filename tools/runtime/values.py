# @dependency-start
# contract implementation
# responsibility Provides structural refiners for decoded runtime values.
# downstream implementation dispatch/agent-canon/src/environment_dependencies.rs owns native dependency manifest and receipt values
# downstream implementation ./dispatch/agent-canon/src/codex_agent_role_eval/model_profiles.rs parses registry values
# downstream implementation ../agent/orchestration/team_config.py narrows config values
# downstream implementation ../agent/orchestration/packets.py narrows packet values
# downstream implementation ./artifacts/artifact_identity.py narrows canonical JSON maps
# downstream implementation ./dispatch/agent-canon/src/catalog/skill_materialization.rs parses YAML frontmatter values natively
# @dependency-end
"""Refine only the container shape of decoded values; domain schemas stay local."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeGuard


def is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    """Return whether a decoded value is a mapping, preserving dynamic key types."""
    return isinstance(value, Mapping)


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def is_string_object_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    """Return whether a mapping has string keys and object values."""
    return is_object_mapping(value) and all(isinstance(key, str) for key in value)


def is_string_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    """Return whether a dictionary has string keys and object values."""
    return _is_object_dict(value) and all(isinstance(key, str) for key in value)


def is_object_list(value: object) -> TypeGuard[list[object]]:
    """Return whether a decoded value is a list of objects."""
    return isinstance(value, list)


def is_object_list_or_tuple(
    value: object,
) -> TypeGuard[list[object] | tuple[object, ...]]:
    """Refine the list-or-tuple container accepted by normalized packet APIs."""
    return isinstance(value, (list, tuple))
