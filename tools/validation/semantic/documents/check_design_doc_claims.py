#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Checks design-document claims against implementation-backed evidence.
# upstream design ../../../../documents/design/dependency-manifest-design.md dependency manifest graph semantics
# upstream design ../../../../documents/design/README.md design-document evidence policy
# downstream design ../../../../documents/tools/check_design_doc_claims.md tool contract
# downstream implementation ../../../../tests/agent_tools/test_check_design_doc_claims.py validates checker behavior
# @dependency-end
"""Check design-document claims against dependency and implementation evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from itertools import groupby
from pathlib import Path

HEADER_SCAN_LINES = 80
MANIFEST_FIELD_COUNT = 4
MANIFEST_REASON_MAX_SPLIT = MANIFEST_FIELD_COUNT - 1
DEFAULT_RECURSIVE_DEPTH = 0
TEXT_SUFFIXES = {
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
SKIPPED_PREFIXES = (
    ".agent-canon/log-archive/",
    "reports/",
    "vendor/agent-canon/.agent-canon/log-archive/",
    "vendor/agent-canon/reports/",
)
CLAIM_CUE_RE = re.compile(
    r"\b(must|should|shall|will|requires?|ensures?|provides?|validates?|"
    r"uses?|reads?|writes?|emits?|runs?|routes?|maps?|owns?)\b"
    r"|必須|責務|契約|検証|確認|使う|接続|比較|生成|出力|入力|読む|書く",
    re.IGNORECASE,
)
POSITIVE_CUE_RE = re.compile(
    r"\b(must|shall|requires?|uses?|validates?|runs?|routes?|maps?|owns?)\b"
    r"|必須|使う|使用|実行|接続|検証",
    re.IGNORECASE,
)
NEGATIVE_CUE_RE = re.compile(
    r"\b(must\s+not|shall\s+not|does\s+not|do\s+not|never|forbid(?:s|den)?|without)\b"
    r"|禁止|使わない|使用しない|不要|しない",
    re.IGNORECASE,
)
HEADING_RE = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$")
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\((?P<target>[^)]+)\)")
DIFF_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")


@dataclass(frozen=True)
class ManifestEdge:
    """One dependency manifest edge."""

    direction: str
    kind: str
    source: str
    target: str
    reason: str


@dataclass(frozen=True)
class Claim:
    """One checkable design claim line."""

    path: str
    line: int
    text: str
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class ClaimEvidenceRecord:
    """One typed design claim-evidence record."""

    record_version: int
    claim_id: str
    claim_text_sha256: str
    evidence_class: str
    input_identity: str
    owner_id: str
    evidence_ids: tuple[str, ...]
    request_clause_ids: tuple[str, ...]
    target_state_contract_sha256: str | None
    final_readback_action_id: str | None
    status: str


@dataclass(frozen=True)
class Finding:
    """One design evidence finding."""

    kind: str
    path: str
    line: int
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding line."""
        return (
            "DESIGN_DOC_CLAIM_FINDING="
            f"{self.kind}:{self.path}:{self.line}:{self.detail}"
        )


@dataclass(frozen=True)
class CheckResult:
    """Result for one checked design document."""

    path: str
    claims: int
    supported_claims: int
    evidence_paths: tuple[str, ...]
    parent_paths: tuple[str, ...]
    claim_evidence_records: tuple[ClaimEvidenceRecord, ...]
    findings: tuple[Finding, ...]


@dataclass
class ClosureAccumulator:
    """Mutable traversal state for dependency closure."""

    evidence: set[str]
    parents: set[str]
    queue: deque[tuple[str, int]]


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--recursive-depth",
        type=int,
        default=DEFAULT_RECURSIVE_DEPTH,
        help="Dependency-header expansion depth for evidence paths.",
    )
    parser.add_argument(
        "--changed",
        action="store_true",
        help="Check changed Markdown files under documents/design or templates/agents.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("paths", nargs="*", type=Path)
    return parser


def strip_manifest_line(line: str) -> str:
    """Strip common comment syntax from one manifest line."""
    stripped = line.rstrip("\r").strip()
    for prefix in ("#", "//", "*"):
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix) :].strip()
    stripped = stripped.rstrip(",").strip()
    if stripped.startswith('"') and stripped.endswith('"'):
        stripped = stripped[1:-1]
    return stripped.strip()


