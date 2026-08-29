#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Reconciles GitHub Issue status labels with typed evidence and readback.
# upstream design ../../agents/internal-routines/github-status-lifecycle.md owns lifecycle semantics.
# upstream design ../../documents/operations/issue-label-taxonomy.toml owns repository labels.
# upstream implementation ./github_publish.py owns the injectable Runner boundary.
# downstream implementation ../../tests/agent_tools/test_github_status_lifecycle.py validates this adapter.
# @dependency-end
"""GitHub Issue status-label reconciliation.

The module deliberately contains two small boundaries:

* :class:`GhStatusAdapter` performs only GitHub API transport and response
  normalization; and
* the functions below it calculate lifecycle state and expected transitions
  without performing I/O.

GitHub does not expose a conditional Issue-comment or label mutation API. The
reconciler therefore reports observable races and partial mutations instead of
claiming CAS or attempting an unsafe rollback.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from urllib.parse import quote

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]

from tools.runtime.artifacts.artifact_identity import canonical_json_bytes
from tools.repository.github.github_publish import CommandResult, Runner, run_command, subprocess_runner

MODULE_OWNER = "github_status_lifecycle.py"
LIFECYCLE_SCOPE = "status-label-lifecycle"
TRANSPORT_SCOPE = "github-api-transport"
MARKER_PREFIX = "<!-- agent-canon:github-status-lifecycle:v1 key=sha256:"
MARKER_RE = re.compile(
    r"^<!-- agent-canon:github-status-lifecycle:v1 key=sha256:(?P<key>[0-9a-f]{64}) -->"
)
REPO_RE = re.compile(r"^[^/\s]+/[^/\s]+$")
NUMBER_RE = re.compile(r"^[0-9]+$")
EVIDENCE_FIELDS = (
    "baseline",
    "branch",
    "head",
    "scope",
    "validation",
    "remaining_verification",
    "readback_expectation",
)
PR_FIELDS = ("repo", "number", "url", "base_sha", "head_sha")
VERIFICATION_GAP_FIELDS = (
    "property",
    "reason",
    "attempt",
    "observed_result",
    "environment",
    "owner",
    "next_command",
)


class LifecycleFailure(Exception):
    """Typed failure that keeps owner and responsibility in every report."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        code_owner: str = MODULE_OWNER,
        responsibility_scope: str = LIFECYCLE_SCOPE,
        details: Mapping[str, object] | None = None,
        next_action: str = "fresh-reconcile-after-owner-review",
    ) -> None:
        """Initialize a typed failure with its owner and scope."""
        self.code = code
        self.message = message
        self.code_owner = code_owner
        self.responsibility_scope = responsibility_scope
        self.details = dict(details or {})
        self.next_action = next_action
        super().__init__(message)

    def as_dict(self) -> dict[str, object]:
        """Return a stable failure report suitable for logs and callers."""
        return {
            "kind": "failure",
            "code": self.code,
            "message": self.message,
            "code_owner": self.code_owner,
            "responsibility_scope": self.responsibility_scope,
            "details": self.details,
            "next_action": self.next_action,
        }

    def __str__(self) -> str:
        """Serialize the failure report for deterministic logs."""
        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class LabelMapping:
    """Canonical status labels and explicitly declared legacy aliases."""

    active: str
    ready_for_review: str
    needs_verification: str
    legacy_aliases_active: tuple[str, ...] = ()
    legacy_aliases_ready_for_review: tuple[str, ...] = ()
    legacy_aliases_needs_verification: tuple[str, ...] = ()

    @property
    def canonical(self) -> dict[str, str]:
        """Return canonical role-to-label names."""
        return {
            "active": self.active,
            "ready_for_review": self.ready_for_review,
            "needs_verification": self.needs_verification,
        }

    @property
    def legacy_aliases(self) -> dict[str, tuple[str, ...]]:
        """Return explicitly declared legacy aliases by role."""
        return {
            "active": self.legacy_aliases_active,
            "ready_for_review": self.legacy_aliases_ready_for_review,
            "needs_verification": self.legacy_aliases_needs_verification,
        }

    @property
    def managed(self) -> frozenset[str]:
        """Return canonical labels and declared aliases."""
        return frozenset(
            set(self.canonical.values())
            | {alias for aliases in self.legacy_aliases.values() for alias in aliases}
        )

    def as_dict(self) -> dict[str, object]:
        """Return the canonical mapping record."""
        return {
            "status_lifecycle": {
                **self.canonical,
                "legacy_aliases": {
                    role: list(values) for role, values in self.legacy_aliases.items()
                },
            }
        }

    @property
    def digest(self) -> str:
        """Return the canonical mapping digest."""
        return hashlib.sha256(canonical_json_bytes(self.as_dict())).hexdigest()

    def desired(self, state: str) -> frozenset[str]:
        """Return the desired canonical labels for one lifecycle state."""
        try:
            if state == "active":
                return frozenset({self.active})
            if state == "review-ready":
                return frozenset({self.ready_for_review})
            if state == "review-ready-unverified":
                return frozenset({self.ready_for_review, self.needs_verification})
        except AttributeError as exc:  # defensive for malformed caller objects
            raise LifecycleFailure("label_mapping_invalid", "incomplete label mapping") from exc
        raise LifecycleFailure(
            "lifecycle_facts_incomplete",
            f"unknown lifecycle state: {state}",
            details={"state": state},
        )


