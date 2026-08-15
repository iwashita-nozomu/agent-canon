#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Derives dependency graph query, review, and context projections directly from tracked source manifests.
# upstream design ../../documents/design/dependency-manifest-design.md dependency manifest DSL and path semantics
# upstream design ../../documents/design/source-owned-dependency-validation.md tracked source authority boundary
# upstream implementation ./surface_manifest.py resolves canonical parent projection bindings
# downstream implementation ./graph_client.py exposes source-derived dependency query and context compatibility
# downstream implementation ./check_dependency_graph.sh validates source-derived relations and writes review artifacts
# downstream implementation ../../tests/agent_tools/test_graph_client_source_projection.py validates no-runtime projections
# @dependency-end
"""Pure tracked-source dependency projection without persisted graph runtime state."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

try:
    from .surface_manifest import load_manifest, normalized_snapshot
except ImportError:  # pragma: no cover - direct CLI import
    from surface_manifest import load_manifest, normalized_snapshot

HEADER_SCAN_LINES = 80
MANIFEST_FIELD_COUNT = 4
MANIFEST_REASON_MAX_SPLIT = MANIFEST_FIELD_COUNT - 1
DEFAULT_CONTEXT_DEPTH = 3
DEPENDENCY_KINDS = frozenset({"design", "implementation", "environment"})
CONTEXT_KINDS = frozenset({"design", "implementation"})
TEXT_SUFFIXES = frozenset(
    {
        ".bash",
        ".c",
        ".cc",
        ".cfg",
        ".cpp",
        ".css",
        ".h",
        ".hpp",
        ".html",
        ".json",
        ".md",
        ".py",
        ".rs",
        ".rst",
        ".sh",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
        ".zsh",
    }
)
SKIPPED_PREFIXES = (
    ".agent-canon/log-archive/",
    ".git/",
    ".pytest_cache/",
    ".ruff_cache/",
    "reports/",
    "vendor/agent-canon/.agent-canon/log-archive/",
    "vendor/agent-canon/reports/",
)
RAW_NVIDIA_FIXTURE_PREFIX = "tests/fixtures/nvidia/"
SURFACE_MANIFEST = Path("documents/runtime/shared-runtime-surfaces.toml")


class SourceDependencyError(RuntimeError):
    """Tracked source could not be projected without violating manifest invariants."""


@dataclass(frozen=True, order=True)
class SourceDependencyEdge:
    """One normalized dependency declaration from tracked source."""

    source: str
    direction: str
    kind: str
    target: str
    reason: str
    line: int


@dataclass(frozen=True, order=True)
class SourceDependencyDocument:
    """One canonical source document and its dependency-manifest projection."""

    path: str
    manifest_present: bool
    edges: tuple[SourceDependencyEdge, ...]


@dataclass(frozen=True)
class SourceDependencyProjection:
    """Typed dependency query payload derived from current source bytes."""

    nodes: tuple[Mapping[str, object], ...]
    facts: tuple[Mapping[str, object], ...]
    fingerprint: str

    def payload(self) -> dict[str, object]:
        """Return a graph-query-compatible payload."""
        return {
            "nodes": list(self.nodes),
            "facts": list(self.facts),
            "graph_fingerprint": self.fingerprint,
            "projection": "tracked-source",
        }


@dataclass(frozen=True)
class SourceContextProjection:
    """Typed dependency context derived from current source bytes."""

    resolved_path: str
    snapshot_commit: str
    content_sha256: str
    evidence_paths: tuple[str, ...]
    parent_paths: tuple[str, ...]
    fingerprint: str

    def payload(self) -> dict[str, object]:
        """Return a graph-context-compatible payload."""
        return {
            "resolved_path": self.resolved_path,
            "source_identity": {
                "snapshot_commit": self.snapshot_commit,
                "source_path": self.resolved_path,
                "content_sha256": self.content_sha256,
            },
            "evidence_paths": list(self.evidence_paths),
            "parent_paths": list(self.parent_paths),
            "graph_fingerprint": self.fingerprint,
            "projection": "tracked-source",
        }


def strip_manifest_line(line: str) -> str:
    """Remove supported comment wrappers from one manifest line."""
    stripped = line.rstrip("\r").strip()
    for prefix in ("# ", "#", "// ", "//", "* ", "*"):
        if stripped.startswith(prefix):
            stripped = stripped.removeprefix(prefix).strip()
            break
    if stripped.endswith(","):
        stripped = stripped[:-1].strip()
    if len(stripped) >= 2 and stripped.startswith('"') and stripped.endswith('"'):
        stripped = stripped[1:-1].strip()
    return stripped


def repo_relative(root: Path, path: Path) -> str:
    """Return one normalized repository-relative path."""
    try:
        return path.resolve(strict=False).relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise SourceDependencyError(f"path escapes repository root: {path}") from error


def _git_files(root: Path) -> tuple[str, ...]:
    """Return tracked paths for one Git worktree, or an empty tuple."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ()
    return tuple(line for line in result.stdout.splitlines() if line)