def repo_relative(root: Path, path: Path) -> str:
    """Return a normalized path relative to root when possible."""
    absolute_root = Path(os.path.normpath(root.absolute().as_posix()))
    absolute_path = (
        Path(os.path.normpath((root / path).absolute().as_posix()))
        if not path.is_absolute()
        else Path(os.path.normpath(path.absolute().as_posix()))
    )
    try:
        return absolute_path.relative_to(absolute_root).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_repo_path(root: Path, path: str | Path) -> Path:
    """Resolve root-relative, vendored, or absolute paths."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    direct = root / candidate
    if direct.exists():
        return direct
    vendor = root / "vendor" / "agent-canon" / candidate
    if vendor.exists():
        return vendor
    return direct


def resolve_claim_token_path(root: Path, claim_path: str, token_path: str) -> Path:
    """Resolve one path-like claim token from its claim document."""
    candidate = Path(token_path)
    if candidate.is_absolute():
        return candidate
    if token_path.startswith(("./", "../")):
        claim_file = resolve_repo_path(root, claim_path)
        return Path(os.path.normpath((claim_file.parent / candidate).as_posix()))
    return resolve_repo_path(root, candidate)


def path_is_under_root(root: Path, path: Path) -> bool:
    """Return whether one path stays inside the repository root."""
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def normalize_target(root: Path, source: Path, relative_target: str) -> str:
    """Normalize one manifest target relative to its source file."""
    target = source.parent / relative_target
    return repo_relative(root, target)


def parse_manifest_edges(root: Path, relative_path: str) -> tuple[ManifestEdge, ...]:
    """Extract dependency manifest edges from one file."""
    path = resolve_repo_path(root, relative_path)
    if not path.is_file() or path.is_symlink():
        return ()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[:HEADER_SCAN_LINES]
    except UnicodeDecodeError:
        return ()
    in_manifest = False
    source = repo_relative(root, path)
    edges: list[ManifestEdge] = []
    for line in lines:
        stripped = strip_manifest_line(line)
        if stripped == "@dependency-start":
            in_manifest = True
            continue
        if stripped == "@dependency-end":
            break
        if not in_manifest or not stripped:
            continue
        if stripped in {"<!--", "-->", "/*", "*/", '"""', "'''"}:
            continue
        fields = stripped.split(maxsplit=MANIFEST_REASON_MAX_SPLIT)
        if len(fields) < MANIFEST_FIELD_COUNT:
            continue
        direction, kind, target_path, reason = fields
        if direction not in {"upstream", "downstream"}:
            continue
        edges.append(
            ManifestEdge(
                direction=direction,
                kind=kind,
                source=source,
                target=normalize_target(root, path, target_path),
                reason=reason,
            )
        )
    return tuple(edges)


def git_files(root: Path) -> list[str]:
    """Return tracked files, including AgentCanon submodule files in parent repos."""
    files: list[str] = []
    files.extend(run_git_files(root, prefix=""))
    vendor_root = root / "vendor" / "agent-canon"
    if vendor_root.is_dir():
        files.extend(
            f"vendor/agent-canon/{path}"
            for path in run_git_files(vendor_root, prefix="")
        )
    return sorted(set(files))


