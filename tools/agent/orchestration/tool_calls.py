# @dependency-start
# contract tool
# responsibility Owns the retained IssueSync receipt-stage command adapter.
# upstream implementation ../../repository/github/issue_sync.py constructs resident-container publication receipt commands
# downstream test ../../../tests/agent_tools/test_tool_calls.py freezes receipt command arguments and authority boundaries
# @dependency-end
"""Build the retained native IssueSync receipt staging command."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path


def build_issue_receipt_stage_command(
    *,
    repository: str,
    runtime_root: str = "<runtime-root>",
    agentcanon_source_root: str = "<agentcanon-source-root>",
    target_root: str = "<target-root>",
    control_parent_root: str = "<control-parent-root>",
    checkout_identity: Mapping[str, object] | None = None,
    number: str = "<issue-number>",
    url: str = "<issue-url>",
    state: str = "<issue-state>",
    action: str = "<issue-action>",
    responsibility: Sequence[str] = (),
    occurrence_locations: Sequence[str] = (),
    source_finding_kind: str = "",
    execution: str = "run",
    bootstrap: str = "./bootstrap.sh",
    preflight: bool = False,
) -> tuple[str, ...]:
    """Build the canonical container command for post-publication staging."""
    if execution not in {"run", "exec"}:
        raise ValueError("receipt staging execution must be run or exec")
    if not repository.strip():
        raise ValueError("receipt staging repository is required")
    for value, field in (
        (agentcanon_source_root, "AgentCanon source root"),
        (target_root, "registered target root"),
    ):
        if value.startswith("<"):
            continue
        if not Path(value).expanduser().is_absolute():
            raise ValueError(f"receipt staging {field} must be absolute")
    if (
        bootstrap == "./bootstrap.sh"
        and agentcanon_source_root != "<agentcanon-source-root>"
    ):
        bootstrap = str(
            Path(agentcanon_source_root).expanduser().resolve() / "bootstrap.sh"
        )
    if (
        not Path(bootstrap).expanduser().is_absolute()
        and agentcanon_source_root != "<agentcanon-source-root>"
    ):
        raise ValueError("receipt staging bootstrap must be absolute")
    state_value = state.strip().casefold()
    if (
        state_value not in {"open", "closed"}
        and not state_value.startswith("<")
        and not preflight
    ):
        raise ValueError("receipt staging state must be open or closed")
    if (
        not preflight
        and action not in {"create", "update", "reopen", "reorganize", "noop"}
        and not action.startswith("<")
    ):
        raise ValueError("receipt staging action is invalid")
    command: list[str] = [
        bootstrap,
        "--control-parent-root",
        control_parent_root,
        "--runtime-root",
        runtime_root,
        "tool",
        execution,
        "--root",
        target_root,
        "issue-sync",
        "--",
        "--receipt-preflight" if preflight else "--stage-publication-receipt",
    ]
    if not preflight:
        command.extend(
            (
                "--repo",
                repository,
                "--receipt-number",
                number,
                "--receipt-url",
                url,
                "--receipt-state",
                state_value,
                "--receipt-action",
                action,
            )
        )
    identity = checkout_identity or {}
    checkout_head = str(identity.get("head") or "").strip()
    checkout_remote = str(identity.get("remote") or "").strip()
    if checkout_head:
        command.extend(("--checkout-head", checkout_head))
    if checkout_remote:
        command.extend(("--checkout-repository", checkout_remote))
    for value in responsibility:
        command.extend(("--receipt-responsibility", value))
    for value in occurrence_locations:
        command.extend(("--receipt-occurrence-location", value))
    if source_finding_kind:
        command.extend(("--receipt-source-finding-kind", source_finding_kind))
    return tuple(command)
