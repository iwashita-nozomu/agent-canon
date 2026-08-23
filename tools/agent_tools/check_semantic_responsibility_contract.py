#!/usr/bin/env python3
"""Validate semantic responsibility contract schema, identity, and references."""

# @dependency-start
# contract tool
# responsibility Validates semantic responsibility contract instance shape, identity, and references.
# upstream design ../../documents/design/semantic-responsibility-contract.md canonical contract
# upstream design ../../templates/documents/semantic-responsibility-contract.template.toml reusable instance shape
# downstream implementation ../../tests/agent_tools/test_check_semantic_responsibility_contract.py focused validator tests
# downstream design ../../documents/tools/check_semantic_responsibility_contract.md reader-facing tool documentation
# @dependency-end

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - supported Python versions include tomllib
    tomllib = None  # type: ignore[assignment]


SCHEMA = "agent-canon.semantic_responsibility_contract.v1"
POLICY_PATH = "documents/design/semantic-responsibility-contract.md"
TEMPLATE_PATH = "templates/documents/semantic-responsibility-contract.template.toml"
ALLOWED_ACTIONS = {"reuse", "extend", "replace", "introduce"}
OWNER_KINDS = {
    "compiler",
    "static_checker",
    "design_review",
    "existing_test",
    "test_extension",
    "new_test",
    "experiment",
    "formal_proof",
}
HARD_EDGES = (
    "invariant",
    "atomic_transition",
    "transaction",
    "lifecycle",
    "effect",
    "consistency",
    "substitutability",
)
ROOT_FIELDS = {
    "schema",
    "instance_kind",
    "policy_ref",
    "active_design_packet_ref",
    "run_id",
    "task_id",
    "responsibility_id",
    "allocation_phase",
    "test_designer_activation",
    "hard_edge_kinds",
    "semantic_grouping",
    "structural_mandates",
    "semantic_delta",
}
DELTA_FIELDS = {"id", "summary", "implementation_action", "design_refs", "obligation"}
OBLIGATION_FIELDS = {
    "id",
    "claim",
    "verification_owner_kind",
    "verification_owner",
    "primary_verification_ref",
    "contract_ref",
    "changed_mechanism_ref",
    "observable_assertion",
    "decidable_oracle",
    "removal_witness",
    "supporting_evidence",
}
SUPPORTING_FIELDS = {"property", "role", "owner_kind", "reference"}
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
REFERENCE = re.compile(r"(?:repo|artifact):[^\s#]+(?:#[^\s]+)?\Z")


class ContractError(ValueError):
    """One fail-closed contract finding."""


