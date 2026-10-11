#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Runs a selected native SCIP indexer and projects bounded facts from its index.
# upstream design ../../../documents/design/dependency-manifest-design.md keeps code and header evidence separate.
# upstream implementation ../../runtime/artifacts/runtime_artifacts.py owns external artifact paths and hashes.
# downstream implementation ./git_dependency_diff_summary.py consumes selected impact projections.
# downstream design ../../../agents/skills/dependency-analysis.md selects optional index/query use.
# downstream implementation ../../../tests/agent_tools/test_scip_index.py verifies native index handling.
# @dependency-end
"""Run maintained native SCIP indexers and query their standard index artifacts."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.runtime.artifacts.runtime_artifacts import (
    RuntimeArtifactBoundary,
    RuntimeArtifactError,
    root_capability_environment,
    runtime_artifact_boundary,
)

DEFINITION_ROLE = 0x1
ROLE_NAMES = (
    (0x1, "definition"),
    (0x2, "import"),
    (0x4, "write-access"),
    (0x8, "read-access"),
    (0x10, "generated"),
    (0x20, "test"),
    (0x40, "forward-definition"),
)
DEFAULT_RESULT_LIMIT = 200
MAX_RESULT_LIMIT = 1000
IMAGE_RECEIPT_ROOT = Path("/usr/local/share/agent-canon/image-dependencies/receipts")
IMAGE_MANIFEST_ROOT = Path("/usr/local/share/agent-canon/runtime")
INDEXER_RECORDS = {
    "scip": ("scip-cli", "scip"),
    "python": ("scip-python", "scip-python"),
    "cpp": ("scip-clang", "scip-clang"),
}


class ScipIndexError(RuntimeError):
    """Base class for SCIP command and input failures."""


class ToolUnavailable(ScipIndexError):
    """A required executable is absent from the verified runtime image."""


class UnsupportedCapability(ScipIndexError):
    """The selected language lacks a maintained native SCIP producer."""


class RequiredProjectInput(ScipIndexError):
    """A supported producer lacks an input owned by the selected project."""


class NativeCommandFailed(ScipIndexError):
    """A native SCIP command returned a failure status."""


class IndexDataError(ScipIndexError):
    """An index or official JSON readback is malformed."""


@dataclass(frozen=True)
class VerifiedTool:
    """One executable resolved from the shared typed dependency manifest."""

    executable: Path
    record_id: str
    version: str
    verification_output: str


@dataclass(frozen=True)
class IndexDocument:
    """A source document and its SCIP occurrences, projected in memory only."""

    path: str
    language: str
    occurrences: tuple[Mapping[str, Any], ...]
    symbols: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class LoadedIndex:
    """One validated native index read through the official SCIP CLI."""

    path: Path
    digest: str
    project_root: Path
    tool_name: str
    tool_version: str
    text_encoding: str
    documents: tuple[IndexDocument, ...]
    external_symbols: tuple[Mapping[str, Any], ...]


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _manifest_and_receipts() -> tuple[Path, Path]:
    """Use the image manifest and receipt owner selected by the runtime."""
    repo_root = _repository_root()
    manifest_override = os.environ.get("AGENT_CANON_DEPENDENCY_MANIFEST", "").strip()
    if manifest_override:
        manifest = Path(manifest_override).expanduser().resolve()
    else:
        source_manifest = (
            repo_root / "bootstrap" / "container" / "image" / "dependencies.toml"
        )
        image_manifest = IMAGE_MANIFEST_ROOT / "dependencies.toml"
        manifest = source_manifest if source_manifest.is_file() else image_manifest
    if not manifest.is_file():
        raise ToolUnavailable(
            "shared tool dependency manifest is unavailable; start bootstrap.sh"
        )

    if IMAGE_RECEIPT_ROOT.is_dir():
        receipts = IMAGE_RECEIPT_ROOT
    else:
        configured = os.environ.get("AGENT_CANON_DEPENDENCY_RECEIPTS", "").strip()
        if not configured:
            raise ToolUnavailable(
                "shared tool dependency receipts are unavailable; start bootstrap.sh"
            )
        receipts = Path(configured).expanduser().resolve()
    return manifest, receipts


def resolve_verified_tool(language_or_tool: str) -> VerifiedTool:
    """Resolve one catalogued executable through its installed receipt."""
    selected = INDEXER_RECORDS.get(language_or_tool)
    if selected is None:
        raise ToolUnavailable(f"no maintained SCIP indexer for {language_or_tool}")
    record_id, executable = selected
    try:
        from tools.analysis.dependencies.dependency_plan import (
            DependencyError,
            resolve_verified_executable,
        )
    except ImportError as exc:  # pragma: no cover - direct isolated invocation.
        raise ToolUnavailable("typed dependency resolver is unavailable") from exc

    manifest, receipts = _manifest_and_receipts()
    try:
        verified = resolve_verified_executable(
            manifest.parent.parent.parent,
            receipts,
            record_id,
            executable,
            manifest=manifest,
        )
    except (DependencyError, OSError, ValueError) as exc:
        raise ToolUnavailable(
            f"verified executable resolution failed for {record_id}: {exc}"
        ) from exc
    return VerifiedTool(
        executable=Path(verified.absolute_path),
        record_id=record_id,
        version=verified.manifest_version,
        verification_output=verified.verification_output,
    )


def _regular_input(root: Path, value: Path, label: str) -> Path:
    """Resolve an explicitly selected project input file."""
    candidate = value if value.is_absolute() else root / value
    try:
        resolved = candidate.resolve(strict=True)
        if not resolved.is_file():
            raise ScipIndexError(f"{label} must be a regular file: {candidate}")
        return resolved
    except OSError as exc:
        raise ScipIndexError(f"unable to read {label}: {candidate}") from exc


def _output_path(
    source_root: Path,
    runtime_root: Path | None,
    output: Path,
) -> tuple[RuntimeArtifactBoundary, Path]:
    """Resolve a new index destination beneath the external runtime root."""
    boundary = runtime_artifact_boundary(source_root, runtime_root, create=True)
    destination = boundary.resolve(output)
    if destination.exists() or destination.is_symlink():
        raise ScipIndexError(f"index output already exists: {destination}")
    boundary.ensure_directory(destination.parent.relative_to(boundary.root))
    return boundary, destination


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run one native command and preserve its stdout, stderr, and exit status."""
    try:
        return subprocess.run(
            list(command),
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    except OSError as exc:
        raise ToolUnavailable(f"unable to execute {command[0]}: {exc}") from exc


def _require_success(
    result: subprocess.CompletedProcess[str],
    command: Sequence[str],
) -> None:
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise NativeCommandFailed(
            f"{Path(command[0]).name} exited {result.returncode}"
            + (f": {detail}" if detail else "")
        )


def _producer_command(
    *,
    root: Path,
    output: Path,
    language: str,
    project_name: str | None,
    project_version: str | None,
    python_environment: Path | None,
    compile_database: Path | None,
    supplementary_output: Path,
) -> tuple[VerifiedTool, list[str]]:
    """Build one exact native invocation from explicit project inputs."""
    tool = resolve_verified_tool(language)
    if language == "python":
        command = [
            str(tool.executable),
            "index",
            ".",
            f"--project-name={project_name}",
            f"--project-version={project_version}",
            f"--environment={python_environment}",
            f"--output={output}",
        ]
    elif language == "cpp":
        command = [
            str(tool.executable),
            f"--compdb-path={compile_database}",
            f"--index-output-path={output}",
            f"--supplementary-output-dir={supplementary_output}",
        ]
    else:
        raise UnsupportedCapability(f"no qualified native SCIP producer for {language}")
    return tool, command


def _inspect_index(
    *,
    root: Path,
    boundary: RuntimeArtifactBoundary,
    index_path: Path,
    env: dict[str, str],
) -> tuple[str, subprocess.CompletedProcess[str]]:
    """Read index statistics with the official SCIP CLI."""
    target = boundary.resolve(index_path)
    if target.is_symlink() or not target.is_file():
        raise ScipIndexError(f"SCIP index is not a regular runtime artifact: {target}")
    scip = resolve_verified_tool("scip")
    command = [str(scip.executable), "stats", "--from", str(target)]
    result = _run(command, cwd=root, env=env)
    _require_success(result, command)
    return scip.version, result


def index_project(args: argparse.Namespace) -> dict[str, Any]:
    """Write a native SCIP index to an explicit external runtime destination."""
    root = args.root.resolve()
    python_environment = args.python_environment
    compile_database = args.compile_database
    if args.language == "python":
        if (
            not args.project_name
            or not args.project_version
            or python_environment is None
        ):
            raise RequiredProjectInput(
                "Python indexing requires --project-name, --project-version, "
                "and --python-environment from the project environment owner"
            )
        python_environment = _regular_input(
            root, python_environment, "Python environment file"
        )
    elif args.language == "cpp":
        if compile_database is None:
            raise RequiredProjectInput(
                "C/C++ indexing requires --compile-database from the project build owner"
            )
        compile_database = _regular_input(root, compile_database, "compile database")
    boundary, destination = _output_path(root, args.runtime_root, args.output)
    env = root_capability_environment(
        source_root=root,
        runtime_root=boundary.root,
        target_root=root,
    )
    supplemental = destination.parent / "scip-clang-supplementary-output"
    if args.language == "cpp":
        boundary.ensure_directory(supplemental.relative_to(boundary.root))
    tool, command = _producer_command(
        root=root,
        output=destination,
        language=args.language,
        project_name=args.project_name,
        project_version=args.project_version,
        python_environment=python_environment,
        compile_database=compile_database,
        supplementary_output=supplemental,
    )
    produced = _run(command, cwd=root, env=env)
    _require_success(produced, command)
    scip_version, stats = _inspect_index(
        root=root, boundary=boundary, index_path=destination, env=env
    )
    artifact_path = destination.relative_to(boundary.root).as_posix()
    return {
        "status": "written",
        "language": args.language,
        "index": {
            "path": artifact_path,
            "sha256": boundary.digest(destination),
        },
        "indexer": {"id": tool.record_id, "version": tool.version},
        "scip": {"version": scip_version, "stats": stats.stdout.strip()},
        "capabilities": {
            args.language: "index-written",
            "source_freshness": "unverified",
        },
        "stdout": produced.stdout.strip(),
        "stderr": produced.stderr.strip(),
    }


def _index_project_root(value: object) -> Path:
    """Decode the standard SCIP project-root URI."""
    if not isinstance(value, str) or not value:
        raise IndexDataError("SCIP index is missing metadata.project_root")
    parsed = urlparse(value)
    if parsed.scheme == "file":
        if parsed.netloc or parsed.query or parsed.fragment:
            raise IndexDataError(f"unsupported SCIP project-root URI: {value}")
        path_text = unquote(parsed.path)
    elif parsed.scheme:
        raise IndexDataError(f"unsupported SCIP project-root URI: {value}")
    else:
        path_text = value
    path = Path(path_text)
    if not path.is_absolute():
        raise IndexDataError(f"SCIP project root is not absolute: {value}")
    return path.resolve(strict=False)


def _relative_source_path(value: object) -> str:
    """Validate a SCIP document path and return its canonical POSIX spelling."""
    if not isinstance(value, str) or not value:
        raise IndexDataError("SCIP document has no relative_path")
    if (
        value.startswith("/")
        or "\\" in value
        or "//" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise IndexDataError(f"SCIP document path is not canonical: {value}")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise IndexDataError(f"SCIP document path is not canonical: {value}")
    return path.as_posix()


def _mapping_sequence(value: object, label: str) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(
        not isinstance(item, Mapping) for item in value
    ):
        raise IndexDataError(f"SCIP {label} must be a list of objects")
    return tuple(value)


def _load_index(
    *,
    source_root: Path,
    boundary: RuntimeArtifactBoundary,
    index_path: Path,
    env: dict[str, str],
) -> LoadedIndex:
    """Load the official JSON inspection view without persisting a mirror."""
    target = boundary.resolve(index_path)
    if target.is_symlink() or not target.is_file():
        raise ScipIndexError(f"SCIP index is not a regular runtime artifact: {target}")
    tool = resolve_verified_tool("scip")
    command = [str(tool.executable), "print", "--json", str(target)]
    result = _run(command, cwd=source_root, env=env)
    _require_success(result, command)
    try:
        payload: object = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise IndexDataError(f"scip print --json returned invalid JSON: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise IndexDataError("SCIP JSON readback must be an object")
    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping):
        raise IndexDataError("SCIP index is missing metadata")
    tool_info = metadata.get("tool_info")
    if not isinstance(tool_info, Mapping):
        tool_info = {}
    raw_documents = _mapping_sequence(payload.get("documents"), "documents")
    documents: list[IndexDocument] = []
    for document in raw_documents:
        documents.append(
            IndexDocument(
                path=_relative_source_path(document.get("relative_path")),
                language=str(document.get("language", "")),
                occurrences=_mapping_sequence(
                    document.get("occurrences"), "occurrences"
                ),
                symbols=_mapping_sequence(document.get("symbols"), "symbols"),
            )
        )
    external_symbols = _mapping_sequence(
        payload.get("external_symbols"), "external_symbols"
    )
    return LoadedIndex(
        path=target,
        digest=boundary.digest(target),
        project_root=_index_project_root(metadata.get("project_root")),
        tool_name=str(tool_info.get("name", "")),
        tool_version=str(tool_info.get("version", "")),
        text_encoding=str(metadata.get("text_document_encoding", "")),
        documents=tuple(documents),
        external_symbols=external_symbols,
    )


def _range_value(value: object) -> dict[str, dict[str, int]] | None:
    """Normalize typed or legacy ranges from the official SCIP CLI JSON."""
    if isinstance(value, Mapping):
        typed_range = value.get("TypedRange")
        if not isinstance(typed_range, Mapping):
            typed_range = {}
        single = typed_range.get("single_line_range")
        if isinstance(single, Mapping):
            fields = (
                single.get("line"),
                single.get("start_character"),
                single.get("end_character"),
            )
            if all(
                isinstance(field, int) and not isinstance(field, bool)
                for field in fields
            ):
                line, start, end = fields
                return {
                    "start": {"line": line, "character": start},
                    "end": {"line": line, "character": end},
                }
        multi = typed_range.get("multi_line_range")
        if isinstance(multi, Mapping):
            fields = (
                multi.get("start_line"),
                multi.get("start_character"),
                multi.get("end_line"),
                multi.get("end_character"),
            )
            if all(
                isinstance(field, int) and not isinstance(field, bool)
                for field in fields
            ):
                start_line, start_character, end_line, end_character = fields
                return {
                    "start": {"line": start_line, "character": start_character},
                    "end": {"line": end_line, "character": end_character},
                }
    if isinstance(value, Mapping):
        value = value.get("range")
    if isinstance(value, list) and all(
        isinstance(field, int) and not isinstance(field, bool) for field in value
    ):
        if len(value) == 3:
            start_line, start_character, end_character = value
            end_line = start_line
        elif len(value) == 4:
            start_line, start_character, end_line, end_character = value
        else:
            return None
        return {
            "start": {"line": start_line, "character": start_character},
            "end": {"line": end_line, "character": end_character},
        }
    return None


def _occurrence_rows(index: LoadedIndex, source_root: Path) -> list[dict[str, Any]]:
    """Project occurrence facts to root-relative paths and source ranges."""
    try:
        prefix_path = index.project_root.relative_to(source_root)
    except ValueError as exc:
        raise IndexDataError(
            f"SCIP project root is outside requested root: {index.project_root}"
        ) from exc
    prefix = "" if prefix_path == Path(".") else prefix_path.as_posix()
    rows: list[dict[str, Any]] = []
    for document in index.documents:
        relative_path = f"{prefix}/{document.path}" if prefix else document.path
        for occurrence in document.occurrences:
            symbol = occurrence.get("symbol")
            if not isinstance(symbol, str) or not symbol:
                continue
            roles_value = occurrence.get("symbol_roles", 0)
            if (
                not isinstance(roles_value, int)
                or isinstance(roles_value, bool)
                or roles_value < 0
            ):
                raise IndexDataError(
                    f"invalid symbol_roles for {relative_path}: {roles_value!r}"
                )
            rows.append(
                {
                    "path": relative_path,
                    "range": _range_value(occurrence),
                    "symbol": symbol,
                    "symbol_roles": roles_value,
                    "roles": [name for bit, name in ROLE_NAMES if roles_value & bit],
                    "language": document.language,
                    "text_encoding": index.text_encoding,
                }
            )
    return rows


def _path_selection(path: str) -> str:
    """Validate a requested target path without requiring it to exist."""
    if path == ".":
        return "."
    if not path or path.startswith("/") or "\\" in path or "//" in path:
        raise ScipIndexError(f"target path must be root-relative and canonical: {path}")
    if any(part in {".", ".."} for part in path.split("/")):
        raise ScipIndexError(f"target path must be root-relative and canonical: {path}")
    pure = PurePosixPath(path)
    if pure.is_absolute():
        raise ScipIndexError(f"target path must be root-relative: {path}")
    normalized = pure.as_posix()
    if normalized.startswith("./") or "//" in normalized:
        raise ScipIndexError(f"target path must be canonical: {path}")
    return normalized.rstrip("/")


def _matches_target(document_path: str, target: str) -> bool:
    return (
        target == "."
        or document_path == target
        or document_path.startswith(target + "/")
    )


def _definition(occurrence: Mapping[str, Any]) -> bool:
    return bool(int(occurrence.get("symbol_roles", 0)) & DEFINITION_ROLE)


def _implementation_targets(
    indexes: Sequence[LoadedIndex],
) -> dict[str, set[str]]:
    """Read only native SCIP implementation relationships."""
    implementations: dict[str, set[str]] = {}
    for index in indexes:
        symbol_records = [*index.external_symbols]
        for document in index.documents:
            symbol_records.extend(document.symbols)
        for information in symbol_records:
            source_symbol = information.get("symbol")
            relationships = _mapping_sequence(
                information.get("relationships"), "relationships"
            )
            if not isinstance(source_symbol, str) or not source_symbol:
                continue
            for relationship in relationships:
                target_symbol = relationship.get("symbol")
                is_implementation = relationship.get("is_implementation", False)
                if (
                    isinstance(target_symbol, str)
                    and target_symbol
                    and is_implementation is True
                ):
                    implementations.setdefault(target_symbol, set()).add(source_symbol)
    return implementations


def query_indexes(args: argparse.Namespace) -> dict[str, Any]:
    """Project definitions, references, and declared implementation relations."""
    source_root = args.root.resolve()
    boundary = runtime_artifact_boundary(source_root, args.runtime_root, create=False)
    env = root_capability_environment(
        source_root=source_root,
        runtime_root=boundary.root,
        target_root=source_root,
    )
    indexes = tuple(
        _load_index(
            source_root=source_root,
            boundary=boundary,
            index_path=index_path,
            env=env,
        )
        for index_path in args.index
    )
    targets = tuple(_path_selection(value) for value in args.path)
    requested_symbols = set(args.symbol)
    all_occurrences: list[dict[str, Any]] = []
    target_documents: set[str] = set()
    index_refs: list[dict[str, str]] = []
    for index in indexes:
        prefix_path = index.project_root.relative_to(source_root)
        prefix = "" if prefix_path == Path(".") else prefix_path.as_posix()
        for document in index.documents:
            document_path = f"{prefix}/{document.path}" if prefix else document.path
            if any(_matches_target(document_path, target) for target in targets):
                target_documents.add(document_path)
        all_occurrences.extend(_occurrence_rows(index, source_root))
        index_refs.append(
            {
                "path": index.path.relative_to(boundary.root).as_posix(),
                "sha256": index.digest,
                "tool": index.tool_name,
                "version": index.tool_version,
                "project_root": index.project_root.relative_to(source_root).as_posix(),
                "text_encoding": index.text_encoding,
            }
        )

    selected_symbols = set(requested_symbols)
    if targets:
        selected_symbols.update(
            occurrence["symbol"]
            for occurrence in all_occurrences
            if occurrence["path"] in target_documents
        )
    if not targets and not requested_symbols:
        raise ScipIndexError("query requires at least one --path or --symbol")

    definitions = [
        occurrence
        for occurrence in all_occurrences
        if occurrence["symbol"] in selected_symbols and _definition(occurrence)
    ]
    references = [
        occurrence
        for occurrence in all_occurrences
        if occurrence["symbol"] in selected_symbols and not _definition(occurrence)
    ]
    implementations_by_target = _implementation_targets(indexes)
    implementation_symbols = {
        symbol
        for target in selected_symbols
        for symbol in implementations_by_target.get(target, set())
    }
    implementations = [
        occurrence
        for occurrence in all_occurrences
        if occurrence["symbol"] in implementation_symbols and _definition(occurrence)
    ]

    unindexed_targets = [
        target
        for target in targets
        if not any(_matches_target(path, target) for path in target_documents)
    ]
    directory_targets = {
        target
        for target in targets
        if target == "." or (source_root / Path(*PurePosixPath(target).parts)).is_dir()
    }
    if targets and not target_documents:
        status = "unindexed-target"
    elif unindexed_targets:
        status = "partial-target"
    elif requested_symbols and not definitions and not references:
        status = "symbol-not-indexed"
    elif not selected_symbols:
        status = "no-indexed-symbols"
    else:
        status = "projected"

    limit = min(args.limit, MAX_RESULT_LIMIT)
    requested_symbol_list = sorted(requested_symbols)
    selected_symbol_list = sorted(selected_symbols)
    result = {
        "status": status,
        "requested_target": {
            "paths": list(targets[:limit]),
            "symbols": requested_symbol_list[:limit],
        },
        "symbols": selected_symbol_list[:limit],
        "unindexed_targets": unindexed_targets[:limit],
        "index_refs": index_refs[:limit],
        "definitions": definitions[:limit],
        "references": references[:limit],
        "implementations": implementations[:limit],
        "counts": {
            "definitions": len(definitions),
            "references": len(references),
            "implementations": len(implementations),
        },
        "truncated": any(
            len(values) > limit for values in (definitions, references, implementations)
        )
        or any(
            len(values) > limit
            for values in (
                targets,
                requested_symbol_list,
                selected_symbol_list,
                unindexed_targets,
                index_refs,
            )
        ),
        "capabilities": {
            "scip": "available",
            "references": (
                "projected"
                if any(
                    occurrence["symbol"] in selected_symbols
                    for occurrence in all_occurrences
                )
                else "unverified"
            ),
            "target_paths": (
                "not-selected"
                if not targets
                else (
                    "partial" if unindexed_targets or directory_targets else "indexed"
                )
            ),
            "source_freshness": "unverified",
            "implementations": (
                "declared"
                if any(
                    implementations_by_target.get(symbol) for symbol in selected_symbols
                )
                else "not-represented"
            ),
            "callers": "not-represented",
            "callees": "not-represented",
        },
    }
    return result


def _index_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser("index", help="write a native index.scip artifact")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--language", required=True)
    parser.add_argument("--project-name")
    parser.add_argument("--project-version")
    parser.add_argument("--python-environment", type=Path)
    parser.add_argument("--compile-database", type=Path)


def _query_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "query", help="project bounded facts from index.scip"
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--index", type=Path, action="append", required=True)
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_RESULT_LIMIT,
        help=f"Maximum entries per projected result list (1-{MAX_RESULT_LIMIT}).",
    )


def build_parser() -> argparse.ArgumentParser:
    """Create the single native index/query command surface."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    _index_parser(subparsers)
    _query_parser(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run exactly one selected native index or bounded query operation."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "index":
            if args.language not in INDEXER_RECORDS or args.language == "scip":
                print(
                    json.dumps(
                        {
                            "status": "unsupported",
                            "language": args.language,
                            "capabilities": {args.language: "unsupported"},
                        },
                        sort_keys=True,
                    )
                )
                return 0
            payload = index_project(args)
        else:
            if args.limit < 1:
                raise ScipIndexError("--limit must be positive")
            if args.limit > MAX_RESULT_LIMIT:
                raise ScipIndexError(f"--limit must not exceed {MAX_RESULT_LIMIT}")
            payload = query_indexes(args)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    except UnsupportedCapability as exc:
        print(
            json.dumps(
                {
                    "status": "unsupported",
                    "language": args.language,
                    "reason": str(exc),
                    "capabilities": {args.language: "unsupported"},
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except RequiredProjectInput as exc:
        print(
            json.dumps(
                {
                    "status": "input-required",
                    "language": args.language,
                    "reason": str(exc),
                    "capabilities": {args.language: "input-required"},
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (ScipIndexError, RuntimeArtifactError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "failed", "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
