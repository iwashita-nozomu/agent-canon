#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Checks design-document claims against implementation-backed evidence.
# upstream design ../../documents/dependency-manifest-design.md dependency manifest graph semantics
# upstream design ../../documents/design/README.md design-document evidence policy
# upstream implementation ./graph_client.py provides verified graph status, query, and context evidence
# downstream design ../../documents/tools/check_design_doc_claims.md tool contract
# downstream implementation ../../tests/agent_tools/test_check_design_doc_claims.py validates checker behavior
# @dependency-end
"""Check design-document claims against dependency and implementation evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.agent_tools.graph_client import (
    CANONICAL_GRAPH_EXECUTABLE,
    GraphClient,
    GraphClientError,
    GraphResponse,
)

DEFAULT_RECURSIVE_DEPTH = 3
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
ASSUMPTION_TERM_RE = re.compile(
    r"\bDSL\b|problem standard form|standard form|canonical form|normalization"
    r"|問題標準形|標準形|正規化|正準形",
    re.IGNORECASE,
)
HEADING_RE = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$")
TOKEN_RE = re.compile(r"`([^`]+)`")
KEY_VALUE_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*=\S+$")
DOTTED_SELECTOR_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\[\*\])?"
    r"(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\*\])?)+$"
)
MATH_OPERATOR_RE = re.compile(
    r"(?:\\(?:cap|cup|in|mapsto|notin|setminus|subset|subseteq|supset|"
    r"supseteq|times|to|varnothing)\b|[∖∪∩⊂⊆⊃⊇∈∉∅×→↦])"
)
MATH_WRAPPER_RE = re.compile(r"^(?:\$.*\$|\\\(.*\\\)|\\\[.*\\\])$", re.DOTALL)
MATH_EXPRESSION_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]*\([^)]*\)\s*(?:=|<|>|≤|≥|∈|⊂|⊆|⊃|⊇)"
)


class ClaimTokenClass(str, Enum):  # noqa: UP042 - supports the repository's Python floor.
    """Classification used before any claim token reaches filesystem APIs."""

    PATH = "path"
    PATH_OR_EVIDENCE = "path_or_evidence"
    EVIDENCE = "evidence"
    MATH_OR_PROSE = "math_or_prose"


@dataclass(frozen=True)
class Claim:
    """One checkable design claim line."""

    path: str
    line: int
    text: str
    tokens: tuple[str, ...]


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
    findings: tuple[Finding, ...]


class GraphClaimConsumer:
    """Graph-gated claim evidence and manifest metadata consumer."""

    def __init__(self, client: GraphClient, status: GraphResponse) -> None:
        """Bind one adapter and its prerequisite status response."""
        self.client = client
        self.status = status

    @classmethod
    def load(cls, root: Path) -> GraphClaimConsumer:
        """Load the prerequisite status without rebuilding or parsing source."""
        client = GraphClient(root, CANONICAL_GRAPH_EXECUTABLE)
        return cls(client, client.status())

    def status_reason(self) -> str | None:
        """Return the typed prerequisite failure for every nonfresh graph state."""
        if self.status.status != "fresh" or self.status.exit_code != 0:
            return (
                f"graph_status:{self.status.status};"
                f"reason={self.status.payload.get('reason')};"
                f"unresolved_count={self.status.payload.get('unresolved_count')};"
                f"ambiguous_count={self.status.payload.get('ambiguous_count')}"
            )
        raw_integration = self.status.payload.get("integration_record")
        if not isinstance(raw_integration, dict):
            return "graph_status:invalid;reason=missing-integration-record"
        integration = cast(dict[str, object], raw_integration)
        expected: dict[str, object] = {
            "schema": "agent-canon.graph.integration.v1",
            "root": ".",
            "db_path": ".agent-canon/knowledge-graph/graph.sqlite",
            "schema_version": "graph_storage_core.v1",
            "profile": "default",
            "source_snapshot_profile": "parent",
            "verified": True,
            "verification_code": "graph.integration.verified",
        }
        observed = {field: integration.get(field) for field in expected}
        if observed != expected:
            return f"graph_status:invalid;reason=integration-mismatch:{observed}"
        for field in ("input_fingerprint", "graph_fingerprint"):
            value = integration.get(field)
            if not isinstance(value, str) or not value:
                return f"graph_status:invalid;reason=integration-{field}-missing"
            if self.status.payload.get(field) != value:
                return f"graph_status:invalid;reason=integration-{field}-mismatch"
        snapshot_head = integration.get("snapshot_head")
        if not isinstance(snapshot_head, str) or not snapshot_head:
            return "graph_status:invalid;reason=integration-snapshot-head-missing"
        if not isinstance(integration.get("producer_artifacts"), list):
            return "graph_status:invalid;reason=integration-producer-artifacts-missing"
        return None

    @staticmethod
    def _require_fresh(response: GraphResponse, operation: str) -> None:
        if response.status != "fresh" or response.exit_code != 0:
            raise GraphClientError(
                f"graph_status:{response.status};operation={operation};"
                f"reason={response.payload.get('reason')}"
            )

    def context(self, path: str, token: str | None = None) -> GraphResponse:
        """Return one fresh graph-owned context response."""
        response = self.client.context(path, token)
        self._require_fresh(response, "context")
        return response

    def document_metadata(self, path: str) -> tuple[str, tuple[int, int] | None]:
        """Return manifest contract and span from canonical context items."""
        response = self.context(path)
        contract = ""
        manifest_span: tuple[int, int] | None = None
        for item in graph_context_items(response):
            if item.get("kind") == "manifest.contract" and isinstance(
                item.get("value"), str
            ):
                contract = str(item["value"])
            if item.get("kind") == "manifest.present":
                span = item.get("source_span")
                if isinstance(span, dict):
                    typed_span = cast(dict[str, object], span)
                    start = typed_span.get("start_line")
                    end = typed_span.get("end_line")
                    if isinstance(start, int) and isinstance(end, int):
                        manifest_span = (start, end)
        return contract, manifest_span

    def evidence_paths(
        self,
        target: str,
        recursive_depth: int,
    ) -> tuple[set[str], set[str]]:
        """Return graph-derived bounded evidence and direct parent paths."""
        response = self.client.query(
            path=target,
            all=False,
            relation="dependency",
            direction="both",
            depth=recursive_depth,
        )
        self._require_fresh(response, "query")
        evidence: set[str] = set()
        parents: set[str] = set()
        for fact in response.dependency_facts:
            if fact.kind not in {"design", "implementation"}:
                continue
            if fact.source != target:
                evidence.add(fact.source)
            if fact.target != target:
                evidence.add(fact.target)
            if (
                fact.source == target
                and fact.direction == "upstream"
                and fact.kind == "design"
            ):
                parents.add(fact.target)
        return evidence, parents

    def token_supported(
        self, claim_path: str, token: str
    ) -> tuple[bool, str | None]:
        """Check one classified token against only canonical graph context."""
        token_class = classify_claim_token(token)
        if token_class is ClaimTokenClass.MATH_OR_PROSE:
            return True, None
        response = self.context(claim_path, token)
        path_supported = isinstance(response.payload.get("resolved_path"), str) and isinstance(
            response.payload.get("source_span"), dict
        )
        if token_class is ClaimTokenClass.PATH:
            return path_supported, None if path_supported else "graph-code=path-unresolved"
        if path_supported or graph_context_matches_token(response, token):
            return True, None
        return False, "graph-code=evidence-unresolved"

    def parent_context_text(self, parent_path: str) -> str:
        """Return parent evidence text projected only from graph context fields."""
        response = self.context(parent_path)
        values: list[str] = []
        for item in graph_context_items(response):
            for field in ("value", "excerpt"):
                value = item.get(field)
                if isinstance(value, str) and value:
                    values.append(value)
        return "\n".join(values)


def graph_context_items(response: GraphResponse) -> tuple[Mapping[str, object], ...]:
    """Return validated graph context item mappings."""
    raw_items_value = response.payload.get("items")
    if not isinstance(raw_items_value, list):
        raise GraphClientError("graph context items must be an array")
    raw_items = cast(list[object], raw_items_value)
    items: list[Mapping[str, object]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise GraphClientError("graph context item must be an object")
        items.append(cast(dict[str, object], raw_item))
    return tuple(items)


def graph_context_matches_token(response: GraphResponse, token: str) -> bool:
    """Match one evidence token against context items and dependency witnesses."""
    evidence: dict[str, str] = {}
    for index, item in enumerate(graph_context_items(response)):
        for field in ("value", "excerpt", "evidence_ref", "source_path"):
            value = item.get(field)
            if isinstance(value, str) and value:
                evidence[f"item-{index}-{field}"] = value
    witnesses_value = response.payload.get("dependency_witnesses")
    if not isinstance(witnesses_value, list):
        raise GraphClientError("graph context dependency_witnesses must be an array")
    witnesses = cast(list[object], witnesses_value)
    for index, witness in enumerate(witnesses):
        if not isinstance(witness, dict):
            raise GraphClientError("graph context dependency witness must be an object")
        typed_witness = cast(dict[str, object], witness)
        for field, value in typed_witness.items():
            if isinstance(value, str) and value:
                evidence[f"witness-{index}-{field}"] = value
    return token_in_evidence(token, evidence)


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
        help="Check changed Markdown files under documents/design or agents/templates.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("paths", nargs="*", type=Path)
    return parser


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
    """Resolve one graph-declared root-relative or explicit absolute path."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return root / candidate


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


