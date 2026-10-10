# @dependency-start
# contract implementation
# responsibility Provides structural refiners for decoded runtime values.
# downstream implementation ./container/devcontainer_dependencies.py narrows dependency manifest and receipt values
# downstream implementation ../agent/orchestration/model_profile_registry.py narrows registry values
# downstream implementation ../agent/orchestration/capacity_handshake.py narrows lifecycle projection values
# downstream implementation ../agent/orchestration/team_config.py narrows config values
# downstream implementation ../agent/orchestration/implementation_dispatch.py narrows packet values
# downstream implementation ../agent/skills/skill_shim_materializer.py narrows YAML frontmatter values
# downstream implementation ./lifecycle/bootstrap_agent_run.py narrows command payload values
# downstream implementation ./lifecycle/task_close.py narrows lifecycle artifact values
# @dependency-end
"""Refine only the container shape of decoded values; domain schemas stay local."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeGuard


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def is_string_object_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    """Return whether a mapping has string keys and object values."""
    return _is_object_mapping(value) and all(isinstance(key, str) for key in value)


def is_string_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    """Return whether a dictionary has string keys and object values."""
    return _is_object_dict(value) and all(isinstance(key, str) for key in value)


def is_object_list(value: object) -> TypeGuard[list[object]]:
    """Return whether a decoded value is a list of objects."""
    return isinstance(value, list)
