#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Materializes and launches the host IssueWorker publisher route.
# upstream implementation ./issue_sync.py qualifies candidates and applies Issue plans
# upstream implementation ./checkout_identity.py supplies repository identity
# upstream implementation ./model_profile_registry.py materializes publisher prompts
# upstream implementation ./tool_calls.py materializes the IssueWorker ToolCall
# downstream implementation ./agent_team.py exposes the orchestration facade
# downstream implementation ../../tests/agent_tools/test_issue_worker_dispatch.py verifies route materialization
# @dependency-end
"""Orchestrate explicit IssueWorker candidates without giving GitHub to runtime."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    # Direct execution must resolve the canonical repository package from the
    # relocated source root before importing any owner module.
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

if __package__:
    from tools.runtime.authority.checkout_identity import (
        CheckoutIdentity,
        resolve_checkout_identity,
        resolve_checkout_identity as resolve_agentcanon_checkout_identity,
    )
    from .issue_sync import (
        IssueWorkerHandoff,
        normalize_repository,
        qualify_issue_worker_finding,
    )
    from tools.agent.orchestration.model_profile_registry import (
        ContextItem,
        MaterializedPromptCapsule,
        PromptMaterializationRequest,
        load_model_profile_registry,
        materialize_prompt_capsule,
    )
    from tools.agent.orchestration.tool_calls import (
        build_issue_receipt_stage_command,
        materialize_issue_worker_tool_call,
        materialize_subagent_spawn_tool_call,
    )
else:
    from tools.runtime.authority.checkout_identity import (  # type: ignore[no-redef]
        CheckoutIdentity,
        resolve_checkout_identity,
        resolve_checkout_identity as resolve_agentcanon_checkout_identity,
    )
    from tools.repository.github.issue_sync import (  # type: ignore[no-redef]
        IssueWorkerHandoff,
        normalize_repository,
        qualify_issue_worker_finding,
    )
    from tools.agent.orchestration.model_profile_registry import (
        ContextItem,
        MaterializedPromptCapsule,
        PromptMaterializationRequest,
        load_model_profile_registry,
        materialize_prompt_capsule,
    )
    from tools.agent.orchestration.tool_calls import (  # type: ignore[no-redef]
        build_issue_receipt_stage_command,
        materialize_issue_worker_tool_call,
        materialize_subagent_spawn_tool_call,
    )


PublisherSpawn = Callable[[str, str], str | None]


@dataclass(frozen=True)
class AgentCanonRuntimeContext:
    """Resolved AgentCanon source and its resident runtime/control roots."""

    source_root: Path
    runtime_root: Path
    control_parent_root: Path


class AgentCanonRuntimeContextError(RuntimeError):
    """Raised when the IssueWorker route has no canonical runtime context."""


def resolve_agentcanon_runtime_context(
    agentcanon_source_root: Path | str | None = None,
    *,
    runtime_root: Path | str | None = None,
    control_parent_root: Path | str | None = None,
) -> AgentCanonRuntimeContext:
    """Resolve the one source-owned resident runtime used by IssueWorker.

    The installed AgentCanon checkout owns the default resident ``.runtime``
    and its control parent.  An omitted value is derived from that source
    checkout.  Explicit runtime/control paths remain supported as long as
    they are absolute; bootstrap owns creation and validation of their
    lifecycle.  The source checkout itself is never replaced by a
    HOME/workspace fallback.
    """
    source_value = (
        Path(agentcanon_source_root).expanduser()
        if agentcanon_source_root is not None
        else Path(__file__).resolve().parents[3]
    )
    if not source_value.is_absolute():
        raise AgentCanonRuntimeContextError("agentcanon_source_root_not_absolute")
    source = source_value.resolve(strict=False)
    if not source.is_dir():
        raise AgentCanonRuntimeContextError("agentcanon_source_root_missing")
    source_identity = resolve_agentcanon_checkout_identity(source)
    if source_identity.git_root in {"", "unknown"}:
        raise AgentCanonRuntimeContextError("agentcanon_source_checkout_unresolved")
    if Path(source_identity.git_root).resolve(strict=False) != source:
        raise AgentCanonRuntimeContextError("agentcanon_source_checkout_mismatch")
    if not (source / "bootstrap.sh").is_file():
        raise AgentCanonRuntimeContextError("agentcanon_bootstrap_missing")
    if not (source / "agents" / "agents_config.json").is_file():
        raise AgentCanonRuntimeContextError("agentcanon_registry_missing")

    canonical_runtime = source / ".runtime"
    canonical_control = source.parent

    def context_value(
        value: Path | str | None,
        expected: Path,
        field: str,
    ) -> Path:
        if value is None or not str(value).strip():
            return expected
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            raise AgentCanonRuntimeContextError(f"{field}_not_absolute")
        resolved = candidate.resolve(strict=False)
        return resolved

    return AgentCanonRuntimeContext(
        source_root=source,
        runtime_root=context_value(runtime_root, canonical_runtime, "runtime_root"),
        control_parent_root=context_value(
            control_parent_root, canonical_control, "control_parent_root"
        ),
    )


@dataclass(frozen=True)
class IssueWorkerDispatch:
    """One typed IssueWorker route and optional publisher launch."""

    status: str
    handoff: IssueWorkerHandoff
    checkout_identity: CheckoutIdentity
    prompt_capsule: MaterializedPromptCapsule | None = None
    tool_call: dict[str, object] | None = None
    publisher_agent_id: str | None = None
    spawn_tool_call: dict[str, object] | None = None

    def as_dict(self) -> dict[str, object]:
        """Return route evidence without credentials or private Issue bodies."""
        return {
            "status": self.status,
            "handoff": self.handoff.as_dict(),
            "checkout_identity": self.checkout_identity.as_dict(),
            "prompt_materialized": self.prompt_capsule is not None,
            "tool_call": self.tool_call,
            "publisher_agent_id": self.publisher_agent_id,
            "spawn_tool_call": self.spawn_tool_call,
        }


def dispatch_issue_worker(
    candidate: Mapping[str, object],
    objective: str,
    spawn: PublisherSpawn | None = None,
    *,
    workspace_root: Path | str = ".",
    agentcanon_source_root: Path | str | None = None,
    request_clause_ids: Sequence[str] = (),
) -> IssueWorkerDispatch:
    """Materialize and launch publisher for one explicit candidate.

    This route performs only checkout readback and prompt/ToolCall
    materialization.  The spawned publisher owns the GitHub client and must
    call ``IssueWorker.plan_publication`` and ``IssueWorker.publish``.
    """
    workspace = Path(workspace_root).expanduser().resolve()
    identity = resolve_checkout_identity(workspace)
    handoff = qualify_issue_worker_finding(
        candidate,
        authenticated_repository=identity.remote if identity.remote != "unknown" else "",
    )
    if handoff.status == "no-action":
        return IssueWorkerDispatch("no-action", handoff, identity)
    if (
        not identity.remote
        or identity.remote == "unknown"
        or normalize_repository(handoff.repository) != normalize_repository(identity.remote)
        or not handoff.can_route
    ):
        return IssueWorkerDispatch("deferred", handoff, identity)
    try:
        context = resolve_agentcanon_runtime_context(
            agentcanon_source_root,
            runtime_root=os.environ.get("AGENT_CANON_RUNTIME_ROOT", "").strip() or None,
            control_parent_root=(
                os.environ.get("AGENT_CANON_CONTROL_PARENT_ROOT", "").strip() or None
            ),
        )
    except AgentCanonRuntimeContextError:
        return IssueWorkerDispatch("deferred", handoff, identity)
    registry_root = context.source_root
    canonical_source_root = context.source_root
    bootstrap = canonical_source_root / "bootstrap.sh"
    runtime_value = context.runtime_root
    control_parent_value = context.control_parent_root
    target_root = identity.git_root
    missing_route: list[str] = []
    if target_root in {"", "unknown"}:
        missing_route.append("target_root")
        target_root = "<target-root>"
    elif not Path(target_root).expanduser().is_absolute():
        missing_route.append("target_root")
        target_root = "<target-root>"
    elif not Path(target_root).expanduser().resolve(strict=False).is_dir():
        missing_route.append("target_root")
        target_root = "<target-root>"
    else:
        target_root = str(Path(target_root).expanduser().resolve())
    publication_mode = "publish" if not missing_route else "investigate_only"
    publication_reason = "" if not missing_route else "receipt_route_unavailable:" + ",".join(missing_route)
    command_agentcanon_source_root = str(canonical_source_root)
    command_runtime_root = str(runtime_value)
    command_control_parent = str(control_parent_value)
    receipt_preflight_command = (
        build_issue_receipt_stage_command(
            repository=normalize_repository(identity.remote),
            runtime_root=command_runtime_root,
            agentcanon_source_root=command_agentcanon_source_root,
            target_root=target_root,
            control_parent_root=command_control_parent,
            checkout_identity=identity.as_dict(),
            bootstrap=str(bootstrap) if bootstrap.is_file() else "./bootstrap.sh",
            preflight=True,
        )
        if publication_mode == "publish"
        else ()
    )
    receipt_stage_command = (
        build_issue_receipt_stage_command(
            repository=normalize_repository(identity.remote),
            runtime_root=command_runtime_root,
            agentcanon_source_root=command_agentcanon_source_root,
            target_root=target_root,
            control_parent_root=command_control_parent,
            checkout_identity=identity.as_dict(),
            bootstrap=str(bootstrap) if bootstrap.is_file() else "./bootstrap.sh",
        )
        if publication_mode == "publish"
        else ()
    )
    registry = load_model_profile_registry(workspace, source_root=registry_root)
    evidence: dict[str, Any] = {
        "issue_worker_handoff": handoff.as_dict(),
        "checkout_identity": identity.as_dict(),
        "publisher_route": "issue_worker_publication",
    }
    prompt = materialize_prompt_capsule(
        PromptMaterializationRequest(
            profile_id=registry.role_profile_bindings["publisher"],
            role_id="publisher",
            context=(
                ContextItem("objective", objective),
                ContextItem(
                    "context",
                    {
                        "issue_worker": (
                            "investigate owner/cause and return deferred"
                            if publication_mode == "investigate_only"
                            else "plan then publish through the host adapter"
                        ),
                        "checkout_identity": identity.as_dict(),
                        "publication_mode": publication_mode,
                        "publication_reason": publication_reason,
                        "receipt_preflight_command": list(receipt_preflight_command),
                        "receipt_stage_command": list(receipt_stage_command),
                    },
                ),
                ContextItem("request_clause_ids", list(request_clause_ids)),
                ContextItem("owner_gate", "issue_worker_publication"),
                ContextItem("evidence", evidence),
            ),
            objective=objective,
        ),
        registry,
    )
    spawn_tool_call = materialize_subagent_spawn_tool_call(
        role="publisher",
        agent_type="worker",
        input=prompt.body,
        checkout_identity=identity.as_dict(),
        workspace_write_capable=False,
    )
    if spawn is None:
        return IssueWorkerDispatch(
            "pending",
            handoff,
            identity,
            prompt,
            spawn_tool_call=spawn_tool_call,
        )
    publisher_agent_id = spawn("publisher", prompt.body)
    if not publisher_agent_id:
        return IssueWorkerDispatch(
            "blocked",
            handoff,
            identity,
            prompt,
            spawn_tool_call=spawn_tool_call,
        )
    tool_call = materialize_issue_worker_tool_call(
        handoff=handoff.as_dict(),
        publisher_agent_id=publisher_agent_id,
        checkout_repository=normalize_repository(identity.remote),
        checkout_identity=identity.as_dict(),
        runtime_root=command_runtime_root,
        agentcanon_source_root=command_agentcanon_source_root,
        target_root=target_root,
        control_parent_root=command_control_parent,
        publication_mode=publication_mode,
        publication_reason=publication_reason,
    )
    return IssueWorkerDispatch(
        "spawned",
        handoff,
        identity,
        prompt,
        tool_call,
        publisher_agent_id,
        spawn_tool_call,
    )


__all__ = (
    "AgentCanonRuntimeContext",
    "AgentCanonRuntimeContextError",
    "IssueWorkerDispatch",
    "dispatch_issue_worker",
    "resolve_agentcanon_runtime_context",
)