def source_paths(root: Path) -> tuple[str, ...]:
    """Return deterministic tracked source paths, including a vendored canon checkout."""
    root = root.resolve()
    paths = set(_git_files(root))
    vendor_root = root / "vendor" / "agent-canon"
    if vendor_root.is_dir():
        paths.update(f"vendor/agent-canon/{path}" for path in _git_files(vendor_root))
    if not paths:
        paths.update(
            repo_relative(root, path)
            for path in root.rglob("*")
            if path.is_file() and not path.is_symlink()
        )
    return tuple(sorted(paths))


def is_text_source(path: str) -> bool:
    """Return whether a path can carry a dependency manifest."""
    normalized = path.replace("\\", "/").removeprefix("./")
    if any(normalized.startswith(prefix) for prefix in SKIPPED_PREFIXES):
        return False
    if normalized.startswith(RAW_NVIDIA_FIXTURE_PREFIX) and Path(normalized).suffix == ".txt":
        return False
    return Path(normalized).suffix.lower() in TEXT_SUFFIXES


def _surface_bindings(root: Path) -> tuple[tuple[str, str], ...]:
    """Return canonical source bindings for generated/copied parent views."""
    vendor_root = root / "vendor" / "agent-canon"
    manifest = vendor_root / SURFACE_MANIFEST
    if not manifest.is_file():
        return ()
    try:
        snapshot = normalized_snapshot(
            load_manifest(root, "vendor/agent-canon", SURFACE_MANIFEST.as_posix())
        )
    except (OSError, ValueError) as error:
        raise SourceDependencyError(f"surface manifest snapshot unavailable: {error}") from error
    prefix = snapshot.get("prefix")
    entries = snapshot.get("entries")
    if not isinstance(prefix, str) or not prefix or not isinstance(entries, list):
        raise SourceDependencyError("surface manifest normalized snapshot is malformed")
    projected = (root / prefix).is_dir() and (root / ".git").exists()
    bindings: list[tuple[str, str]] = []
    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            raise SourceDependencyError("surface manifest normalized entry is malformed")
        path = raw_entry.get("path")
        mode = raw_entry.get("mode")
        source = raw_entry.get("source")
        if not all(isinstance(value, str) for value in (path, mode, source)):
            raise SourceDependencyError(
                "surface manifest normalized entry has invalid binding fields"
            )
        if mode not in {"symlink", "copy"} or not source:
            continue
        target = (Path(prefix) / source).as_posix() if projected else source
        bindings.append((path, target))
    return tuple(sorted(bindings, key=lambda item: (-len(item[0]), item[0], item[1])))