def is_checkable_path(path: str) -> bool:
    """Return whether a file path is a checkable source text path."""
    normalized = path.replace("\\", "/")
    if any(normalized.startswith(prefix) for prefix in SKIPPED_PREFIXES):
        return False
    return Path(normalized).suffix in TEXT_SUFFIXES


def changed_design_paths(root: Path) -> tuple[str, ...]:
    """Return changed design-document paths."""
    return design_paths_from_candidates(run_git_changed_path_names(root))


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
        or normalized == "agents/templates/design_brief.md"
        or normalized == "vendor/agent-canon/agents/templates/design_brief.md"
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


def iter_body_lines(
    text: str,
    manifest_span: tuple[int, int] | None = None,
) -> Iterable[tuple[int, str]]:
    """Yield non-fenced Markdown body lines."""
    in_fence = False
    for index, raw_line in enumerate(text.splitlines(), start=1):
        if manifest_span is not None and manifest_span[0] <= index <= manifest_span[1]:
            continue
        stripped = raw_line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
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
    """Return checkable backtick tokens from one line."""
    tokens: list[str] = []
    for raw_token in TOKEN_RE.findall(line):
        if token := normalized_checkable_token(raw_token):
            tokens.append(token)
    return tuple(dict.fromkeys(tokens))


def normalized_checkable_token(raw_token: str) -> str | None:
    """Return a normalized token when one Markdown code span is checkable."""
    token = raw_token.strip()
    if not token:
        return None
    if "..." in token:
        return None
    if "<" in token and ">" in token:
        return None
    if token.startswith(("http://", "https://")):
        return None
    if token.lower() in {"yes", "no", "pass", "fail", "active", "pending"}:
        return None
    if token.startswith("<") and token.endswith(">"):
        return None
    if not is_checkable_token(token):
        return None
    return token