def run_git_files(root: Path, prefix: str) -> list[str]:
    """Return git-tracked file paths for one root."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [
        f"{prefix}{line.strip()}" for line in result.stdout.splitlines() if line.strip()
    ]


def walk_files(root: Path) -> list[str]:
    """Return a fallback file list for non-git fixtures."""
    return sorted(
        repo_relative(root, path)
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    )


def is_checkable_path(path: str) -> bool:
    """Return whether a file path is a checkable source text path."""
    normalized = path.replace("\\", "/")
    if any(normalized.startswith(prefix) for prefix in SKIPPED_PREFIXES):
        return False
    return Path(normalized).suffix in TEXT_SUFFIXES


def all_manifest_edges(root: Path) -> tuple[ManifestEdge, ...]:
    """Extract manifest edges from all checkable files under root."""
    files = git_files(root) or walk_files(root)
    edges: list[ManifestEdge] = []
    for path in files:
        if is_checkable_path(path):
            edges.extend(parse_manifest_edges(root, path))
    return tuple(
        sorted(
            set(edges),
            key=lambda item: (item.source, item.direction, item.kind, item.target),
        )
    )


def changed_design_paths(root: Path) -> tuple[str, ...]:
    """Return changed active designs with added implementation claims.

    A changed design scope is intentionally narrower than ``git diff``.  A
    dependency-header repair, a retired redirect, a historical/evidence table,
    or a deleted row cannot change the implementation contract and therefore
    must not trigger claim enforcement.  The caller still checks the complete
    dependency closure for each selected active design.
    """
    return tuple(
        path
        for path in design_paths_from_candidates(run_git_changed_path_names(root))
        if has_changed_implementation_claim(root, path)
    )


def _without_dependency_manifest(text: str) -> str:
    """Remove the dependency header so header-only repairs do not trigger claim review."""
    start = text.find("@dependency-start")
    end = text.find("@dependency-end")
    if start < 0 or end < start:
        return text
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line_end = len(text) if line_end < 0 else line_end + 1
    return text[:line_start] + text[line_end:]


def has_non_manifest_change(root: Path, path: str) -> bool:
    """Return true for new docs or changes beyond the dependency header."""
    current_path = root / path
    if not current_path.is_file():
        return False
    baseline = subprocess.run(
        ["git", "-C", str(root), "show", f"HEAD:{path}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if baseline.returncode != 0:
        return True
    return _without_dependency_manifest(
        current_path.read_text(encoding="utf-8")
    ) != _without_dependency_manifest(baseline.stdout)


def _added_diff_lines(root: Path, path: str) -> tuple[tuple[int, str], ...]:
    """Return added lines and their current-file line numbers for one path."""
    result = subprocess.run(
        ["git", "-C", str(root), "diff", "--unified=0", "HEAD", "--", path],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ()
    current_line = 0
    added: list[tuple[int, str]] = []
    for raw_line in result.stdout.splitlines():
        match = DIFF_HUNK_RE.match(raw_line)
        if match:
            current_line = int(match.group("start"))
            continue
        if raw_line.startswith("+++"):
            continue
        if raw_line.startswith("+"):
            added.append((current_line, raw_line[1:]))
            current_line += 1
        elif raw_line.startswith("-"):
            continue
        elif raw_line.startswith("\\"):
            continue
        elif current_line:
            current_line += 1
    return tuple(added)


def is_retired_or_historical_design(text: str) -> bool:
    """Return whether a design is an explicitly non-current redirect/archive."""
    header = "\n".join(text.splitlines()[:HEADER_SCAN_LINES])
    if re.search(r"(?im)^\s*#\s*(?:retired|historical)\b", header):
        return True
    if re.search(r"(?im)^\s*responsibility\s+retired\b", header):
        return True
    return bool(
        re.search(
            r"(?i)\b(?:former|historical)\s+[^\n]{0,100}\b(?:design|policy|contract)\b[^\n]{0,100}\bretired\b",
            header,
        )
    )


def changed_implementation_claims(root: Path, path: str) -> tuple[Claim, ...]:
    """Return implementation-backed claims added to an active design.

    Markdown tables are intentionally excluded: their fixed evidence IDs and
    generated labels are an evidence record, not executable implementation
    claims.  Only an added line with both a claim cue and a concrete token is
    eligible; continuation prose and deleted/unchanged claims remain outside
    changed enforcement.
    """
    current_path = resolve_existing_text_path(root, path)
    if current_path is None:
        return ()
    text = current_path.read_text(encoding="utf-8")
    if is_retired_or_historical_design(text):
        return ()
    # The ledger is the explicit marker that a document is a current,
    # implementation-backed design.  Reference, migration, and historical
    # documents without it remain readable but are not changed-claim gates.
    if not has_evidence_ledger(text):
        return ()
    body_lines = dict(iter_body_lines(text))
    claims: list[Claim] = []
    for line_number, raw_line in _added_diff_lines(root, path):
        if line_number not in body_lines:
            continue
        stripped = raw_line.strip()
        if stripped.startswith("#") or stripped.startswith("|"):
            continue
        if is_non_claim_control_line(stripped):
            continue
        tokens = checkable_tokens(stripped)
        if not tokens or not CLAIM_CUE_RE.search(stripped):
            continue
        claims.append(Claim(path, line_number, stripped, tokens))
    return tuple(claims)


def has_changed_implementation_claim(root: Path, path: str) -> bool:
    """Return whether one changed design has an active implementation claim."""
    return bool(changed_implementation_claims(root, path))


def run_git_changed_path_names(root: Path) -> tuple[str, ...]:
    """Return git changed path names from the current checkout."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "diff",
            "--name-only",
            "--diff-filter=ACMRT",
            "HEAD",
            "--",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ()
    return tuple(result.stdout.splitlines())