def resolve_surface_binding(relative: str, bindings: Sequence[tuple[str, str]]) -> str:
    """Map one parent view to its canonical source by deterministic longest prefix."""
    for view, target in bindings:
        if relative == view or relative.startswith(f"{view}/"):
            return f"{target}{relative[len(view):]}"
    return relative


def resolve_source_path(
    root: Path,
    relative: str,
    bindings: Sequence[tuple[str, str]],
) -> tuple[str, Path]:
    """Return canonical relative and physical source paths."""
    normalized = relative.replace("\\", "/").removeprefix("./")
    canonical = resolve_surface_binding(normalized, bindings)
    candidate_path = root / canonical
    if not candidate_path.is_symlink():
        candidate = candidate_path.resolve(strict=False)
        repo_relative(root, candidate)
        if candidate.is_file():
            return canonical, candidate
    direct_path = root / normalized
    if direct_path.is_symlink():
        raise SourceDependencyError(f"source path is a symbolic link: {normalized}")
    direct = direct_path.resolve(strict=False)
    repo_relative(root, direct)
    if not direct.is_file():
        raise SourceDependencyError(f"source path is unavailable: {normalized}")
    return normalized, direct


def _read_text(path: Path, relative: str) -> str:
    """Read UTF-8 source text or reject non-text source bytes."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise SourceDependencyError(f"source text is unreadable: {relative}: {error}") from error


def _normalize_target(root: Path, source: Path, raw_target: str) -> str:
    """Resolve one relative dependency target and reject root escape."""
    if raw_target.startswith("/") or "://" in raw_target:
        raise SourceDependencyError(
            f"dependency path must be repository-relative: {raw_target}"
        )
    target = (source.parent / raw_target).resolve(strict=False)
    return repo_relative(root, target)


def parse_manifest_document(
    root: Path,
    relative: str,
    bindings: Sequence[tuple[str, str]],
) -> SourceDependencyDocument:
    """Parse one canonical source document with the strict dependency DSL."""
    canonical, source = resolve_source_path(root, relative, bindings)
    text = _read_text(source, canonical)
    in_manifest = False
    saw_start = False
    saw_end = False
    edges: list[SourceDependencyEdge] = []
    for line_number, raw_line in enumerate(text.splitlines()[:HEADER_SCAN_LINES], start=1):
        line = strip_manifest_line(raw_line)
        if line == "@dependency-start":
            if in_manifest or saw_start:
                raise SourceDependencyError(
                    f"{canonical}:{line_number}: duplicate @dependency-start"
                )
            in_manifest = True
            saw_start = True
            continue
        if line == "@dependency-end":
            if not in_manifest:
                raise SourceDependencyError(
                    f"{canonical}:{line_number}: @dependency-end without start"
                )
            in_manifest = False
            saw_end = True
            break
        if not in_manifest or not line:
            continue
        if line in {"<!--", "-->", "/*", "*/", '"""', "'''"}:
            continue
        if line.startswith(("contract ", "responsibility ", "coverage ")):
            continue
        fields = line.split(maxsplit=MANIFEST_REASON_MAX_SPLIT)
        if len(fields) != MANIFEST_FIELD_COUNT:
            raise SourceDependencyError(
                f"{canonical}:{line_number}: dependency line must be "
                "direction kind relative-path reason"
            )
        direction, kind, raw_target, reason = fields
        if direction not in {"upstream", "downstream"}:
            raise SourceDependencyError(
                f"{canonical}:{line_number}: invalid dependency direction: {direction}"
            )
        if kind not in DEPENDENCY_KINDS:
            raise SourceDependencyError(
                f"{canonical}:{line_number}: invalid dependency kind: {kind}"
            )
        if not reason:
            raise SourceDependencyError(
                f"{canonical}:{line_number}: dependency reason is empty"
            )
        edges.append(
            SourceDependencyEdge(
                source=canonical,
                direction=direction,
                kind=kind,
                target=_normalize_target(root, source, raw_target),
                reason=reason,
                line=line_number,
            )
        )
    if saw_start != saw_end:
        raise SourceDependencyError(f"{canonical}: incomplete dependency manifest markers")
    return SourceDependencyDocument(canonical, saw_start and saw_end, tuple(edges))


