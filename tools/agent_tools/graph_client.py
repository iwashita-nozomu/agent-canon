#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides the sole Python adapter for canonical AgentCanon graph JSON commands.
# upstream design ../../agents/canonical/CLI_ENTRYPOINTS.md canonical graph command contract
# upstream implementation ../../rust/agent-canon/src/graph.rs owns graph build, status, query, and context semantics
# downstream implementation ./check_dependency_headers.py consumes verified manifest metadata
# downstream implementation ./check_design_doc_claims.py consumes graph context for claim evidence
# downstream implementation ./search.py consumes dependency graph results without parsing source manifests
# downstream implementation ./tool_drift.py consumes dependency graph results for drift policy
# @dependency-end
"""Typed subprocess adapter for the canonical AgentCanon graph CLI."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

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
GRAPH_EXIT_CODES = frozenset(range(6))
CANONICAL_GRAPH_EXECUTABLE = Path(__file__).resolve().parents[1] / "bin" / "agent-canon"


class GraphClientError(RuntimeError):
    """Canonical graph invocation or schema validation failed."""


@dataclass(frozen=True)
class GraphDependencyFact:
    """One explicit manifest declaration projected from canonical graph rows."""

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
class GraphSourceIdentity:
    """Exact source-snapshot identity returned by graph context."""

    snapshot_commit: str
    source_path: str
    content_sha256: str


@dataclass(frozen=True)
class GraphResponse:
    """One parsed command-specific graph response, including valid nonzero states."""

    schema: str
    command: str
    status: str
    payload: Mapping[str, object]
    exit_code: int

    @property
    def source_identity(self) -> GraphSourceIdentity | None:
        """Return the validated context source tuple without consumer-side parsing."""
        if self.command != "context":
            return None
        resolved_path = _optional_string(
            self.payload.get("resolved_path"),
            "graph context resolved_path",
        )
        raw_identity = self.payload.get("source_identity")
        if raw_identity is None:
            if resolved_path is not None:
                raise GraphClientError(
                    "graph context resolved_path lacks source_identity"
                )
            return None
        identity = _required_mapping(raw_identity, "graph context source_identity")
        expected_fields = {"snapshot_commit", "source_path", "content_sha256"}
        if set(identity) != expected_fields:
            raise GraphClientError(
                "graph context source_identity fields must be exactly "
                "snapshot_commit,source_path,content_sha256"
            )
        snapshot_commit = _required_string(
            identity,
            "snapshot_commit",
            "graph context source_identity",
        )
        source_path = _required_string(
            identity,
            "source_path",
            "graph context source_identity",
        )
        content_sha256 = _required_string(
            identity,
            "content_sha256",
            "graph context source_identity",
        )
        if resolved_path != source_path:
            raise GraphClientError(
                "graph context source_identity.source_path must equal resolved_path"
            )
        if len(content_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in content_sha256
        ):
            raise GraphClientError(
                "graph context source_identity.content_sha256 must be lowercase SHA-256"
            )
        return GraphSourceIdentity(snapshot_commit, source_path, content_sha256)

    @property
    def dependency_facts(self) -> tuple[GraphDependencyFact, ...]:
        """Project explicit dependency facts through the response node identity join."""
        if self.command != "query":
            return ()
        raw_nodes = _required_array(self.payload, "nodes", "graph response")
        raw_facts = _required_array(self.payload, "facts", "graph response")
        paths_by_id: dict[str, str] = {}
        for raw_node in raw_nodes:
            node = _required_mapping(raw_node, "graph node")
            node_id = _required_string(node, "id", "graph node")
            path = node.get("path")
            selector = node.get("selector")
            endpoint = path if isinstance(path, str) and path else selector
            if not isinstance(endpoint, str) or not endpoint:
                raise GraphClientError(
                    f"graph node {node_id} lacks a nonempty path or selector"
                )
            if node_id in paths_by_id:
                raise GraphClientError(f"duplicate graph node id: {node_id}")
            paths_by_id[node_id] = endpoint

        projected: list[GraphDependencyFact] = []
        for raw_fact in raw_facts:
            fact = _required_mapping(raw_fact, "graph fact")
            if fact.get("kind") != "dependency" or fact.get("inferred") is True:
                continue
            if fact.get("inferred") is not False:
                raise GraphClientError("explicit dependency fact inferred must be false")
            fact_id = _required_string(fact, "id", "graph fact")
            from_id = _required_string(fact, "from", f"graph fact {fact_id}")
            to_id = _required_string(fact, "to", f"graph fact {fact_id}")
            try:
                source = paths_by_id[from_id]
                target = paths_by_id[to_id]
            except KeyError as error:
                raise GraphClientError(
                    f"graph fact {fact_id} endpoint is absent from nodes: {error.args[0]}"
                ) from error
            detail = _required_mapping(
                fact.get("dependency_detail"),
                f"graph fact {fact_id}.dependency_detail",
            )
            source_path = _optional_string(
                fact.get("source_path"), f"graph fact {fact_id}.source_path"
            )
            source_span = _optional_mapping(
                fact.get("source_span"), f"graph fact {fact_id}.source_span"
            )
            projected.append(
                GraphDependencyFact(
                    id=fact_id,
                    direction=_required_string(detail, "direction", "dependency detail"),
                    kind=_required_string(detail, "kind", "dependency detail"),
                    source=source,
                    target=target,
                    reason=_required_string(detail, "reason", "dependency detail"),
                    producer=_required_string(fact, "producer", f"graph fact {fact_id}"),
                    source_path=source_path,
                    source_span=source_span,
                    evidence_ref=_required_string(
                        fact, "evidence_ref", f"graph fact {fact_id}"
                    ),
                    authority=_required_string(
                        fact, "authority", f"graph fact {fact_id}"
                    ),
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
    """Invoke only the four canonical graph commands with fixed argument sets."""

    def __init__(self, root: Path, executable: Path) -> None:
        """Bind the adapter to one parent root and one explicit canonical executable."""
        self.root = root.resolve()
        self.executable = executable.resolve()

    def invoke(self, command: str, arguments: Sequence[str]) -> GraphResponse:
        """Invoke one graph command and preserve its valid typed response state."""
        if command not in GRAPH_COMMANDS:
            raise GraphClientError(f"unsupported graph command: {command}")
        normalized_arguments = tuple(arguments)
        _validate_arguments(command, normalized_arguments)
        if not self.executable.is_file():
            raise GraphClientError(
                f"canonical graph executable is missing: {self.executable}"
            )
        argv = [
            self.executable.as_posix(),
            "graph",
            command,
            "--root",
            self.root.as_posix(),
            "--profile",
            "default",
            "--format",
            "json",
            *normalized_arguments,
        ]
        try:
            result = subprocess.run(
                argv,
                cwd=self.root,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as error:
            raise GraphClientError(f"graph {command} process launch failed: {error}") from error
        payload = _decode_json_object(result.stdout, command, result.stderr)
        schema = _required_string(payload, "schema", "graph response")
        expected_schema = f"agent-canon.graph.{command}.v1"
        if schema != expected_schema:
            raise GraphClientError(
                f"graph schema mismatch: expected {expected_schema}, observed {schema}"
            )
        response_command = _required_string(payload, "command", "graph response")
        if response_command != command:
            raise GraphClientError(
                f"graph command mismatch: expected {command}, observed {response_command}"
            )
        status = _required_string(payload, "status", "graph response")
        exit_code = _required_integer(payload, "exit_code", "graph response")
        if exit_code not in GRAPH_EXIT_CODES:
            raise GraphClientError(f"unsupported graph exit_code: {exit_code}")
        if result.returncode != exit_code:
            raise GraphClientError(
                f"graph {command} process/response exit mismatch: "
                f"{result.returncode}/{exit_code}"
            )
        response = GraphResponse(schema, response_command, status, payload, exit_code)
        if command == "context":
            _ = response.source_identity
        return response

    def build(self) -> GraphResponse:
        """Build the graph and return its typed operation response."""
        return self.invoke("build", ())

    def status(self) -> GraphResponse:
        """Return graph status without converting a valid nonfresh state to transport error."""
        return self.invoke("status", ())

    def query(
        self,
        path: str | None = None,
        all: bool = False,  # noqa: A002 - public field name is fixed by the design schema.
        relation: str = "all",
        direction: str = "both",
        depth: int = 1,
    ) -> GraphResponse:
        """Run one path query or one zero-depth all-facts relation scan."""
        if all == (path is not None):
            raise GraphClientError("query requires exactly one of path or all")
        if relation not in GRAPH_RELATIONS:
            raise GraphClientError(f"unsupported graph relation: {relation}")
        if direction not in GRAPH_DIRECTIONS:
            raise GraphClientError(f"unsupported graph direction: {direction}")
        if isinstance(depth, bool) or not 0 <= depth <= 64:
            raise GraphClientError("graph query depth must be an integer from 0 through 64")
        if all and depth != 0:
            raise GraphClientError("all-facts graph query requires depth=0")
        selector = ("--all",) if all else ("--path", cast(str, path))
        return self.invoke(
            "query",
            (
                *selector,
                "--relation",
                relation,
                "--direction",
                direction,
                "--depth",
                str(depth),
            ),
        )

    def context(self, claim_path: str, token: str | None = None) -> GraphResponse:
        """Return one graph-owned context expansion without interpreting its evidence."""
        arguments = ["--path", claim_path]
        if token is not None:
            arguments.extend(("--token", token))
        return self.invoke("context", arguments)


def _validate_arguments(command: str, arguments: Sequence[str]) -> None:
    if command in {"build", "status"}:
        if arguments:
            raise GraphClientError(f"graph {command} accepts no operation arguments")
        return
    value_flags = {"--path", "--token"} if command == "context" else {
        "--path",
        "--relation",
        "--direction",
        "--depth",
    }
    boolean_flags: set[str] = set() if command == "context" else {"--all"}
    seen: set[str] = set()
    index = 0
    while index < len(arguments):
        flag = arguments[index]
        if flag in seen:
            raise GraphClientError(f"duplicate graph {command} flag: {flag}")
        seen.add(flag)
        if flag in boolean_flags:
            index += 1
            continue
        if flag not in value_flags:
            raise GraphClientError(f"unsupported graph {command} flag: {flag}")
        if index + 1 >= len(arguments) or arguments[index + 1].startswith("--"):
            raise GraphClientError(f"graph {command} flag requires a value: {flag}")
        index += 2
    if command == "context":
        if "--path" not in seen:
            raise GraphClientError("graph context requires --path")
        return
    if ("--all" in seen) == ("--path" in seen):
        raise GraphClientError("graph query requires exactly one of --all or --path")
    required = {"--relation", "--direction", "--depth"}
    missing = sorted(required - seen)
    if missing:
        raise GraphClientError(f"graph query missing flags: {','.join(missing)}")


def _decode_json_object(stdout: str, command: str, stderr: str) -> dict[str, object]:
    try:
        value: object = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise GraphClientError(
            f"graph {command} returned invalid JSON: {stdout!r}; "
            f"stderr={stderr.strip()!r}"
        ) from error
    return dict(_required_mapping(value, f"graph {command} response"))


def _required_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise GraphClientError(f"{field} must be an object")
    return cast(dict[str, object], value)


def _optional_mapping(value: object, field: str) -> Mapping[str, object] | None:
    if value is None:
        return None
    return _required_mapping(value, field)


def _required_array(
    row: Mapping[str, object], field: str, owner: str
) -> Sequence[object]:
    value = row.get(field)
    if not isinstance(value, list):
        raise GraphClientError(f"{owner}.{field} must be an array")
    return cast(list[object], value)


def _required_string(row: Mapping[str, object], field: str, owner: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise GraphClientError(f"{owner}.{field} must be a nonempty string")
    return value


def _optional_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise GraphClientError(f"{field} must be a string or null")
    return value


def _required_integer(row: Mapping[str, object], field: str, owner: str) -> int:
    value = row.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise GraphClientError(f"{owner}.{field} must be an integer")
    return value