def design_paths_from_candidates(paths: Iterable[str]) -> tuple[str, ...]:
    """Return design-document paths from candidate path names."""
    return tuple(path for path in paths if is_design_doc_path(path))


def is_design_doc_path(path: str) -> bool:
    """Return whether a path is a design-document candidate."""
    normalized = path.replace("\\", "/")
    if normalized.endswith("documents/design/README.md"):
        return False
    return normalized.endswith(".md") and (
        normalized.startswith("documents/design/")
        or normalized.startswith("vendor/agent-canon/documents/design/")
        or normalized == "templates/agents/design_brief.md"
        or normalized == "vendor/agent-canon/templates/agents/design_brief.md"
    )


def dependency_indexes(
    edges: Sequence[ManifestEdge],
) -> tuple[dict[str, list[ManifestEdge]], dict[str, list[ManifestEdge]]]:
    """Return outgoing and incoming manifest-edge indexes."""
    return edge_index_by_source(edges), edge_index_by_target(edges)


def edge_index_by_source(
    edges: Sequence[ManifestEdge],
) -> dict[str, list[ManifestEdge]]:
    """Return manifest edges grouped by source path."""
    return {
        source: list(group)
        for source, group in groupby(
            sorted(edges, key=lambda edge: edge.source),
            key=lambda edge: edge.source,
        )
    }


def edge_index_by_target(
    edges: Sequence[ManifestEdge],
) -> dict[str, list[ManifestEdge]]:
    """Return manifest edges grouped by target path."""
    return {
        target: list(group)
        for target, group in groupby(
            sorted(edges, key=lambda edge: edge.target),
            key=lambda edge: edge.target,
        )
    }


def dependency_closure(
    target: str,
    edges: Sequence[ManifestEdge],
    recursive_depth: int,
) -> tuple[set[str], set[str], list[Finding]]:
    """Return evidence paths, parent paths, and dependency traversal findings."""
    outgoing, incoming = dependency_indexes(edges)
    findings: list[Finding] = []
    accumulator = ClosureAccumulator(set(), set(), deque([(target, 0)]))
    visited: set[str] = set()
    while accumulator.queue:
        current, depth = accumulator.queue.popleft()
        if closure_node_visited_or_too_deep(current, depth, recursive_depth, visited):
            continue
        visited.add(current)
        for edge in related_dependency_edges(outgoing, incoming, current):
            record_dependency_closure_edge(
                target, current, depth, recursive_depth, edge, accumulator
            )
    return accumulator.evidence, accumulator.parents, findings


def closure_node_visited_or_too_deep(
    current: str,
    depth: int,
    recursive_depth: int,
    visited: set[str],
) -> bool:
    """Return whether one closure node should be skipped."""
    return current in visited or depth > recursive_depth


def related_dependency_edges(
    outgoing: dict[str, list[ManifestEdge]],
    incoming: dict[str, list[ManifestEdge]],
    current: str,
) -> tuple[ManifestEdge, ...]:
    """Return deterministic manifest edges touching one path."""
    return tuple(
        sorted(
            [*outgoing.get(current, ()), *incoming.get(current, ())],
            key=lambda edge: (edge.source, edge.direction, edge.kind, edge.target),
        )
    )