def parse_manifest_edges(
    root: Path,
    relative: str,
    bindings: Sequence[tuple[str, str]],
) -> tuple[SourceDependencyEdge, ...]:
    """Return the normalized dependency edges for one source document."""
    return parse_manifest_document(root, relative, bindings).edges


def dependency_documents(root: Path) -> tuple[SourceDependencyDocument, ...]:
    """Return every unique canonical text document and manifest projection."""
    root = root.resolve()
    bindings = _surface_bindings(root)
    documents: list[SourceDependencyDocument] = []
    canonical_sources: set[str] = set()
    for relative in source_paths(root):
        if not is_text_source(relative):
            continue
        canonical = resolve_surface_binding(relative, bindings)
        if canonical in canonical_sources:
            continue
        try:
            canonical_relative, source = resolve_source_path(root, relative, bindings)
        except SourceDependencyError:
            # Git links, deleted paths, and unavailable generated views are not text sources.
            continue
        if canonical_relative in canonical_sources or source.is_symlink():
            continue
        canonical_sources.add(canonical_relative)
        documents.append(parse_manifest_document(root, canonical_relative, ()))
    return tuple(sorted(documents))


def dependency_edges(root: Path) -> tuple[SourceDependencyEdge, ...]:
    """Return every unique source-declared dependency edge."""
    edges = {edge for document in dependency_documents(root) for edge in document.edges}
    return tuple(sorted(edges))


def dependency_manifest_paths(root: Path) -> tuple[str, ...]:
    """Return every canonical text source containing a complete manifest block."""
    return tuple(
        document.path for document in dependency_documents(root) if document.manifest_present
    )


def _stable_id(prefix: str, *values: object) -> str:
    """Return a deterministic identifier for one source projection record."""
    encoded = json.dumps(
        [prefix, *values],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()}"