def classify_claim_token(token: str) -> ClaimTokenClass:
    """Classify a claim token before selecting an evidence or path check."""
    stripped = token.strip()
    if (
        MATH_WRAPPER_RE.fullmatch(stripped)
        or MATH_OPERATOR_RE.search(stripped)
        or MATH_EXPRESSION_RE.match(stripped)
    ):
        return ClaimTokenClass.MATH_OR_PROSE
    if KEY_VALUE_TOKEN_RE.fullmatch(stripped):
        return ClaimTokenClass.EVIDENCE
    if DOTTED_SELECTOR_RE.fullmatch(stripped):
        return ClaimTokenClass.PATH_OR_EVIDENCE
    try:
        candidate = Path(stripped)
        if candidate.is_absolute() or stripped.startswith(("./", "../")):
            return ClaimTokenClass.PATH
        if "/" in stripped:
            return ClaimTokenClass.PATH
        if any(marker in stripped for marker in ("*", "?", "[")) and candidate.suffix:
            return ClaimTokenClass.PATH
        if candidate.suffix and not any(char.isspace() for char in stripped):
            return ClaimTokenClass.PATH_OR_EVIDENCE
    except (OSError, ValueError, RuntimeError):
        return ClaimTokenClass.PATH
    return ClaimTokenClass.EVIDENCE


def is_checkable_token(token: str) -> bool:
    """Return whether a Markdown code span is a checkable code/path token."""
    if classify_claim_token(token) is ClaimTokenClass.MATH_OR_PROSE:
        return True
    if KEY_VALUE_TOKEN_RE.fullmatch(token):
        return True
    if any(sep in token for sep in ("/", "\\", "::", ".", "_", "-")):
        return True
    if token.startswith("--"):
        return True
    if " " in token and any(
        part.endswith((".py", ".sh", ".rs", ".md")) for part in token.split()
    ):
        return True
    return token.isupper() and len(token) > 2