def record_dependency_closure_edge(
    target: str,
    current: str,
    depth: int,
    recursive_depth: int,
    edge: ManifestEdge,
    accumulator: ClosureAccumulator,
) -> None:
    """Record one traversable dependency edge in closure state."""
    next_path = dependency_next_path(edge, current)
    if not dependency_edge_is_traversable(edge, next_path, target):
        return
    accumulator.evidence.add(next_path)
    if dependency_edge_is_parent(target, edge):
        accumulator.parents.add(next_path)
    if depth < recursive_depth:
        accumulator.queue.append((next_path, depth + 1))


def dependency_next_path(edge: ManifestEdge, current: str) -> str:
    """Return the opposite endpoint from the current path."""
    if edge.source == current:
        return edge.target
    return edge.source


def dependency_edge_is_traversable(
    edge: ManifestEdge, next_path: str, target: str
) -> bool:
    """Return whether one dependency edge participates in claim evidence closure."""
    return (
        edge.kind in {"design", "implementation"}
        and is_checkable_path(next_path)
        and next_path != target
    )


def dependency_edge_is_parent(target: str, edge: ManifestEdge) -> bool:
    """Return whether one edge identifies an upstream parent design document."""
    return (
        edge.source == target and edge.direction == "upstream" and edge.kind == "design"
    )


def read_text(root: Path, relative_path: str) -> str:
    """Read a text file if possible."""
    path = resolve_repo_path(root, relative_path)
    if not path.is_file() or path.is_symlink():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def resolve_existing_text_path(root: Path, relative_path: str) -> Path | None:
    """Return a resolved text path when it exists and is UTF-8 readable."""
    path = resolve_repo_path(root, relative_path)
    if not path.is_file() or path.is_symlink():
        return None
    try:
        path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    return path


def evidence_texts(root: Path, paths: Iterable[str]) -> dict[str, str]:
    """Return readable evidence texts."""
    return {path: text for path in sorted(paths) if (text := read_text(root, path))}


def iter_body_lines(text: str) -> Iterable[tuple[int, str]]:
    """Yield non-fenced Markdown body lines."""
    in_fence = False
    in_manifest = False
    for index, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        manifest_line = strip_manifest_line(stripped)
        if manifest_line == "@dependency-start":
            in_manifest = True
            continue
        if in_manifest:
            if manifest_line == "@dependency-end":
                in_manifest = False
            continue
        if not stripped or stripped.startswith("<!--") or stripped.startswith("-->"):
            continue
        if stripped.startswith("|") and set(stripped.replace("|", "").strip()) <= {
            "-",
            ":",
        }:
            continue
        yield index, raw_line.rstrip()


def section_text(text: str, section_keywords: Sequence[str]) -> str:
    """Return text under the first heading containing one keyword."""
    lines = text.splitlines()
    start: int | None = None
    level = 0
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line.strip())
        if not match:
            continue
        title = match.group("title").lower()
        if any(keyword.lower() in title for keyword in section_keywords):
            start = index + 1
            level = len(line) - len(line.lstrip("#"))
            break
    if start is None:
        return ""
    collected: list[str] = []
    for line in lines[start:]:
        match = HEADING_RE.match(line.strip())
        if match and len(line) - len(line.lstrip("#")) <= level:
            break
        collected.append(line)
    return "\n".join(collected)


def checkable_tokens(line: str) -> tuple[str, ...]:
    """Return local Markdown link targets used as explicit evidence references.

    Inline code and ``key=value`` examples are ordinary prose.  Only an
    explicit Markdown link enters the source-evidence check, so formatting a
    value as a code span cannot silently become a private claim language.
    """
    tokens: list[str] = []
    for match in MARKDOWN_LINK_RE.finditer(line):
        target = markdown_link_target(match.group("target"))
        if target:
            tokens.append(target)
    return tuple(dict.fromkeys(tokens))