def _failure(code: str, message: str, *, scope: str = LIFECYCLE_SCOPE, **details: object) -> LifecycleFailure:
    return LifecycleFailure(code, message, responsibility_scope=scope, details=details)


def _require_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _failure("label_mapping_invalid", f"{field} must be a non-empty string", field=field)
    return value


def _parse_aliases(value: object, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _failure("label_mapping_invalid", f"{field} must be an array of strings", field=field)
    values = cast(list[object], value)
    if any(not isinstance(item, str) for item in values):
        raise _failure("label_mapping_invalid", f"{field} must be an array of strings", field=field)
    aliases = tuple(cast(str, item).strip() for item in values)
    if any(not alias for alias in aliases) or len(set(aliases)) != len(aliases):
        raise _failure("label_mapping_invalid", f"{field} contains empty or duplicate names", field=field)
    return aliases


def mapping_from_data(data: Mapping[str, object]) -> LabelMapping:
    """Parse and validate the exact TOML mapping schema."""
    if set(data) != {"status_lifecycle"}:
        raise _failure("label_mapping_invalid", "taxonomy has unknown top-level keys", keys=sorted(data))
    raw_value = data.get("status_lifecycle")
    if not isinstance(raw_value, Mapping):
        raise _failure("label_mapping_invalid", "status_lifecycle must be a table")
    raw = cast(Mapping[str, object], raw_value)
    required = {"active", "ready_for_review", "needs_verification"}
    allowed = required | {"legacy_aliases"}
    unknown = set(raw) - allowed
    if unknown:
        raise _failure("label_mapping_invalid", "status_lifecycle has unknown keys", keys=sorted(unknown))
    aliases_value = raw.get("legacy_aliases", {})
    if not isinstance(aliases_value, Mapping):
        raise _failure("label_mapping_invalid", "legacy_aliases must be a table")
    aliases_raw = cast(Mapping[str, object], aliases_value)
    alias_unknown = set(aliases_raw) - required
    if alias_unknown:
        raise _failure("label_mapping_invalid", "legacy_aliases has unknown keys", keys=sorted(alias_unknown))
    mapping = LabelMapping(
        active=_require_string(raw.get("active"), field="active"),
        ready_for_review=_require_string(raw.get("ready_for_review"), field="ready_for_review"),
        needs_verification=_require_string(raw.get("needs_verification"), field="needs_verification"),
        legacy_aliases_active=_parse_aliases(aliases_raw.get("active"), field="legacy_aliases.active"),
        legacy_aliases_ready_for_review=_parse_aliases(
            aliases_raw.get("ready_for_review"), field="legacy_aliases.ready_for_review"
        ),
        legacy_aliases_needs_verification=_parse_aliases(
            aliases_raw.get("needs_verification"), field="legacy_aliases.needs_verification"
        ),
    )
    names = list(mapping.canonical.values())
    aliases = [alias for values in mapping.legacy_aliases.values() for alias in values]
    if len(set(names)) != len(names):
        raise _failure("label_mapping_invalid", "canonical label names must be distinct")
    if set(names) & set(aliases):
        raise _failure("label_mapping_invalid", "legacy alias equals a canonical label")
    if len(set(aliases)) != len(aliases):
        raise _failure("label_mapping_invalid", "legacy aliases must be globally distinct")
    return mapping


def load_label_mapping(root: str | Path | None = None) -> LabelMapping:
    """Load the sole repository taxonomy owner relative to AgentCanon root."""
    source_root = Path(root or Path(__file__).resolve().parents[3])
    path = source_root / "documents" / "operations" / "issue-label-taxonomy.toml"
    try:
        with path.open("rb") as stream:
            loaded = tomllib.load(stream)
    except (OSError, ValueError) as exc:
        raise _failure("label_mapping_invalid", f"cannot load taxonomy: {path}", path=str(path)) from exc
    return mapping_from_data(cast(Mapping[str, object], loaded))


def validate_remote_catalog(mapping: LabelMapping, labels: Sequence[str] | frozenset[str]) -> frozenset[str]:
    """Require every canonical label, while allowing absent historical aliases."""
    catalog = frozenset(labels)
    missing = sorted(set(mapping.canonical.values()) - catalog)
    if missing:
        raise _failure("label_mapping_invalid", "canonical labels are absent from remote catalog", missing=missing)
    return catalog


def _json(text: str, *, operation: str, scope: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise _failure("transport_failure", f"{operation} returned invalid JSON", scope=scope) from exc


def _run_json(runner: Runner, command: Sequence[str], *, operation: str, scope: str) -> object:
    try:
        result = run_command(runner, command, next_action=f"retry_{operation}")
    except Exception as exc:
        if isinstance(exc, LifecycleFailure):
            raise
        # github_publish.CommandFailure deliberately remains its own API. Keep
        # this lifecycle failure typed and include the original result.
        result = getattr(exc, "result", None)
        details: dict[str, object] = {"operation": operation}
        if isinstance(result, CommandResult):
            details.update({"args": list(result.args), "stderr": result.stderr})
        raise _failure("transport_failure", f"{operation} command failed", scope=scope, **details) from exc
    return _json(result.stdout, operation=operation, scope=scope)


def _validate_repo_issue(repo: str, issue_number: str | int) -> tuple[str, str]:
    repo_text = str(repo)
    number_text = str(issue_number)
    if not REPO_RE.fullmatch(repo_text):
        raise _failure("issue_unresolved", "repository must be an owner/name slug", repo=repo_text)
    if not NUMBER_RE.fullmatch(number_text):
        raise _failure("issue_unresolved", "Issue number must be decimal digits", issue=number_text)
    return repo_text, number_text


def _flatten_pages(value: object, *, operation: str) -> list[object]:
    if not isinstance(value, list):
        raise _failure("transport_failure", f"{operation} expected a slurped list of pages", scope=TRANSPORT_SCOPE)
    pages = cast(list[object], value)
    if any(not isinstance(page_value, list) for page_value in pages):
        raise _failure("transport_failure", f"{operation} expected a slurped list of pages", scope=TRANSPORT_SCOPE)
    items: list[object] = []
    for page_value in pages:
        page = cast(list[object], page_value)
        items.extend(page)
    return items


@dataclass(frozen=True)
class IssueSnapshot:
    """Normalized Issue identity and complete label snapshot."""

    number: int
    url: str
    state: str
    labels: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return the snapshot as canonical JSON-compatible data."""
        return {"number": self.number, "url": self.url, "state": self.state, "labels": list(self.labels)}


@dataclass(frozen=True)
class CommentSnapshot:
    """Normalized Issue-comment identity and body."""

    comment_id: int
    body: str
    url: str

    def as_dict(self) -> dict[str, object]:
        """Return the comment as JSON-compatible data."""
        return {"id": self.comment_id, "body": self.body, "url": self.url}


class GhStatusAdapter:
    """Transport-only GitHub adapter with an injectable ``Runner``."""

    def __init__(self, repo: str, issue_number: str | int, runner: Runner = subprocess_runner) -> None:
        """Create a transport adapter for one validated Issue locator."""
        self.repo, self.issue_number = _validate_repo_issue(repo, issue_number)
        self.runner = runner

    def _api_json(self, command: Sequence[str], *, operation: str) -> object:
        return _run_json(self.runner, command, operation=operation, scope=TRANSPORT_SCOPE)

    def issue(self) -> IssueSnapshot:
        """Read and normalize the complete Issue snapshot."""
        value = self._api_json(["gh", "api", f"repos/{self.repo}/issues/{self.issue_number}"], operation="issue_snapshot")
        if not isinstance(value, Mapping):
            raise _failure("transport_failure", "Issue snapshot must be an object", scope=TRANSPORT_SCOPE)
        issue_value = cast(Mapping[str, object], value)
        raw_labels = issue_value.get("labels")
        if not isinstance(raw_labels, list):
            raise _failure("transport_failure", "Issue labels must be a list", scope=TRANSPORT_SCOPE)
        labels: list[str] = []
        seen_labels: set[str] = set()
        for item_value in cast(list[object], raw_labels):
            if not isinstance(item_value, Mapping):
                raise _failure("transport_failure", "Issue label entry is malformed", scope=TRANSPORT_SCOPE)
            item = cast(Mapping[str, object], item_value)
            if not isinstance(item.get("name"), str) or not cast(str, item["name"]).strip():
                raise _failure("transport_failure", "Issue label entry is malformed", scope=TRANSPORT_SCOPE)
            label_name = cast(str, item["name"])
            if label_name in seen_labels:
                raise _failure("transport_failure", "Issue label identity is duplicated", scope=TRANSPORT_SCOPE)
            seen_labels.add(label_name)
            labels.append(label_name)
        number = issue_value.get("number")
        url = issue_value.get("html_url", issue_value.get("url"))
        state = issue_value.get("state")
        if (
            isinstance(number, bool)
            or not isinstance(number, int)
            or number != int(self.issue_number)
            or not isinstance(url, str)
            or not url.strip()
            or not isinstance(state, str)
            or not state.strip()
        ):
            raise _failure("transport_failure", "Issue identity fields are malformed", scope=TRANSPORT_SCOPE)
        return IssueSnapshot(number, url, state, tuple(labels))

    def comments(self) -> tuple[CommentSnapshot, ...]:
        """Read, flatten, deduplicate, and sort paginated comments."""
        value = self._api_json(
            [
                "gh",
                "api",
                "--paginate",
                "--slurp",
                f"repos/{self.repo}/issues/{self.issue_number}/comments?per_page=100",
            ],
            operation="comment_snapshot",
        )
        items = _flatten_pages(value, operation="comment_snapshot")
        normalized: dict[int, CommentSnapshot] = {}
        for item_value in items:
            if not isinstance(item_value, Mapping):
                raise _failure("transport_failure", "comment entry is malformed", scope=TRANSPORT_SCOPE)
            item = cast(Mapping[str, object], item_value)
            comment_id, body, url = item.get("id"), item.get("body"), item.get("html_url", item.get("url"))
            if not isinstance(comment_id, int) or not isinstance(body, str) or not isinstance(url, str):
                raise _failure("transport_failure", "comment requires id, body, and url", scope=TRANSPORT_SCOPE)
            normalized[comment_id] = CommentSnapshot(comment_id, body, url)
        return tuple(normalized[key] for key in sorted(normalized))

    def label_catalog(self) -> frozenset[str]:
        """Read and normalize the repository label catalog."""
        value = self._api_json(
            [
                "gh",
                "api",
                "--paginate",
                "--slurp",
                f"repos/{self.repo}/labels?per_page=100",
            ],
            operation="label_catalog",
        )
        items = _flatten_pages(value, operation="label_catalog")
        labels: set[str] = set()
        for item_value in items:
            if not isinstance(item_value, Mapping):
                raise _failure("transport_failure", "repository label entry is malformed", scope=TRANSPORT_SCOPE)
            item = cast(Mapping[str, object], item_value)
            if not isinstance(item.get("name"), str):
                raise _failure("transport_failure", "repository label entry is malformed", scope=TRANSPORT_SCOPE)
            labels.add(cast(str, item["name"]))
        return frozenset(labels)

    def create_comment(self, body: str) -> CommandResult:
        """Create exactly one evidence comment through the GitHub API."""
        command = [
            "gh",
            "api",
            "--method",
            "POST",
            f"repos/{self.repo}/issues/{self.issue_number}/comments",
            "-f",
            f"body={body}",
        ]
        try:
            return run_command(self.runner, command, next_action="read_back_created_evidence_comment")
        except Exception as exc:
            raise _failure("evidence_readback_unavailable", "evidence comment create failed", scope=TRANSPORT_SCOPE) from exc

    def add_label(self, label: str) -> CommandResult:
        """Add one label and leave readback to the reconciler."""
        command = [
            "gh", "api", "--method", "POST", f"repos/{self.repo}/issues/{self.issue_number}/labels", "-f", f"labels[]={label}"
        ]
        try:
            return run_command(self.runner, command, next_action="read_back_added_label")
        except Exception as exc:
            raise _failure("mutation_partial", "label add failed", operation=f"add:{label}") from exc

    def remove_label(self, label: str) -> CommandResult:
        """Remove one URL-encoded label and leave readback to the reconciler."""
        encoded = quote(label, safe="")
        command = [
            "gh", "api", "--method", "DELETE", f"repos/{self.repo}/issues/{self.issue_number}/labels/{encoded}"
        ]
        try:
            return run_command(self.runner, command, next_action="read_back_removed_label")
        except Exception as exc:
            raise _failure("mutation_partial", "label remove failed", operation=f"remove:{label}") from exc


def classify_lifecycle(facts: Mapping[str, object]) -> str:
    """Purely classify lifecycle facts; no status is inferred from labels."""
    if not isinstance(facts.get("work_started"), bool):
        raise _failure("lifecycle_facts_incomplete", "work_started is required")
    if not facts["work_started"]:
        raise _failure("lifecycle_facts_incomplete", "work_started must be true")
    if facts.get("implementation_failure") or facts.get("validation_failed"):
        return "active"
    handoff_ready = facts.get("handoff_ready")
    validation_complete = facts.get("validation_complete")
    if not isinstance(handoff_ready, bool) or not isinstance(validation_complete, bool):
        raise _failure("lifecycle_facts_incomplete", "handoff_ready and validation_complete are required")
    if not handoff_ready or not validation_complete:
        return "active"
    unavailable = facts.get("verification_unavailable", False)
    if not isinstance(unavailable, bool):
        raise _failure("lifecycle_facts_incomplete", "verification_unavailable must be boolean")
    if not unavailable:
        return "review-ready"
    gap_value = facts.get("verification_gap")
    gap = cast(Mapping[str, object], gap_value) if isinstance(gap_value, Mapping) else None
    required = ("property", "reason", "attempt", "observed_result", "environment", "next_command")
    if gap is None or any(
        not isinstance(gap.get(key), str) or not cast(str, gap[key]).strip() for key in required
    ):
        raise _failure("verification_gap_incomplete", "verification gap must contain all required fields")
    return "review-ready-unverified"


def _has_evidence_value(value: object) -> bool:
    """Return whether an evidence field is materially populated."""
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return len(cast(Mapping[str, object], value)) > 0
    if isinstance(value, Sequence):
        return len(cast(Sequence[object], value)) > 0
    return True


def validate_evidence_inputs(
    *,
    lifecycle: str,
    evidence: Mapping[str, object],
    pr_identity: Mapping[str, object],
    repo: str,
    issue_number: str | int,
) -> None:
    """Fail closed on evidence, PR identity, and verification-gap omissions."""
    if not NUMBER_RE.fullmatch(str(issue_number)):
        raise _failure("issue_unresolved", "Issue number must be decimal digits")
    missing = [field for field in EVIDENCE_FIELDS if not _has_evidence_value(evidence.get(field))]
    if missing:
        raise _failure(
            "lifecycle_facts_incomplete",
            "required evidence fields are missing or empty",
            missing_fields=missing,
        )
    for field in ("branch", "head"):
        value = evidence.get(field)
        if not isinstance(value, str) or not value.strip():
            raise _failure("lifecycle_facts_incomplete", f"evidence {field} must be a non-empty string")
    if pr_identity.get("repo") != repo:
        raise _failure("lifecycle_facts_incomplete", "PR identity repository does not match Issue repository")
    missing_pr = [field for field in PR_FIELDS if not _has_evidence_value(pr_identity.get(field))]
    if missing_pr:
        raise _failure(
            "lifecycle_facts_incomplete",
            "required PR identity fields are missing or empty",
            missing_fields=missing_pr,
        )
    number = pr_identity.get("number")
    if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
        raise _failure("lifecycle_facts_incomplete", "PR number must be a positive integer")
    if not isinstance(pr_identity.get("url"), str) or not cast(str, pr_identity["url"]).strip():
        raise _failure("lifecycle_facts_incomplete", "PR URL must be non-empty")
    for field in ("base_sha", "head_sha"):
        value = pr_identity.get(field)
        if not isinstance(value, str) or not value.strip():
            raise _failure("lifecycle_facts_incomplete", f"PR {field} must be a non-empty string")
    if lifecycle == "review-ready-unverified":
        raw_gap = evidence.get("verification_gap", evidence.get("remaining_verification"))
        if not isinstance(raw_gap, Mapping):
            raise _failure("verification_gap_incomplete", "verification gap owner and evidence are required")
        gap = cast(Mapping[str, object], raw_gap)
        missing_gap = [field for field in VERIFICATION_GAP_FIELDS if not _has_evidence_value(gap.get(field))]
        if missing_gap:
            raise _failure(
                "verification_gap_incomplete",
                "verification gap fields are missing or empty",
                missing_fields=missing_gap,
            )


def desired_labels(mapping: LabelMapping, state: str) -> frozenset[str]:
    """Return the pure desired set for a lifecycle state."""
    return mapping.desired(state)


def plan_operations(observed: Sequence[str], desired: Sequence[str] | set[str] | frozenset[str], mapping: LabelMapping) -> list[tuple[str, str]]:
    """Plan removals before additions, preserving unrelated labels."""
    observed_set = set(observed)
    desired_set = set(desired)
    remove = observed_set & set(mapping.managed) - desired_set
    add = desired_set - observed_set
    order = [mapping.active, mapping.ready_for_review, mapping.needs_verification]
    order.extend(alias for values in mapping.legacy_aliases.values() for alias in values)
    return [("remove", label) for label in order if label in remove] + [
        ("add", label) for label in order if label in add
    ]


def evaluate_final(
    observed: Sequence[str],
    desired: Sequence[str] | set[str] | frozenset[str],
    initial: Sequence[str],
    mapping: LabelMapping,
    evidence_count: int,
) -> bool:
    """Evaluate the complete final success predicate without I/O."""
    observed_set = set(observed)
    desired_set = set(desired)
    managed_canonical = set(mapping.canonical.values())
    observed_canonical = observed_set & managed_canonical
    declared_aliases = {alias for values in mapping.legacy_aliases.values() for alias in values}
    unrelated_before = set(initial) - set(mapping.managed)
    unrelated_after = observed_set - set(mapping.managed)
    return (
        observed_canonical == desired_set
        and not (observed_set & declared_aliases)
        and unrelated_after == unrelated_before
        and evidence_count == 1
    )


def _payload_digest(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def operation_identity(payload: Mapping[str, object]) -> str:
    """Hash stable evidence/PR identity while excluding mutable snapshots."""
    derived = {
        "evidence_payload_digest",
        "operation_identity_digest",
        "source_snapshot_digest",
        "attempt_key",
    }
    stable_payload = {key: value for key, value in payload.items() if key not in derived}
    return _payload_digest(stable_payload)


def attempt_key(payload: Mapping[str, object]) -> str:
    """Return a per-preflight retry key bound to stable operation identity."""
    identity = {
        "repo": payload.get("repo"),
        "issue": payload.get("issue"),
        "operation_identity_digest": payload.get("operation_identity_digest")
        or operation_identity(payload),
        "source_snapshot_digest": payload.get("source_snapshot_digest"),
    }
    return _payload_digest(identity)


def build_evidence_payload(
    *,
    repo: str,
    issue_number: str | int,
    lifecycle: str,
    evidence: Mapping[str, object],
    pr_identity: Mapping[str, object],
    source_snapshot: Mapping[str, object],
    mapping: LabelMapping,
) -> dict[str, object]:
    """Bind evidence to PR identity, taxonomy, and preflight snapshot."""
    payload: dict[str, object] = dict(evidence)
    payload.update(
        {
            "repo": repo,
            "issue": int(issue_number),
            "lifecycle": lifecycle,
            "pr_identity": dict(pr_identity),
            "pr": dict(pr_identity),
            "taxonomy_mapping_digest": f"sha256:{mapping.digest}",
            "source_snapshot_digest": f"sha256:{_payload_digest(source_snapshot)}",
        }
    )
    payload["operation_identity_digest"] = f"sha256:{operation_identity(payload)}"
    payload["evidence_payload_digest"] = f"sha256:{_payload_digest(payload)}"
    return payload


def evidence_comment(payload: Mapping[str, object]) -> str:
    """Render a stable marker and canonical evidence payload body."""
    key = attempt_key(payload)
    return f"{MARKER_PREFIX}{key} -->\n\n```json\n{json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, indent=2)}\n```"


def matching_comments(comments: Sequence[CommentSnapshot], payload: Mapping[str, object]) -> tuple[list[CommentSnapshot], list[CommentSnapshot]]:
    """Return exact-body comments and same-attempt conflicting comments."""
    body = evidence_comment(payload)
    key = attempt_key(payload)
    exact = [comment for comment in comments if comment.body == body]
    same_key: list[CommentSnapshot] = []
    for comment in comments:
        match = MARKER_RE.match(comment.body)
        if match and match.group("key") == key and comment not in exact:
            same_key.append(comment)
    return exact, same_key


def _comment_payload(comment: CommentSnapshot) -> dict[str, object] | None:
    """Decode the JSON evidence payload from a canonical comment body."""
    marker = MARKER_RE.match(comment.body)
    if marker is None:
        return None
    match = re.search(r"\n```json\n(?P<payload>.*?)\n```\s*$", comment.body, re.DOTALL)
    if match is None:
        return None
    try:
        value = json.loads(match.group("payload"))
    except json.JSONDecodeError:
        return None
    if not isinstance(value, Mapping):
        return None
    parsed = cast(Mapping[str, object], value)
    if parsed.get("operation_identity_digest") != f"sha256:{operation_identity(parsed)}":
        return None
    return dict(parsed)


def _operation_matches(
    comments: Sequence[CommentSnapshot], payload: Mapping[str, object]
) -> list[tuple[CommentSnapshot, dict[str, object]]]:
    """Find historical exact operation identities across source snapshots."""
    identity = payload.get("operation_identity_digest") or f"sha256:{operation_identity(payload)}"
    matches: list[tuple[CommentSnapshot, dict[str, object]]] = []
    for comment in comments:
        historical = _comment_payload(comment)
        if historical is not None and historical.get("operation_identity_digest") == identity:
            matches.append((comment, historical))
    return matches


def _select_evidence(
    comments: Sequence[CommentSnapshot], payload: Mapping[str, object]
) -> tuple[CommentSnapshot, dict[str, object]] | None:
    """Select one historical payload or raise typed conflict/duplicate stops."""
    exact, same_attempt_key = matching_comments(comments, payload)
    if same_attempt_key:
        raise _failure(
            "evidence_conflict",
            "one retry marker has a conflicting payload",
            comment_ids=[item.comment_id for item in same_attempt_key],
        )
    if len(exact) > 1:
        raise _failure(
            "evidence_duplicate",
            "one retry marker has multiple exact comments",
            comment_ids=[item.comment_id for item in exact],
            next_action="manual-evidence-dedup-or-new-attempt",
        )
    matches = _operation_matches(comments, payload)
    if len(matches) > 1:
        unique_payloads = {canonical_json_bytes(item[1]) for item in matches}
        if len(unique_payloads) > 1:
            raise _failure(
                "evidence_conflict",
                "one operation identity has conflicting historical payloads",
                comment_ids=[item[0].comment_id for item in matches],
            )
        raise _failure(
            "evidence_duplicate",
            "one operation identity has multiple historical comments",
            comment_ids=[item[0].comment_id for item in matches],
            next_action="manual-evidence-dedup-or-new-attempt",
        )
    if matches:
        return matches[0]
    return None


def reconcile_status(
    adapter: GhStatusAdapter,
    *,
    mapping: LabelMapping,
    facts: Mapping[str, object],
    evidence: Mapping[str, object],
    pr_identity: Mapping[str, object],
) -> dict[str, object]:
    """Run one strict evidence-before-label reconciliation."""
    state = classify_lifecycle(facts)
    desired = desired_labels(mapping, state)
    validate_evidence_inputs(
        lifecycle=state,
        evidence=evidence,
        pr_identity=pr_identity,
        repo=adapter.repo,
        issue_number=adapter.issue_number,
    )
    catalog = validate_remote_catalog(mapping, adapter.label_catalog())
    before_issue = adapter.issue()
    before_comments = adapter.comments()
    source_snapshot = {"issue": before_issue.as_dict(), "catalog": sorted(catalog), "pr_identity": dict(pr_identity)}
    payload = build_evidence_payload(
        repo=adapter.repo,
        issue_number=adapter.issue_number,
        lifecycle=state,
        evidence=evidence,
        pr_identity=pr_identity,
        source_snapshot=source_snapshot,
        mapping=mapping,
    )
    selected = _select_evidence(before_comments, payload)
    if selected is None:
        adapter.create_comment(evidence_comment(payload))
        after_comments = adapter.comments()
        selected = _select_evidence(after_comments, payload)
        if selected is None:
            raise _failure(
                "evidence_readback_unavailable",
                "created evidence comment was not uniquely readable",
            )
    evidence_comment_snapshot, selected_payload = selected
    after_evidence_issue = adapter.issue()
    if set(after_evidence_issue.labels) != set(before_issue.labels):
        raise _failure(
            "concurrent_status_drift",
            "Issue labels changed while publishing evidence",
            initial_labels=list(before_issue.labels),
            observed_labels=list(after_evidence_issue.labels),
        )
    expected = set(before_issue.labels)
    operations = plan_operations(before_issue.labels, desired, mapping)
    completed: list[str] = []
    observed = list(before_issue.labels)
    for operation, label in operations:
        current = list(adapter.issue().labels)
        if set(current) != set(observed):
            raise _failure("concurrent_status_drift", "labels changed before mutation", observed_labels=current)
        try:
            if operation == "remove":
                adapter.remove_label(label)
                expected.discard(label)
            else:
                adapter.add_label(label)
                expected.add(label)
        except LifecycleFailure as exc:
            observed_after = list(adapter.issue().labels)
            raise LifecycleFailure(
                "mutation_partial", "label mutation stopped without rollback", details={
                    "completed_operations": completed,
                    "failed_operation": f"{operation}:{label}",
                    "response_state": "ambiguous",
                    "observed_labels": observed_after,
                    "desired_labels": sorted(desired),
                    "unrelated_before": sorted(set(before_issue.labels) - set(mapping.managed)),
                    "unrelated_after": sorted(set(observed_after) - set(mapping.managed)),
                    "rollback": "not-attempted",
                    "next_action": "fresh-reconcile-after-owner-review",
                },
            ) from exc
        observed = list(adapter.issue().labels)
        if set(observed) != expected:
            raise _failure(
                "readback_mismatch",
                "per-operation label readback differs from expected state",
                observed_labels=observed,
                expected_labels=sorted(expected),
                completed_operations=completed,
            )
        completed.append(f"{operation}:{label}")
    final_issue = adapter.issue()
    final_comments = adapter.comments()
    final_selected = _select_evidence(final_comments, selected_payload)
    if final_selected is None:
        raise _failure(
            "evidence_conflict",
            "final readback no longer contains the selected evidence payload",
        )
    if not evaluate_final(final_issue.labels, desired, before_issue.labels, mapping, 1):
        raise _failure(
            "readback_mismatch",
            "final status lifecycle predicate is false",
            observed_labels=list(final_issue.labels),
            desired_labels=sorted(desired),
            completed_operations=completed,
        )
    return {
        "kind": "success",
        "lifecycle": state,
        "observed_managed_before": sorted(set(before_issue.labels) & set(mapping.managed)),
        "observed_managed_after": sorted(set(final_issue.labels) & set(mapping.managed)),
        "added": [label for operation, label in operations if operation == "add"],
        "removed": [label for operation, label in operations if operation == "remove"],
        "completed_operations": completed,
        "evidence": evidence_comment_snapshot.as_dict(),
        "readback": final_issue.as_dict(),
        "code_owner": MODULE_OWNER,
        "responsibility_scope": LIFECYCLE_SCOPE,
    }


__all__ = [
    "CommentSnapshot",
    "GhStatusAdapter",
    "IssueSnapshot",
    "LabelMapping",
    "LifecycleFailure",
    "build_evidence_payload",
    "attempt_key",
    "operation_identity",
    "classify_lifecycle",
    "desired_labels",
    "evidence_comment",
    "evaluate_final",
    "load_label_mapping",
    "matching_comments",
    "mapping_from_data",
    "plan_operations",
    "reconcile_status",
    "validate_remote_catalog",
    "validate_evidence_inputs",
]