def strict_claim_prose_required(path: str, manifest_contract: str) -> bool:
    """Return whether cue-only prose lines are design claims for this document."""
    if "/design/" in path or path.endswith("-design.md"):
        return True
    return manifest_contract == "design"


def extract_claims(
    path: str,
    text: str,
    manifest_contract: str,
    manifest_span: tuple[int, int] | None,
) -> tuple[Claim, ...]:
    """Extract checkable design claim lines."""
    claims: list[Claim] = []
    strict_prose = strict_claim_prose_required(path, manifest_contract)
    for line_number, line in iter_body_lines(text, manifest_span):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if is_non_claim_control_line(stripped):
            continue
        tokens = checkable_tokens(stripped)
        if tokens or (strict_prose and CLAIM_CUE_RE.search(stripped)):
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


def key_value_token_in_evidence(token: str, texts: Mapping[str, str]) -> bool:
    """Return whether a key/value token has same-record evidence."""
    for separator in (":", "="):
        if separator not in token:
            continue
        key, value = (part.strip() for part in token.split(separator, 1))
        if not key or not value:
            return False
        pattern = re.compile(
            rf"(?<![\w.-]){re.escape(key)}[ \t]*[:=][ \t]*[\"'{{]?"
            rf"{re.escape(value)}[\"'}}]?(?![\w.-])",
            re.IGNORECASE,
        )
        return any(pattern.search(text) for text in texts.values())
    return False


def token_in_evidence(token: str, texts: Mapping[str, str]) -> bool:
    """Return whether one token appears in any evidence text."""
    token_lower = token.lower()
    candidates = [token_lower]
    if any(
        candidate and candidate in text.lower()
        for text in texts.values()
        for candidate in candidates
    ):
        return True
    if "*" in token:
        pattern = re.compile(re.escape(token_lower).replace(r"\*", r"[^\s`'\"|,]+"))
        return any(pattern.search(text.lower()) for text in texts.values())
    if key_value_token_in_evidence(token, texts):
        return True
    return False


def has_evidence_ledger(text: str) -> bool:
    """Return whether the design carries an evidence / assumption section."""
    return bool(
        section_text(
            text, ("evidence and assumption", "assumption ledger", "evidence ledger")
        )
    )


def assumption_terms(text: str) -> tuple[str, ...]:
    """Return implicit-assumption vocabulary terms present in text."""
    return tuple(
        dict.fromkeys(match.group(0) for match in ASSUMPTION_TERM_RE.finditer(text))
    )


def check_assumption_ledger(path: str, text: str) -> list[Finding]:
    """Check implicit assumption terms against the design ledger."""
    terms = assumption_terms(text)
    if not terms:
        return []
    ledger = section_text(
        text, ("evidence and assumption", "assumption ledger", "assumptions")
    )
    if not ledger:
        return [
            Finding(
                "implicit-assumption-without-ledger",
                path,
                0,
                f"terms={','.join(sorted(terms, key=str.lower))}",
            )
        ]
    ledger_lower = ledger.lower()
    findings: list[Finding] = []
    for term in terms:
        if term.lower() not in ledger_lower:
            findings.append(
                Finding("implicit-assumption-term-untracked", path, 0, f"term={term}")
            )
    return findings


def polarity_for_line(line: str) -> str:
    """Return positive, negative, or neutral polarity for a line."""
    if NEGATIVE_CUE_RE.search(line):
        return "negative"
    if POSITIVE_CUE_RE.search(line):
        return "positive"
    return "neutral"


def token_polarities(
    text: str,
    manifest_span: tuple[int, int] | None,
) -> dict[str, set[str]]:
    """Return token to modal polarity mapping for one text."""
    entries = tuple(
        entry
        for _line_number, line in iter_body_lines(text, manifest_span)
        for entry in token_polarity_entries(line)
    )
    return {
        token: {polarity for entry_token, polarity in entries if entry_token == token}
        for token in sorted({entry_token for entry_token, _polarity in entries})
    }


def token_polarity_entries(line: str) -> tuple[tuple[str, str], ...]:
    """Return polarity entries for checkable tokens in one prose line."""
    return tuple(
        (token.lower(), polarity)
        for match in TOKEN_RE.finditer(line)
        if (token := normalized_checkable_token(match.group(1)))
        if (polarity := polarity_for_line(line[: match.start()])) != "neutral"
    )