def markdown_link_target(raw_target: str) -> str:
    """Return a local Markdown link target, excluding optional title/anchor data."""
    target = raw_target.strip().split(maxsplit=1)[0]
    if not target or target.startswith(("http://", "https://", "mailto:", "#")):
        return ""
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    return target.split("#", 1)[0].split("?", 1)[0].strip()


def extract_claims(path: str, text: str) -> tuple[Claim, ...]:
    """Extract design claim lines with explicit Markdown evidence links."""
    claims: list[Claim] = []
    for line_number, line in iter_body_lines(text):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if is_non_claim_control_line(stripped):
            continue
        tokens = checkable_tokens(stripped)
        if tokens and CLAIM_CUE_RE.search(stripped):
            claims.append(Claim(path, line_number, stripped, tokens))
    return tuple(claims)


def is_non_claim_control_line(line: str) -> bool:
    """Return whether one Markdown line is metadata or ledger scaffolding."""
    content = line.lstrip("-*0123456789. ").strip().lower()
    return content.startswith(
        (
            "run id:",
            "task:",
            "owner:",
            "created at",
            "evidence sources:",
            "assumptions:",
            "parent-doc alignment:",
            "refactor handoff:",
        )
    )


def token_path_candidates(token: str) -> tuple[str, ...]:
    """Return path-like candidates from a token or command token."""
    parts = [token]
    parts.extend(part for part in token.split() if "/" in part or Path(part).suffix)
    normalized: list[str] = []
    for part in parts:
        candidate = part.strip("'\";,")
        if candidate.startswith("./"):
            candidate = candidate[2:]
        normalized.append(candidate)
    return tuple(dict.fromkeys(normalized))


def token_is_path_in_repo(root: Path, claim_path: str, token: str) -> bool:
    """Return whether one token points to an existing repo path."""
    for candidate in token_path_candidates(token):
        if "*" in candidate:
            base = (
                resolve_repo_path(root, claim_path).parent
                if candidate.startswith("../")
                else root
            )
            if any(path_is_under_root(root, path) for path in base.glob(candidate)):
                return True
            continue
        try:
            path = resolve_claim_token_path(root, claim_path, candidate)
            if path_is_under_root(root, path) and path.exists():
                return True
        except (OSError, ValueError):
            # Formula/code tokens can look path-like while being invalid filesystem
            # names (for example a literal NUL escape). They are not repository
            # path evidence, but they must not abort claim evaluation.
            continue
    return False


def token_in_evidence(token: str, texts: dict[str, str]) -> bool:
    """Return whether one explicit link target appears in evidence text."""
    token_lower = token.lower()
    candidates = [token_lower]
    candidates.extend(candidate.lower() for candidate in token_path_candidates(token))
    if any(
        candidate and candidate in text.lower()
        for text in texts.values()
        for candidate in candidates
    ):
        return True
    if "*" in token:
        pattern = re.compile(re.escape(token_lower).replace(r"\*", r"[^\s`'\"|,]+"))
        return any(pattern.search(text.lower()) for text in texts.values())
    return False


def has_evidence_ledger(text: str) -> bool:
    """Return whether the design carries an evidence / assumption section."""
    return bool(
        section_text(
            text, ("evidence and assumption", "assumption ledger", "evidence ledger")
        )
    )


def claim_evidence_record_v1(
    claim: Claim,
    all_evidence_text: dict[str, str],
) -> ClaimEvidenceRecord:
    """Return one fixed-shape claim evidence record."""
    claim_hash = hashlib.sha256(claim.text.encode("utf-8")).hexdigest()
    return ClaimEvidenceRecord(
        record_version=1,
        claim_id=f"{claim.path}:{claim.line}",
        claim_text_sha256=claim_hash,
        evidence_class="current_state",
        input_identity=claim.path,
        owner_id="check_design_doc_claims",
        evidence_ids=tuple(sorted(all_evidence_text)),
        request_clause_ids=(),
        target_state_contract_sha256=None,
        final_readback_action_id=None,
        status="verified",
    )


def claim_evidence_class_counts(
    records: Sequence[ClaimEvidenceRecord],
) -> dict[str, int]:
    """Return stable counts by typed evidence class."""
    counts = {
        "current_state": 0,
        "request_contract": 0,
        "target_state": 0,
        "assumption": 0,
    }
    for record in records:
        counts[record.evidence_class] += 1
    return counts