def _require_text(value: Any, field: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ContractError(f"{field}:required_text")
    return value


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractError(f"{field}:required_list")
    return value


def _check_unknown(mapping: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(mapping).difference(allowed))
    if unknown:
        raise ContractError(f"{field}:unknown_fields:{','.join(unknown)}")


def _check_identifier(value: Any, field: str, *, empty: bool = False) -> str:
    text = _require_text(value, field, empty=empty)
    if text and IDENTIFIER.fullmatch(text) is None:
        raise ContractError(f"{field}:invalid_identifier")
    return text


def _check_reference(
    value: Any,
    field: str,
    *,
    root: Path,
    instance_path: Path,
    required: bool,
    artifact_root: Path | None = None,
) -> str:
    text = _require_text(value, field, empty=not required)
    if not text:
        return text
    if REFERENCE.fullmatch(text) is None:
        raise ContractError(f"{field}:invalid_reference")
    prefix, target = text.split(":", 1)
    target_path = target.split("#", 1)[0]
    relative = Path(target_path)
    if relative.is_absolute() or ".." in relative.parts or not target_path:
        raise ContractError(f"{field}:unsafe_reference")
    base = root if prefix == "repo" else (artifact_root or instance_path.parent)
    unresolved = base / relative
    if unresolved.is_symlink():
        raise ContractError(f"{field}:symlink_reference")
    candidate = unresolved.resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError as exc:
        raise ContractError(f"{field}:outside_reference_root") from exc
    if not candidate.is_file() or candidate.is_symlink():
        raise ContractError(f"{field}:missing_reference:{target_path}")
    return text


def _check_supporting_evidence(
    value: Any,
    field: str,
    *,
    root: Path,
    instance_path: Path,
    artifact_root: Path | None,
    primary_property: str,
    primary_role: str,
) -> None:
    entries = _require_list(value, field)
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(entries):
        entry_field = f"{field}[{index}]"
        if not isinstance(raw, dict):
            raise ContractError(f"{entry_field}:required_table")
        _check_unknown(raw, SUPPORTING_FIELDS, entry_field)
        property_name = _require_text(raw.get("property"), f"{entry_field}.property")
        role = _require_text(raw.get("role"), f"{entry_field}.role")
        owner_kind = _require_text(raw.get("owner_kind"), f"{entry_field}.owner_kind")
        if owner_kind not in OWNER_KINDS:
            raise ContractError(f"{entry_field}.owner_kind:unknown_owner_kind")
        if property_name == primary_property and role == primary_role:
            raise ContractError(f"{entry_field}:duplicates_primary_property_role")
        key = (property_name, role)
        if key in seen:
            raise ContractError(f"{entry_field}:duplicate_property_role")
        seen.add(key)
        _check_reference(
            raw.get("reference"),
            f"{entry_field}.reference",
            root=root,
            instance_path=instance_path,
            required=True,
            artifact_root=artifact_root,
        )


def _check_obligation(
    raw: Any,
    field: str,
    *,
    root: Path,
    instance_path: Path,
    template: bool,
    artifact_root: Path | None,
) -> None:
    if not isinstance(raw, dict):
        raise ContractError(f"{field}:required_table")
    _check_unknown(raw, OBLIGATION_FIELDS, field)
    if template and not raw.get("id"):
        for name in OBLIGATION_FIELDS:
            if name == "supporting_evidence":
                if raw.get(name) != []:
                    raise ContractError(f"{field}.{name}:template_must_be_empty")
            elif raw.get(name, "") not in ("", None):
                raise ContractError(f"{field}.{name}:template_must_be_empty")
        return
    _check_identifier(raw.get("id"), f"{field}.id")
    _require_text(raw.get("claim"), f"{field}.claim")
    owner_kind = _require_text(raw.get("verification_owner_kind"), f"{field}.verification_owner_kind")
    if owner_kind not in OWNER_KINDS:
        raise ContractError(f"{field}.verification_owner_kind:unknown_owner_kind")
    owner = _require_text(raw.get("verification_owner"), f"{field}.verification_owner")
    _check_reference(
        raw.get("primary_verification_ref"),
        f"{field}.primary_verification_ref",
        root=root,
        instance_path=instance_path,
        required=True,
        artifact_root=artifact_root,
    )
    for name in ("contract_ref", "changed_mechanism_ref", "removal_witness"):
        _check_reference(
            raw.get(name),
            f"{field}.{name}",
            root=root,
            instance_path=instance_path,
            required=owner_kind == "existing_test",
            artifact_root=artifact_root,
        )
    for name in ("observable_assertion", "decidable_oracle"):
        _require_text(raw.get(name), f"{field}.{name}", empty=owner_kind != "existing_test")
    if owner_kind == "existing_test":
        _require_text(raw.get("contract_ref"), f"{field}.contract_ref")
        _require_text(raw.get("changed_mechanism_ref"), f"{field}.changed_mechanism_ref")
        _require_text(raw.get("removal_witness"), f"{field}.removal_witness")
        _require_text(raw.get("observable_assertion"), f"{field}.observable_assertion")
        _require_text(raw.get("decidable_oracle"), f"{field}.decidable_oracle")
    _check_supporting_evidence(
        raw.get("supporting_evidence"),
        f"{field}.supporting_evidence",
        root=root,
        instance_path=instance_path,
        artifact_root=artifact_root,
        primary_property=raw["claim"],
        primary_role=owner,
    )


def _check_delta(
    raw: Any,
    field: str,
    *,
    root: Path,
    instance_path: Path,
    template: bool,
    artifact_root: Path | None,
) -> None:
    if not isinstance(raw, dict):
        raise ContractError(f"{field}:required_table")
    _check_unknown(raw, DELTA_FIELDS, field)
    if template:
        for name in ("id", "summary", "implementation_action"):
            if raw.get(name, "") not in ("", None):
                raise ContractError(f"{field}.{name}:template_must_be_empty")
        if raw.get("design_refs") != []:
            raise ContractError(f"{field}.design_refs:template_must_be_empty")
        obligations = _require_list(raw.get("obligation"), f"{field}.obligation")
        if len(obligations) != 1:
            raise ContractError(f"{field}.obligation:template_shape_requires_placeholder")
        _check_obligation(
            obligations[0],
            f"{field}.obligation[0]",
            root=root,
            instance_path=instance_path,
            template=True,
            artifact_root=artifact_root,
        )
        return
    _check_identifier(raw.get("id"), f"{field}.id")
    _require_text(raw.get("summary"), f"{field}.summary")
    action = _require_text(raw.get("implementation_action"), f"{field}.implementation_action")
    if action not in ALLOWED_ACTIONS:
        raise ContractError(f"{field}.implementation_action:unknown_action")
    refs = _require_list(raw.get("design_refs"), f"{field}.design_refs")
    if not refs:
        raise ContractError(f"{field}.design_refs:empty")
    for index, reference in enumerate(refs):
        _check_reference(
            reference,
            f"{field}.design_refs[{index}]",
            root=root,
            instance_path=instance_path,
            required=True,
            artifact_root=artifact_root,
        )
    obligations = _require_list(raw.get("obligation"), f"{field}.obligation")
    if not obligations:
        raise ContractError(f"{field}.obligation:empty")
    obligation_ids: set[str] = set()
    for index, obligation in enumerate(obligations):
        obligation_field = f"{field}.obligation[{index}]"
        _check_obligation(
            obligation,
            obligation_field,
            root=root,
            instance_path=instance_path,
            template=False,
            artifact_root=artifact_root,
        )
        identifier = obligation["id"]
        if identifier in obligation_ids:
            raise ContractError(f"{obligation_field}.id:duplicate")
        obligation_ids.add(identifier)


def validate_document(
    path: Path,
    *,
    root: Path,
    template: bool,
    artifact_root: Path | None = None,
) -> list[str]:
    """Validate one TOML contract document and return its identity record."""
    if tomllib is None:  # pragma: no cover
        raise ContractError("python:tomllib_unavailable")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ContractError(f"{path}:toml_invalid:{exc}") from exc
    if not isinstance(data, dict):
        raise ContractError(f"{path}:root_must_be_table")
    _check_unknown(data, ROOT_FIELDS, "root")
    if data.get("schema") != SCHEMA:
        raise ContractError("root.schema:invalid")
    expected_kind = "template" if template else "task"
    if data.get("instance_kind") != expected_kind:
        raise ContractError(f"root.instance_kind:expected_{expected_kind}")
    policy_ref = data.get("policy_ref")
    if template:
        if policy_ref != POLICY_PATH:
            raise ContractError("root.policy_ref:invalid_template_policy")
    else:
        _check_reference(
            policy_ref,
            "root.policy_ref",
            root=root,
            instance_path=path,
            required=True,
            artifact_root=artifact_root,
        )
        if not str(policy_ref).split("#", 1)[0].endswith(POLICY_PATH):
            raise ContractError("root.policy_ref:not_semantic_responsibility_policy")
    for name in ("allocation_phase", "test_designer_activation"):
        if data.get(name) not in (
            "pre_implementation" if name == "allocation_phase" else "post_implementation_unresolved_test_owned_runtime_risk",
        ):
            raise ContractError(f"root.{name}:invalid")
    edges = _require_list(data.get("hard_edge_kinds"), "root.hard_edge_kinds")
    if tuple(edges) != HARD_EDGES or len(set(edges)) != len(edges):
        raise ContractError("root.hard_edge_kinds:invalid")
    mandates = _require_list(data.get("structural_mandates"), "root.structural_mandates")
    if mandates:
        raise ContractError("root.structural_mandates:must_be_empty")
    if template:
        for name in ("active_design_packet_ref", "run_id", "task_id", "responsibility_id", "semantic_grouping"):
            if data.get(name) != "":
                raise ContractError(f"root.{name}:template_must_be_empty")
    else:
        for name in ("run_id", "task_id", "responsibility_id", "semantic_grouping"):
            _require_text(data.get(name), f"root.{name}")
        _check_reference(
            data.get("active_design_packet_ref"),
            "root.active_design_packet_ref",
            root=root,
            instance_path=path,
            required=True,
            artifact_root=artifact_root,
        )
    deltas = _require_list(data.get("semantic_delta"), "root.semantic_delta")
    if template:
        if len(deltas) != 1:
            raise ContractError("root.semantic_delta:template_shape_requires_placeholder")
    elif not deltas:
        raise ContractError("root.semantic_delta:empty")
    delta_ids: set[str] = set()
    for index, delta in enumerate(deltas):
        delta_field = f"root.semantic_delta[{index}]"
        _check_delta(
            delta,
            delta_field,
            root=root,
            instance_path=path,
            template=template,
            artifact_root=artifact_root,
        )
        if delta.get("id"):
            if delta["id"] in delta_ids:
                raise ContractError(f"{delta_field}.id:duplicate")
            delta_ids.add(delta["id"])
    return [f"schema={SCHEMA}", f"instance_kind={expected_kind}", f"path={path}"]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--template", action="append", type=Path, default=[])
    parser.add_argument("--instance", action="append", type=Path, default=[])
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Validate selected template and populated contract documents."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    root = args.root.resolve()
    templates = list(args.template)
    instances = list(args.instance)
    for path in args.paths:
        (templates if path.name == Path(TEMPLATE_PATH).name else instances).append(path)
    if not templates:
        templates = [root / TEMPLATE_PATH]
    documents = [(path, True) for path in templates] + [(path, False) for path in instances]
    if not documents:
        print("SEMANTIC_RESPONSIBILITY_CONTRACT=fail", file=sys.stderr)
        print("no contract documents supplied", file=sys.stderr)
        return 2
    results: list[dict[str, Any]] = []
    failures: list[str] = []
    for raw_path, is_template in documents:
        path = raw_path if raw_path.is_absolute() else (Path.cwd() / raw_path)
        try:
            record = validate_document(
                path.resolve(),
                root=root,
                template=is_template,
                artifact_root=args.artifact_root.resolve() if args.artifact_root else None,
            )
        except ContractError as exc:
            failures.append(str(exc))
        else:
            results.append({"path": str(path.resolve()), "template": is_template, "identity": record})
    if args.format == "json":
        print(json.dumps({"status": "fail" if failures else "pass", "results": results, "errors": failures}, ensure_ascii=False, indent=2))
    else:
        for result in results:
            print(f"SEMANTIC_RESPONSIBILITY_CONTRACT_FILE={result['path']}")
        if failures:
            print("SEMANTIC_RESPONSIBILITY_CONTRACT=fail", file=sys.stderr)
            for failure in failures:
                print(f"SEMANTIC_RESPONSIBILITY_CONTRACT_ERROR={failure}", file=sys.stderr)
        else:
            print("SEMANTIC_RESPONSIBILITY_CONTRACT=pass")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
