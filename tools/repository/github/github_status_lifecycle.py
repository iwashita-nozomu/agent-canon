#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Reconciles Issue status labels using native GitHub comment identities and fresh label readback.
# upstream design ../../../agents/internal-routines/github-status-lifecycle.md owns lifecycle decisions and publication authority
# upstream implementation ../../../documents/operations/issue-label-taxonomy.toml owns canonical and legacy status labels
# upstream implementation ./github_publish.py owns single-attempt GitHub command transport
# downstream implementation ../../../tests/agent_tools/test_github_status_lifecycle.py tests reconciliation without remote writes
# @dependency-end
"""Publish ordinary evidence and reconcile only lifecycle-owned Issue labels.

A comment ID identifies the selected evidence. Neither private markers nor a
hash of a comment provide GitHub exclusion or compare-and-swap. Reads detect
observed drift; an unobserved ABA change remains outside this guarantee.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlsplit

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

from tools.repository.github.github_publish import (
    Runner,
    run_command,
    subprocess_runner,
)

MODULE_OWNER = "github_status_lifecycle.py"
LIFECYCLE_SCOPE = "status-label-lifecycle"
TRANSPORT_SCOPE = "github-api-transport"
REPO_RE = re.compile(r"^[^/\s]+/[^/\s]+$")


class LifecycleFailure(Exception):
    """A failed observation or mutation, with no implicit retry or rollback."""

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
        super().__init__(message)
        self.code = code
        self.message = message
        self.code_owner = code_owner
        self.responsibility_scope = responsibility_scope
        self.details = dict(details or {})
        self.next_action = next_action

    def as_dict(self) -> dict[str, object]:
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
        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True)


def _failure(
    code: str,
    message: str,
    *,
    scope: str = LIFECYCLE_SCOPE,
    **details: object,
) -> LifecycleFailure:
    return LifecycleFailure(code, message, responsibility_scope=scope, details=details)


@dataclass(frozen=True)
class LabelMapping:
    active: str
    ready_for_review: str
    needs_verification: str
    legacy_active: tuple[str, ...] = ()
    legacy_ready_for_review: tuple[str, ...] = ()
    legacy_needs_verification: tuple[str, ...] = ()

    @property
    def canonical(self) -> dict[str, str]:
        return {
            "active": self.active,
            "ready_for_review": self.ready_for_review,
            "needs_verification": self.needs_verification,
        }

    @property
    def legacy_aliases(self) -> dict[str, tuple[str, ...]]:
        return {
            "active": self.legacy_active,
            "ready_for_review": self.legacy_ready_for_review,
            "needs_verification": self.legacy_needs_verification,
        }

    @property
    def managed(self) -> frozenset[str]:
        return frozenset(self.canonical.values()).union(
            *self.legacy_aliases.values()
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "status_lifecycle": {
                **self.canonical,
                "legacy_aliases": {
                    key: list(values) for key, values in self.legacy_aliases.items()
                },
            }
        }

    def desired(self, lifecycle: str) -> frozenset[str]:
        states = {
            "active": frozenset({self.active}),
            "review-ready": frozenset({self.ready_for_review}),
            "review-ready-unverified": frozenset(
                {self.ready_for_review, self.needs_verification}
            ),
        }
        if lifecycle not in states:
            raise _failure("lifecycle_facts_incomplete", "unknown lifecycle state")
        return states[lifecycle]


def mapping_from_data(data: Mapping[str, object]) -> LabelMapping:
    """Read the existing taxonomy without a second label vocabulary."""
    table = data.get("status_lifecycle")
    keys = {"active", "ready_for_review", "needs_verification"}
    if not isinstance(table, Mapping) or set(table) - { *keys, "legacy_aliases" }:
        raise _failure("taxonomy_invalid", "invalid status_lifecycle table")
    canonical: dict[str, str] = {}
    for key in sorted(keys):
        value = table.get(key)
        if not isinstance(value, str) or not value.strip():
            raise _failure("taxonomy_invalid", "canonical label is missing", field=key)
        canonical[key] = value
    aliases = table.get("legacy_aliases", {})
    if not isinstance(aliases, Mapping) or set(aliases) - keys:
        raise _failure("taxonomy_invalid", "invalid legacy_aliases table")
    legacy: dict[str, tuple[str, ...]] = {}
    all_names = list(canonical.values())
    for key in sorted(keys):
        values = aliases.get(key, [])
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not value.strip() for value in values
        ):
            raise _failure("taxonomy_invalid", "invalid legacy label list", field=key)
        legacy[key] = tuple(values)
        all_names.extend(values)
    if len(all_names) != len(set(all_names)):
        raise _failure("taxonomy_invalid", "status labels overlap")
    return LabelMapping(
        **canonical,
        legacy_active=legacy["active"],
        legacy_ready_for_review=legacy["ready_for_review"],
        legacy_needs_verification=legacy["needs_verification"],
    )


def load_label_mapping(root: Path | None = None) -> LabelMapping:
    source = root if root is not None else Path(__file__).resolve().parents[3]
    path = source / "documents/operations/issue-label-taxonomy.toml"
    try:
        return mapping_from_data(tomllib.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise _failure("taxonomy_invalid", "label taxonomy could not be read") from exc


def validate_remote_catalog(
    mapping: LabelMapping, remote: Sequence[str]
) -> frozenset[str]:
    names = frozenset(remote)
    missing = set(mapping.canonical.values()) - names
    if missing:
        raise _failure("label_mapping_missing", "canonical labels are absent", missing=sorted(missing))
    return names


@dataclass(frozen=True)
class IssueSnapshot:
    number: int
    url: str
    state: str
    labels: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {"number": self.number, "url": self.url, "state": self.state, "labels": list(self.labels)}


@dataclass(frozen=True)
class CommentSnapshot:
    comment_id: int
    body: str
    url: str

    def as_dict(self) -> dict[str, object]:
        return {"id": self.comment_id, "body": self.body, "url": self.url}


def _positive_id(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise _failure("identity_invalid", f"{name} must be a positive integer")
    return value


class GhStatusAdapter:
    """Use native gh API arguments; every write is attempted once."""

    def __init__(self, repo: str, issue: int | str, *, runner: Runner = subprocess_runner) -> None:
        if not REPO_RE.fullmatch(repo) or "?" in repo or "#" in repo:
            raise _failure("identity_invalid", "repository must be owner/name")
        if isinstance(issue, str) and issue.isascii() and issue.isdecimal():
            issue = int(issue)
        self.issue_number = _positive_id(issue, "issue")
        self.repo = repo
        self.runner = runner
        self.issue_path = f"repos/{repo}/issues/{self.issue_number}"

    def _api_json(self, args: Sequence[str], *, mutation: bool = False) -> object:
        try:
            result = run_command(["gh", "api", *args], runner=self.runner)
            return json.loads(result.stdout)
        except Exception as exc:
            raise _failure(
                "mutation_partial" if mutation else "readback_unavailable",
                "GitHub response is unavailable; do not blindly retry a write",
                scope=TRANSPORT_SCOPE,
                operation=list(args[:3]),
            ) from exc

    def issue(self) -> IssueSnapshot:
        raw = self._api_json([self.issue_path])
        if not isinstance(raw, dict) or type(raw.get("number")) is not int or raw["number"] != self.issue_number:
            raise _failure("readback_invalid", "Issue identity does not match", scope=TRANSPORT_SCOPE)
        labels = raw.get("labels")
        if not isinstance(labels, list) or any(
            not isinstance(row, dict) or not isinstance(row.get("name"), str)
            or not row["name"] for row in labels
        ):
            raise _failure("readback_invalid", "invalid Issue labels", scope=TRANSPORT_SCOPE)
        names = tuple(sorted(row["name"] for row in labels))
        url, state = raw.get("html_url"), raw.get("state")
        if len(set(names)) != len(names) or not isinstance(url, str) or not url or state not in {"open", "closed"}:
            raise _failure("readback_invalid", "invalid Issue snapshot", scope=TRANSPORT_SCOPE)
        return IssueSnapshot(self.issue_number, url, state, names)

    def label_catalog(self) -> tuple[str, ...]:
        pages = self._api_json([
            "--paginate", "--slurp", f"repos/{self.repo}/labels?per_page=100"
        ])
        if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
            raise _failure("readback_invalid", "invalid label catalog pages", scope=TRANSPORT_SCOPE)
        names: list[str] = []
        for page in pages:
            for row in page:
                if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"]:
                    raise _failure("readback_invalid", "invalid catalog label", scope=TRANSPORT_SCOPE)
                names.append(row["name"])
        return tuple(names)

    def _comment_snapshot(self, raw: object, expected_id: int | None = None) -> CommentSnapshot:
        if not isinstance(raw, dict):
            raise _failure("evidence_readback_unavailable", "invalid comment response", scope=TRANSPORT_SCOPE)
        identity = _positive_id(raw.get("id"), "comment id")
        body, url, issue_url = raw.get("body"), raw.get("html_url"), raw.get("issue_url")
        if expected_id is not None and identity != expected_id:
            raise _failure("evidence_readback_mismatch", "comment id changed")
        if not all(isinstance(value, str) and value.strip() for value in (body, url, issue_url)):
            raise _failure("evidence_readback_unavailable", "comment fields are missing", scope=TRANSPORT_SCOPE)
        if urlsplit(issue_url).path.casefold() != f"/{self.issue_path}".casefold():
            raise _failure("evidence_readback_mismatch", "comment belongs to a different Issue")
        return CommentSnapshot(identity, body, url)

    def comment(self, comment_id: int) -> CommentSnapshot:
        identity = _positive_id(comment_id, "comment id")
        raw = self._api_json([f"repos/{self.repo}/issues/comments/{identity}"])
        return self._comment_snapshot(raw, identity)

    def create_comment(self, body: str) -> CommentSnapshot:
        raw = self._api_json([
            "--method", "POST", f"{self.issue_path}/comments", "-f", f"body={body}"
        ], mutation=True)
        created = self._comment_snapshot(raw)
        observed = self.comment(created.comment_id)
        if created != observed or observed.body != body:
            raise _failure("evidence_readback_mismatch", "created comment could not be read back unchanged", comment_id=created.comment_id)
        return observed

    def add_label(self, label: str) -> None:
        self._api_json([
            "--method", "POST", f"{self.issue_path}/labels", "-f", f"labels[]={label}"
        ], mutation=True)

    def remove_label(self, label: str) -> None:
        # DELETE returns an empty body, so successful transport needs no JSON parse.
        try:
            run_command([
                "gh", "api", "--method", "DELETE",
                f"{self.issue_path}/labels/{quote(label, safe='')}",
            ], runner=self.runner)
        except Exception as exc:
            raise _failure("mutation_partial", "label removal response unavailable", scope=TRANSPORT_SCOPE) from exc


def classify_lifecycle(facts: Mapping[str, object]) -> str:
    """Classify work, not the syntax of its human-readable evidence."""
    if facts.get("work_started") is not True:
        raise _failure("lifecycle_facts_incomplete", "work has not started")
    for field in ("implementation_failure", "validation_failed"):
        if facts.get(field, False) is True:
            return "active"
        if type(facts.get(field, False)) is not bool:
            raise _failure("lifecycle_facts_incomplete", "invalid lifecycle fact", field=field)
    for field in ("handoff_ready", "validation_complete", "verification_unavailable"):
        if type(facts.get(field, False)) is not bool:
            raise _failure("lifecycle_facts_incomplete", "invalid lifecycle fact", field=field)
    if not facts.get("handoff_ready", False) or not facts.get("validation_complete", False):
        return "active"
    return "review-ready-unverified" if facts.get("verification_unavailable", False) else "review-ready"


def desired_labels(lifecycle: str, mapping: LabelMapping) -> frozenset[str]:
    return mapping.desired(lifecycle)


def plan_operations(
    before: Sequence[str], desired: frozenset[str], mapping: LabelMapping
) -> tuple[tuple[str, str], ...]:
    labels = set(before)
    removals = tuple(("remove", name) for name in sorted((labels & mapping.managed) - desired))
    additions = tuple(("add", name) for name in mapping.canonical.values() if name in desired - labels)
    return removals + additions


def evaluate_final(
    observed: Sequence[str], desired: frozenset[str], initial: Sequence[str], mapping: LabelMapping
) -> bool:
    labels = set(observed)
    return labels & mapping.managed == desired and labels - mapping.managed == set(initial) - mapping.managed


def reconcile_status(
    adapter: GhStatusAdapter,
    *,
    mapping: LabelMapping,
    facts: Mapping[str, object],
    comment_body: str | None = None,
    comment_id: int | None = None,
) -> dict[str, object]:
    """Reconcile after one ordinary comment or one explicitly selected existing ID.

    The caller owns authorization and the content's adequacy. Evidence describes
    source/branch/PR when present, validation, and remaining work in ordinary
    Markdown. This adapter neither requires a PR nor infers authority from prose.
    """
    if (comment_body is None) == (comment_id is None):
        raise _failure("evidence_missing", "supply either comment_body or an existing comment_id")
    if comment_body is not None and (not isinstance(comment_body, str) or not comment_body.strip()):
        raise _failure("evidence_missing", "comment_body must be non-empty")
    if comment_id is not None:
        _positive_id(comment_id, "comment id")
    lifecycle = classify_lifecycle(facts)
    desired = mapping.desired(lifecycle)
    validate_remote_catalog(mapping, adapter.label_catalog())
    before = adapter.issue()
    evidence = adapter.comment(comment_id) if comment_id is not None else adapter.create_comment(comment_body)
    expected = set(before.labels)
    operations = plan_operations(before.labels, desired, mapping)
    completed: list[dict[str, str]] = []
    for action, label in operations:
        observed = adapter.issue()
        if set(observed.labels) != expected:
            raise _failure("fresh_state_changed", "labels changed before mutation", completed_prefix=completed, observed_labels=list(observed.labels), comment_id=evidence.comment_id)
        try:
            if action == "remove":
                adapter.remove_label(label)
            else:
                adapter.add_label(label)
        except LifecycleFailure as exc:
            try:
                observed_labels: list[str] | None = list(adapter.issue().labels)
            except LifecycleFailure:
                observed_labels = None
            raise _failure(
                "mutation_partial", "mutation result requires fresh owner review",
                completed_prefix=completed, failed_operation={"action": action, "label": label},
                observed_labels=observed_labels, desired_labels=sorted(desired),
                comment_id=evidence.comment_id, cause=exc.as_dict(), rollback="not-attempted",
            ) from exc
        if action == "remove":
            expected.remove(label)
        else:
            expected.add(label)
        observed = adapter.issue()
        if set(observed.labels) != expected:
            raise _failure("readback_mismatch", "labels differ after mutation", completed_prefix=completed, last_operation={"action": action, "label": label}, observed_labels=list(observed.labels), comment_id=evidence.comment_id)
        completed.append({"action": action, "label": label})
    final = adapter.issue()
    selected = adapter.comment(evidence.comment_id)
    if selected != evidence:
        raise _failure("evidence_readback_mismatch", "selected evidence changed", comment_id=evidence.comment_id, completed_prefix=completed)
    if not evaluate_final(final.labels, desired, before.labels, mapping):
        raise _failure("readback_mismatch", "final labels differ from intended state", observed_labels=list(final.labels), completed_prefix=completed)
    return {
        "kind": "success", "lifecycle": lifecycle,
        "before_managed": sorted(set(before.labels) & mapping.managed),
        "after_managed": sorted(set(final.labels) & mapping.managed),
        "labels_added": [item["label"] for item in completed if item["action"] == "add"],
        "labels_removed": [item["label"] for item in completed if item["action"] == "remove"],
        "completed_operations": completed, "evidence": evidence.as_dict(),
        "readback": final.as_dict(), "code_owner": MODULE_OWNER,
        "responsibility_scope": LIFECYCLE_SCOPE,
    }
