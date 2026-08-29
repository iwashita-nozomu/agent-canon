#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides typed source-derived dependency query/context and explicit persisted graph runtime commands.
# upstream design ../../agents/canonical/CLI_ENTRYPOINTS.md explicit persisted graph command contract
# upstream design ../../documents/design/dependency-manifest-design.md tracked-source dependency semantics
# upstream implementation ./source_dependency_graph.py derives dependency query and context without runtime state
# upstream implementation ../../rust/agent-canon/src/graph.rs owns opt-in persisted graph build/status and non-dependency relations
# downstream implementation ./check_design_doc_claims.py consumes source-derived dependency context
# downstream implementation ./tool_drift.py consumes source-derived dependency facts
# downstream implementation ./vector_search.py consumes source-derived dependency facts
# @dependency-end
"""Typed compatibility adapter for source dependency projections and opt-in graph runtime."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

try:
    from .source_dependency_graph import (
        SourceDependencyError,
        build_context_projection,
        build_dependency_projection,
    )
except ImportError:  # pragma: no cover - direct CLI import
    from source_dependency_graph import (
        SourceDependencyError,
        build_context_projection,
        build_dependency_projection,
    )

GRAPH_COMMANDS = frozenset({"build", "status", "query", "context"})
GRAPH_RELATIONS = frozenset(
    {
        "all",
        "dependency",
        "owner",
        "scope",
        "import",
        "include",
        "symbol",
        "call",
        "containment",
        "document",
        "catalog",
        "pin",
        "view",
        "generated",
        "submodule",
        "public",
    }
)
GRAPH_DIRECTIONS = frozenset({"outgoing", "incoming", "both"})
CANONICAL_GRAPH_EXECUTABLE = Path(__file__).resolve().parents[1] / "bin" / "agent-canon"


class GraphClientError(RuntimeError):
    """Source projection or explicit graph runtime response validation failed."""


@dataclass(frozen=True)
class GraphSourceIdentity:
    """Exact source identity returned by dependency context."""

    snapshot_commit: str
    source_path: str
    content_sha256: str


@dataclass(frozen=True)
class GraphDependencyFact:
    """One explicit dependency declaration projected from source or graph rows."""

    id: str
    direction: str
    kind: str
    source: str
    target: str
    reason: str
    producer: str
    source_path: str | None
    source_span: Mapping[str, object] | None
    evidence_ref: str
    authority: str


@dataclass(frozen=True)
class GraphResponse:
    """One source-derived or persisted graph response."""

    schema: str
    command: str
    status: str
    payload: Mapping[str, object]
    exit_code: int

    @property
    def source_identity(self) -> GraphSourceIdentity | None:
        """Return the source-bound identity carried by dependency context."""
        if self.command != "context":
            return None
        resolved = self.payload.get("resolved_path")
        raw = self.payload.get("source_identity")
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise GraphClientError("graph context source_identity must be an object")
        identity = cast(dict[str, object], raw)
        required = {"snapshot_commit", "source_path", "content_sha256"}
        if set(identity) != required:
            raise GraphClientError("graph context source_identity fields are not canonical")
        values = tuple(identity.get(field) for field in required)
        if any(not isinstance(value, str) or not value for value in values):
            raise GraphClientError("graph context source_identity has empty fields")
        if resolved is not None and resolved != identity["source_path"]:
            raise GraphClientError("graph context source identity path mismatch")
        content = cast(str, identity["content_sha256"])
        if len(content) != 64 or any(
            character not in "0123456789abcdef" for character in content
        ):
            raise GraphClientError("graph context source identity hash is invalid")
        return GraphSourceIdentity(
            cast(str, identity["snapshot_commit"]),
            cast(str, identity["source_path"]),
            content,
        )

    @property
    def dependency_facts(self) -> tuple[GraphDependencyFact, ...]:
        """Project explicit dependency facts using response node identities."""
        if self.command != "query":
            return ()
        raw_nodes = self.payload.get("nodes")
        raw_facts = self.payload.get("facts")
        if not isinstance(raw_nodes, list) or not isinstance(raw_facts, list):
            raise GraphClientError("graph query nodes/facts must be arrays")
        paths: dict[str, str] = {}
        for raw_node in raw_nodes:
            if not isinstance(raw_node, dict):
                raise GraphClientError("graph node must be an object")
            node = cast(dict[str, object], raw_node)
            node_id = node.get("id")
            endpoint = node.get("path") or node.get("selector")
            if (
                not isinstance(node_id, str)
                or not isinstance(endpoint, str)
                or not endpoint
            ):
                raise GraphClientError("graph node identity is incomplete")
            if node_id in paths:
                raise GraphClientError(f"duplicate graph node id: {node_id}")
            paths[node_id] = endpoint
        projected: list[GraphDependencyFact] = []
        for raw_fact in raw_facts:
            if not isinstance(raw_fact, dict):
                raise GraphClientError("graph fact must be an object")
            fact = cast(dict[str, object], raw_fact)
            if fact.get("kind") != "dependency" or fact.get("inferred") is True:
                continue
            if fact.get("inferred") is not False:
                raise GraphClientError("explicit dependency fact inferred must be false")
            fact_id = _required_string(fact, "id", "graph fact")
            source_id = _required_string(fact, "from", fact_id)
            target_id = _required_string(fact, "to", fact_id)
            if source_id not in paths or target_id not in paths:
                raise GraphClientError(f"graph fact {fact_id} endpoint is absent from nodes")
            detail = _required_mapping(
                fact.get("dependency_detail"),
                f"graph fact {fact_id}.dependency_detail",
            )
            projected.append(
                GraphDependencyFact(
                    fact_id,
                    _required_string(detail, "direction", "dependency detail"),
                    _required_string(detail, "kind", "dependency detail"),
                    paths[source_id],
                    paths[target_id],
                    _required_string(detail, "reason", "dependency detail"),
                    _required_string(fact, "producer", fact_id),
                    _optional_string(fact.get("source_path")),
                    _optional_mapping(fact.get("source_span")),
                    _required_string(fact, "evidence_ref", fact_id),
                    _required_string(fact, "authority", fact_id),
                )
            )
        return tuple(
            sorted(
                projected,
                key=lambda item: (
                    item.source,
                    item.target,
                    item.direction,
                    item.kind,
                    item.id,
                ),
            )
        )


class GraphClient:
    """Read dependency facts from source and invoke persisted graph only explicitly."""

    def __init__(self, root: Path, executable: Path | None = None) -> None:
        """Bind one repository root and optional persisted graph executable."""
        self.root = root.resolve()
        self.executable = (executable or CANONICAL_GRAPH_EXECUTABLE).resolve()

    def invoke(self, command: str, options: Sequence[str] = ()) -> GraphResponse:
        """Invoke one explicit persisted graph command and validate its JSON response."""
        if command not in GRAPH_COMMANDS:
            raise GraphClientError(f"unsupported graph command: {command}")
        argv = [
            str(self.executable),
            "graph",
            command,
            "--root",
            str(self.root),
            "--format",
            "json",
            *options,
        ]
        try:
            process = subprocess.run(argv, check=False, capture_output=True, text=True)
        except OSError as error:
            raise GraphClientError(f"process launch failed: {error}") from error
        try:
            payload = json.loads(process.stdout)
        except json.JSONDecodeError as error:
            raise GraphClientError(f"graph response is not JSON: {error}") from error
        if not isinstance(payload, dict):
            raise GraphClientError("graph response must be an object")
        typed = cast(dict[str, object], payload)
        schema = typed.get("schema")
        response_command = typed.get("command")
        status = typed.get("status")
        if not all(
            isinstance(value, str) and value
            for value in (schema, response_command, status)
        ):
            raise GraphClientError("graph response identity is incomplete")
        if response_command != command:
            raise GraphClientError("graph response command mismatch")
        expected_schema = f"agent-canon.graph.{command}.v1"
        if schema != expected_schema:
            raise GraphClientError("graph response schema mismatch")
        payload_exit = typed.get("exit_code")
        if type(payload_exit) is not int or payload_exit != process.returncode:
            raise GraphClientError("graph response exit status mismatch")
        if status not in {"fresh", "incomplete", "stale", "unavailable"}:
            raise GraphClientError("graph response status is invalid")
        return GraphResponse(
            cast(str, schema),
            command,
            cast(str, status),
            typed,
            process.returncode,
        )

    def build(self) -> GraphResponse:
        """Build one opt-in persisted graph transaction."""
        return self.invoke("build")

    def status(self) -> GraphResponse:
        """Read opt-in persisted graph status without rebuilding producers."""
        return self.invoke("status")

    def query(
        self,
        *,
        path: str | None = None,
        relation: str = "dependency",
        direction: str = "both",
        depth: int = 0,
        all_nodes: bool = False,
        **legacy_options: bool,
    ) -> GraphResponse:
        """Query dependency source directly; use runtime for other graph relations."""
        legacy_all = legacy_options.pop("all", None)
        if legacy_options:
            unsupported = ",".join(sorted(legacy_options))
            raise GraphClientError(f"unsupported graph query options: {unsupported}")
        if legacy_all is not None:
            if all_nodes and legacy_all is not all_nodes:
                raise GraphClientError("conflicting all/all_nodes graph query options")
            all_nodes = legacy_all
        if relation not in GRAPH_RELATIONS:
            raise GraphClientError(f"unsupported graph relation: {relation}")
        if direction not in GRAPH_DIRECTIONS:
            raise GraphClientError(f"unsupported graph direction: {direction}")
        if depth < 0:
            raise GraphClientError("graph query depth must be non-negative")
        if (
            relation == "dependency"
            and direction == "both"
            and depth == 0
            and all_nodes
            and path is None
        ):
            try:
                projection = build_dependency_projection(self.root)
            except SourceDependencyError as error:
                raise GraphClientError(f"source dependency projection failed: {error}") from error
            return GraphResponse(
                schema="agent-canon.graph.query.v1",
                command="query",
                status="fresh",
                payload={
                    **projection.payload(),
                    "exit_code": 0,
                },
                exit_code=0,
            )
        options = [
            "--relation",
            relation,
            "--direction",
            direction,
            "--depth",
            str(depth),
        ]
        if path is not None:
            options.extend(("--path", path))
        if all_nodes:
            options.append("--all")
        return self.invoke("query", options)

    def context(self, path: str, token: str | None = None) -> GraphResponse:
        """Read dependency context from source; token context remains opt-in runtime."""
        if token is None:
            try:
                projection = build_context_projection(self.root, path)
            except SourceDependencyError as error:
                raise GraphClientError(f"source dependency context failed: {error}") from error
            return GraphResponse(
                schema="agent-canon.graph.context.v1",
                command="context",
                status="fresh",
                payload={
                    **projection.payload(),
                    "exit_code": 0,
                },
                exit_code=0,
            )
        return self.invoke("context", ("--path", path, "--token", token))


def _required_string(value: Mapping[str, object], field: str, owner: str) -> str:
    candidate = value.get(field)
    if not isinstance(candidate, str) or not candidate:
        raise GraphClientError(f"{owner}.{field} must be nonempty text")
    return candidate


def _required_mapping(value: object, owner: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise GraphClientError(f"{owner} must be an object")
    return cast(Mapping[str, object], value)


def _optional_mapping(value: object) -> Mapping[str, object] | None:
    if value is None:
        return None
    return _required_mapping(value, "graph optional mapping")


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise GraphClientError("graph optional string is invalid")
    return value