def check_parent_contradictions(
    consumer: GraphClaimConsumer,
    path: str,
    text: str,
    manifest_span: tuple[int, int] | None,
    parent_paths: Sequence[str],
) -> list[Finding]:
    """Find modal contradictions using only parent graph context strings."""
    child_polarities = token_polarities(text, manifest_span)
    findings: list[Finding] = []
    for parent_path in parent_paths:
        parent_polarities = token_polarities(
            consumer.parent_context_text(parent_path),
            None,
        )
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
    consumer: GraphClaimConsumer,
    claims: Sequence[Claim],
) -> tuple[int, list[Finding]]:
    """Check claim tokens against graph-owned path and evidence context."""
    supported = 0
    findings: list[Finding] = []
    for claim in claims:
        if not claim.tokens:
            findings.append(
                Finding(
                    "claim-without-checkable-token",
                    claim.path,
                    claim.line,
                    "add code/path/command evidence token or move statement to non-claim prose",
                )
            )
            continue
        token_findings: list[Finding] = []
        for token in claim.tokens:
            supported_token, reason = consumer.token_supported(claim.path, token)
            if supported_token:
                continue
            detail = f"token={token}"
            if reason is not None:
                detail = f"{detail};{reason}"
            token_findings.append(
                Finding(
                    "claim-token-without-evidence",
                    claim.path,
                    claim.line,
                    detail,
                )
            )
        if token_findings:
            findings.extend(token_findings)
        else:
            supported += 1
    return supported, findings


def check_one(
    root: Path,
    path: str,
    consumer: GraphClaimConsumer,
    recursive_depth: int,
) -> CheckResult:
    """Check one design document."""
    if status_reason := consumer.status_reason():
        return CheckResult(
            path=path,
            claims=0,
            supported_claims=0,
            evidence_paths=(),
            parent_paths=(),
            findings=(
                Finding("graph-integration-unverified", path, 0, status_reason),
            ),
        )
    if resolve_existing_text_path(root, path) is None:
        return CheckResult(
            path=path,
            claims=0,
            supported_claims=0,
            evidence_paths=(),
            parent_paths=(),
            findings=(Finding("design-document-unresolved", path, 0, f"path={path}"),),
        )
    text = read_text(root, path)
    try:
        contract, manifest_span = consumer.document_metadata(path)
        claims = extract_claims(path, text, contract, manifest_span)
        evidence_paths, parent_paths = consumer.evidence_paths(path, recursive_depth)
        supported, claim_findings = check_claim_support(consumer, claims)
        parent_findings = check_parent_contradictions(
            consumer,
            path,
            text,
            manifest_span,
            sorted(parent_paths),
        )
    except GraphClientError as error:
        return CheckResult(
            path=path,
            claims=0,
            supported_claims=0,
            evidence_paths=(),
            parent_paths=(),
            findings=(
                Finding("graph-unavailable", path, 0, f"graph-context:{error}"),
            ),
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
    findings.extend(check_assumption_ledger(path, text))
    findings.extend(parent_findings)
    findings.extend(claim_findings)
    return CheckResult(
        path=path,
        claims=len(claims),
        supported_claims=supported,
        evidence_paths=tuple(sorted(evidence_paths)),
        parent_paths=tuple(sorted(parent_paths)),
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
    lines.extend(
        [
            f"DESIGN_DOC_CLAIMS_DOCUMENTS={len(results)}",
            f"DESIGN_DOC_CLAIMS_CHECKED={sum(result.claims for result in results)}",
            f"DESIGN_DOC_CLAIMS_SUPPORTED={sum(result.supported_claims for result in results)}",
            f"DESIGN_DOC_CLAIMS_EVIDENCE_PATHS={sum(len(result.evidence_paths) for result in results)}",
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
    try:
        consumer = GraphClaimConsumer.load(root)
    except GraphClientError as error:
        print(f"DESIGN_DOC_CLAIMS_GRAPH_ERROR={error}")
        print("DESIGN_DOC_CLAIMS=fail")
        return 1
    results = tuple(
        check_one(root, path, consumer, args.recursive_depth) for path in paths
    )
    if args.format == "json":
        print(render_json(results))
    else:
        print(render_text(results))
    return 1 if any(result.findings for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