def build_dependency_projection(root: Path) -> SourceDependencyProjection:
    """Build a graph-query-compatible projection from current source bytes."""
    edges = dependency_edges(root)
    paths = sorted({endpoint for edge in edges for endpoint in (edge.source, edge.target)})
    node_ids = {path: _stable_id("node", path) for path in paths}
    nodes = tuple({"id": node_ids[path], "path": path} for path in paths)
    facts: list[Mapping[str, object]] = []
    for edge in edges:
        fact_id = _stable_id(
            "dependency",
            edge.source,
            edge.direction,
            edge.kind,
            edge.target,
            edge.reason,
            edge.line,
        )
        facts.append(
            {
                "id": fact_id,
                "kind": "dependency",
                "inferred": False,
                "from": node_ids[edge.source],
                "to": node_ids[edge.target],
                "producer": "tracked-source-manifest",
                "source_path": edge.source,
                "source_span": {
                    "path": edge.source,
                    "start_line": edge.line,
                    "start_column": 1,
                    "end_line": edge.line,
                    "end_column": 1,
                },
                "evidence_ref": f"{edge.source}:{edge.line}",
                "authority": "tracked-source",
                "dependency_detail": {
                    "direction": edge.direction,
                    "kind": edge.kind,
                    "reason": edge.reason,
                },
            }
        )
    fingerprint = hashlib.sha256(
        json.dumps(
            facts,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return SourceDependencyProjection(nodes, tuple(facts), fingerprint)


def _snapshot_commit(root: Path) -> str:
    """Return the current source commit identity without requiring repository history."""
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    candidate = result.stdout.strip()
    return candidate if result.returncode == 0 and candidate else "working-tree"


def _dependency_indexes(
    edges: Sequence[SourceDependencyEdge],
) -> tuple[
    Mapping[str, tuple[SourceDependencyEdge, ...]],
    Mapping[str, tuple[SourceDependencyEdge, ...]],
]:
    outgoing: dict[str, list[SourceDependencyEdge]] = defaultdict(list)
    incoming: dict[str, list[SourceDependencyEdge]] = defaultdict(list)
    for edge in edges:
        outgoing[edge.source].append(edge)
        incoming[edge.target].append(edge)
    return (
        {path: tuple(sorted(values)) for path, values in outgoing.items()},
        {path: tuple(sorted(values)) for path, values in incoming.items()},
    )


def build_context_projection(
    root: Path,
    path: str,
    depth: int = DEFAULT_CONTEXT_DEPTH,
) -> SourceContextProjection:
    """Build deterministic design/implementation context directly from source manifests."""
    if depth < 0:
        raise SourceDependencyError("context depth must be non-negative")
    root = root.resolve()
    bindings = _surface_bindings(root)
    resolved_path, source = resolve_source_path(root, path, bindings)
    text = _read_text(source, resolved_path)
    edges = dependency_edges(root)
    outgoing, incoming = _dependency_indexes(edges)
    evidence: set[str] = {resolved_path}
    parents: set[str] = set()
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(resolved_path, 0)])
    while queue:
        current, current_depth = queue.popleft()
        if current in visited or current_depth > depth:
            continue
        visited.add(current)
        related = sorted((*outgoing.get(current, ()), *incoming.get(current, ())))
        for edge in related:
            if edge.kind not in CONTEXT_KINDS:
                continue
            next_path = edge.target if edge.source == current else edge.source
            if next_path == resolved_path:
                continue
            evidence.add(next_path)
            if (
                edge.source == resolved_path
                and edge.direction == "upstream"
                and edge.kind == "design"
            ):
                parents.add(next_path)
            if current_depth < depth:
                queue.append((next_path, current_depth + 1))
    projection = build_dependency_projection(root)
    return SourceContextProjection(
        resolved_path=resolved_path,
        snapshot_commit=_snapshot_commit(root),
        content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        evidence_paths=tuple(sorted(evidence)),
        parent_paths=tuple(sorted(parents)),
        fingerprint=projection.fingerprint,
    )


def write_review_projection(root: Path, edges_out: Path, manifests_out: Path) -> None:
    """Write deterministic review inputs into caller-owned scratch paths."""
    documents = dependency_documents(root)
    edges = sorted({edge for document in documents for edge in document.edges})
    manifests = sorted(
        document.path for document in documents if document.manifest_present
    )
    edge_lines = [
        "\t".join((edge.direction, edge.kind, edge.source, edge.target))
        for edge in edges
    ]
    edges_out.parent.mkdir(parents=True, exist_ok=True)
    manifests_out.parent.mkdir(parents=True, exist_ok=True)
    edges_out.write_text(
        "\n".join(edge_lines) + ("\n" if edge_lines else ""),
        encoding="utf-8",
    )
    manifests_out.write_text(
        "\n".join(manifests) + ("\n" if manifests else ""),
        encoding="utf-8",
    )


def build_cli_parser() -> argparse.ArgumentParser:
    """Create the source dependency projection CLI."""
    parser = argparse.ArgumentParser(
        description="Export source-derived dependency review inputs without graph runtime state."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--edges-out", required=True, type=Path)
    parser.add_argument("--manifests-out", required=True, type=Path)
    return parser


def main() -> int:
    """Export source-derived review inputs for shell validators."""
    args = build_cli_parser().parse_args()
    try:
        write_review_projection(
            args.root.resolve(),
            args.edges_out.resolve(strict=False),
            args.manifests_out.resolve(strict=False),
        )
    except SourceDependencyError as error:
        print(f"SOURCE_DEPENDENCY_EXPORT=fail reason={error}", file=sys.stderr)
        return 1
    print("SOURCE_DEPENDENCY_EXPORT=pass authority=tracked-source")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