def polarity_for_line(line: str) -> str:
    """Return positive, negative, or neutral polarity for a line."""
    if NEGATIVE_CUE_RE.search(line):
        return "negative"
    if POSITIVE_CUE_RE.search(line):
        return "positive"
    return "neutral"


def token_polarities(text: str) -> dict[str, set[str]]:
    """Return token to modal polarity mapping for one text."""
    entries = tuple(
        entry
        for _line_number, line in iter_body_lines(text)
        for entry in token_polarity_entries(line)
    )
    return {
        token: {polarity for entry_token, polarity in entries if entry_token == token}
        for token in sorted({entry_token for entry_token, _polarity in entries})
    }


def token_polarity_entries(line: str) -> tuple[tuple[str, str], ...]:
    """Return polarity entries for explicit Markdown evidence links."""
    return tuple(
        (token.lower(), polarity)
        for match in MARKDOWN_LINK_RE.finditer(line)
        if (token := markdown_link_target(match.group("target")))
        if (polarity := polarity_for_line(line[: match.start()])) != "neutral"
    )


def check_parent_contradictions(
    root: Path,
    path: str,
    text: str,
    parent_paths: Sequence[str],
) -> list[Finding]:
    """Find deterministic parent/child modal contradictions over evidence links."""
    child_polarities = token_polarities(text)
    findings: list[Finding] = []
    for parent_path in parent_paths:
        parent_polarities = token_polarities(read_text(root, parent_path))
        for token, child_values in sorted(child_polarities.items()):
            parent_values = parent_polarities.get(token, set())
            if "positive" in child_values and "negative" in parent_values:
                findings.append(
                    Finding(
                        "parent-document-contradiction",
                        path,
                        0,
                        f"token={token} parent={parent_path}",
                    )
                )
            if "negative" in child_values and "positive" in parent_values:
                findings.append(
                    Finding(
                        "parent-document-contradiction",
                        path,
                        0,
                        f"token={token} parent={parent_path}",
                    )
                )
    return findings


def check_claim_support(
    root: Path,
    claims: Sequence[Claim],
    evidence: dict[str, str],
) -> tuple[int, list[Finding], tuple[ClaimEvidenceRecord, ...]]:
    """Check explicit Markdown evidence links against source paths and text."""
    supported = 0
    findings: list[Finding] = []
    records: list[ClaimEvidenceRecord] = []
    for claim in claims:
        record = claim_evidence_record_v1(claim, evidence)
        records.append(record)
        token_findings = []
        for token in claim.tokens:
            if token_is_path_in_repo(root, claim.path, token) or token_in_evidence(
                token, evidence
            ):
                continue
            token_findings.append(
                Finding(
                    "claim-token-without-evidence",
                    claim.path,
                    claim.line,
                    f"token={token}",
                )
            )
        if token_findings:
            findings.extend(token_findings)
        else:
            supported += 1
    return supported, findings, tuple(records)


def missing_dependency_target_findings(
    root: Path, path: str, evidence_paths: Sequence[str]
) -> list[Finding]:
    """Return findings for dependency targets that do not resolve."""
    findings: list[Finding] = []
    for evidence_path in evidence_paths:
        if not resolve_repo_path(root, evidence_path).exists():
            findings.append(
                Finding(
                    "dependency-target-unresolved", path, 0, f"path={evidence_path}"
                )
            )
    return findings


def _check_one_from_manifest(
    root: Path,
    path: str,
    edges: Sequence[ManifestEdge],
    recursive_depth: int,
    changed_only: bool = False,
) -> CheckResult:
    """Check one design document."""
    if resolve_existing_text_path(root, path) is None:
        return CheckResult(
            path=path,
            claims=0,
            supported_claims=0,
            evidence_paths=(),
            parent_paths=(),
            claim_evidence_records=(),
            findings=(Finding("design-document-unresolved", path, 0, f"path={path}"),),
        )
    text = read_text(root, path)
    claims = (
        changed_implementation_claims(root, path)
        if changed_only
        else extract_claims(path, text)
    )
    evidence_paths, parent_paths, traversal_findings = dependency_closure(
        path, edges, recursive_depth
    )
    readable_evidence = evidence_texts(root, evidence_paths)
    supported, claim_findings, claim_evidence_records = check_claim_support(
        root,
        claims,
        readable_evidence,
    )
    findings: list[Finding] = []
    if claims and not has_evidence_ledger(text):
        findings.append(
            Finding(
                "missing-evidence-assumption-ledger",
                path,
                0,
                "section=Evidence And Assumption Ledger",
            )
        )
    findings.extend(traversal_findings)
    findings.extend(
        missing_dependency_target_findings(root, path, sorted(evidence_paths))
    )
    analysis_text = "\n".join(claim.text for claim in claims) if changed_only else text
    findings.extend(
        check_parent_contradictions(root, path, analysis_text, sorted(parent_paths))
    )
    findings.extend(claim_findings)
    return CheckResult(
        path=path,
        claims=len(claims),
        supported_claims=supported,
        evidence_paths=tuple(sorted(evidence_paths)),
        parent_paths=tuple(sorted(parent_paths)),
        claim_evidence_records=claim_evidence_records,
        findings=tuple(
            sorted(
                findings,
                key=lambda item: (item.kind, item.path, item.line, item.detail),
            )
        ),
    )


def selected_paths(root: Path, args: argparse.Namespace) -> tuple[str, ...]:
    """Return design-document paths selected by CLI arguments."""
    if args.paths:
        return tuple(repo_relative(root, path) for path in args.paths)
    if args.changed:
        return changed_design_paths(root)
    return tuple(path for path in git_files(root) if is_design_doc_path(path))


def render_text(results: Sequence[CheckResult]) -> str:
    """Render text output."""
    findings = [finding for result in results for finding in result.findings]
    lines: list[str] = []
    for finding in findings:
        lines.append(finding.render())
    aggregate_counts = {
        "current_state": 0,
        "request_contract": 0,
        "target_state": 0,
        "assumption": 0,
    }
    for result in results:
        for key, value in claim_evidence_class_counts(
            result.claim_evidence_records
        ).items():
            aggregate_counts[key] += value
    lines.extend(
        [
            f"DESIGN_DOC_CLAIMS_DOCUMENTS={len(results)}",
            f"DESIGN_DOC_CLAIMS_CHECKED={sum(result.claims for result in results)}",
            f"DESIGN_DOC_CLAIMS_SUPPORTED={sum(result.supported_claims for result in results)}",
            f"DESIGN_DOC_CLAIMS_EVIDENCE_PATHS={sum(len(result.evidence_paths) for result in results)}",
            f"DESIGN_DOC_CLAIMS_CURRENT_STATE={aggregate_counts['current_state']}",
            f"DESIGN_DOC_CLAIMS_REQUEST_CONTRACT={aggregate_counts['request_contract']}",
            f"DESIGN_DOC_CLAIMS_TARGET_STATE={aggregate_counts['target_state']}",
            f"DESIGN_DOC_CLAIMS_ASSUMPTION={aggregate_counts['assumption']}",
            f"DESIGN_DOC_CLAIMS_FINDINGS={len(findings)}",
            f"DESIGN_DOC_CLAIMS={'pass' if not findings else 'fail'}",
        ]
    )
    return "\n".join(lines)


def render_json(results: Sequence[CheckResult]) -> str:
    """Render JSON output."""
    findings = [finding for result in results for finding in result.findings]
    payload = {
        "status": "pass" if not findings else "fail",
        "documents": [asdict(result) for result in results],
        "finding_count": len(findings),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the design-document claim checker."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    paths = selected_paths(root, args)
    edges = all_manifest_edges(root)
    results = tuple(
        _check_one_from_manifest(
            root,
            path,
            edges,
            args.recursive_depth,
            changed_only=args.changed,
        )
        for path in paths
    )
    if args.format == "json":
        print(render_json(results))
    else:
        print(render_text(results))
    return 1 if any(result.findings for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
