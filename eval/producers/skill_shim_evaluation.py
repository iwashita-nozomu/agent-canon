#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Produces route golden, fresh packet, and deterministic shim measurement artifacts.
# upstream design ../../documents/design/skill-runtime-shim-materialization.md approved shim evaluation contract
# upstream implementation ./route.py owns route behavior and JSON schema
# upstream implementation ./evaluate_workflow_selection.py owns the frozen 525-case manifest loader
# upstream implementation ./skill_shim_materializer.py owns generated shim records and content
# upstream implementation ./runtime_artifacts.py owns external runtime receipt publication
# downstream implementation ../../tests/agent_tools/test_skill_shim_evaluation.py focused producer tests
# @dependency-end
"""Produce route goldens, answer-free packet receipts, and shim measurements."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, cast

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ is the supported runtime.
    import tomli as tomllib  # type: ignore[no-redef]

from eval.producers.evaluate_workflow_selection import load_manifest
from tools.agent.skills.skill_shim_materializer import (  # pyright: ignore[reportMissingTypeStubs]
    BuildContext,
    build_context,
    build_record,
    render_shim,
)

try:
    from .runtime_artifacts import RuntimeArtifactBoundary, RuntimeArtifactError
except ImportError:
    from tools.runtime.artifacts.runtime_artifacts import RuntimeArtifactBoundary, RuntimeArtifactError  # type: ignore[no-redef]

SCHEMA_ROUTE = "agent_canon.route_golden_case.v1"
SCHEMA_PACKETS = "agent_canon.skill_runtime_shim.fresh_packets"
SCHEMA_MEASUREMENT = "agent_canon.skill_runtime_shim.measurement"
MODEL_ID = "gpt-5.4-mini"
HOST_PROFILE = "medium"
NORMALIZATION = "utf8-nfc-lf-final-newline"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
ROUTE_SCHEMA = "agent_canon.route.skill_route.v1"
PACKET_CLASSES = ("full", "changed")
VARIANTS = ("current", "generated")
SCENARIO_CATEGORIES = (
    "discovery-selection",
    "boundary-and-negative",
    "toolcall-route",
    "dependent-skill-ordering",
    "parent-subagent-instruction",
    "failure-argparse-normalization",
)
HOST_OBSERVATION_SCHEMA = "agent_canon.skill_runtime_shim.host_observation"


def _runtime_boundary(
    root: Path, runtime_root: Path | str | None = None
) -> RuntimeArtifactBoundary:
    """Resolve the explicit external runtime artifact capability.

    Evaluation producers never publish into the AgentCanon checkout.  A
    caller may pass the root directly or provide the same explicit runtime
    capability used by the bootstrap service; there is no source-tree or
    parent-temporary fallback.
    """
    configured = runtime_root or os.environ.get("AGENT_CANON_RUNTIME_ROOT", "").strip()
    if not configured:
        raise ProducerError("runtime_root_required")
    try:
        return RuntimeArtifactBoundary.for_source(root, configured, create=True)
    except RuntimeArtifactError as exc:
        raise ProducerError(f"runtime_artifact_boundary:{exc}") from exc


def _runtime_write(
    boundary: RuntimeArtifactBoundary, path: Path, data: bytes, purpose: str
) -> None:
    """Publish one producer result through the external runtime boundary."""
    try:
        boundary.atomic_write_bytes(path, data)
    except RuntimeArtifactError as exc:
        raise ProducerError(f"{purpose}:{exc}") from exc


class WorkflowSelectionCase(Protocol):
    """Typed projection of one imported route manifest case."""

    case_id: str
    prompt: str


class WorkflowSelectionManifest(Protocol):
    """Typed projection of the imported route manifest document."""

    expected_case_count: int
    expected_generated_case_count: int
    cases: Sequence[WorkflowSelectionCase]


def _expected_skill_id_from_targets(targets: Sequence[str], packet_id: str) -> str:
    """Extract one canonical target skill id from manifest target files."""
    values: list[str] = []
    for target in targets:
        if target.startswith("agents/skills/") and target.endswith(".md"):
            values.append(Path(target).stem)
        elif target.startswith(".codex/personal/skills/") and target.endswith("/SKILL.md"):
            values.append(Path(target).parent.name)
    if not values:
        raise ProducerError(f"packet_target_skill_id:{packet_id}")
    if len(set(values)) != 1:
        raise ProducerError(f"packet_target_skill_id_ambiguous:{packet_id}")
    return values[0]


def _prompt_under_test(content: str, packet_id: str) -> str:
    """Extract the prompt body for a packet from its Prompt Under Test section."""
    lines = content.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == "## Prompt Under Test":
            start = index + 1
            break
    if start is None:
        raise ProducerError(f"packet_prompt_section_missing:{packet_id}")
    body: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        body.append(line)
    prompt_body = "\n".join(body).strip()
    if not prompt_body:
        raise ProducerError(f"packet_prompt_empty:{packet_id}")
    return normalize_text(prompt_body)


class ProducerError(ValueError):
    """Raised when an evaluation input or observed process result is unmapped."""


def canonical_json_bytes(value: object) -> bytes:
    """Serialize a JSON value using the producer's compact canonical form."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    """Return a SHA-256 hex digest."""
    return hashlib.sha256(value).hexdigest()


def normalize_text(value: str) -> str:
    """Normalize text to NFC, LF, and one final newline."""
    normalized = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    return normalized.rstrip("\n") + "\n"


def deterministic_measure(value: str) -> tuple[int, int, bytes]:
    """Measure normalized UTF-8 bytes and Unicode scalar count."""
    normalized = normalize_text(value)
    encoded = normalized.encode("utf-8")
    return len(encoded), len(normalized), encoded


def _empty_route(mode: str) -> dict[str, object]:
    """Return the fixed route projection used for a failed subprocess case."""
    return {
        "schema": ROUTE_SCHEMA,
        "route": "",
        "mode": mode,
        "skills": [],
        "active_skills": [],
        "deferred_skills": [],
        "matched_skills": [],
        "related_skill_candidates": [],
        "related_skills": {},
        "reasons": [],
        "visualization_owner_skill": None,
        "visualization_tool_call": None,
        "visualization_adapter_tool_call": None,
        "visualization_rejection": None,
        "evidence": "",
    }


def normalize_route_result(
    completed: subprocess.CompletedProcess[bytes],
    *,
    mode: str,
) -> tuple[str, Mapping[str, object], Mapping[str, object]]:
    """Map only the approved route CLI results into a golden row."""
    stderr = completed.stderr or b""
    stderr_text = stderr.decode("utf-8", errors="replace")
    if completed.returncode == 0:
        try:
            route_value: object = json.loads(
                (completed.stdout or b"").decode("utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProducerError("UNMAPPED_ROUTE_FAILURE:invalid_success_json") from exc
        if not isinstance(route_value, dict):
            raise ProducerError("UNMAPPED_ROUTE_FAILURE:invalid_success_schema")
        route = cast(dict[str, object], route_value)
        if route.get("schema") != ROUTE_SCHEMA:
            raise ProducerError("UNMAPPED_ROUTE_FAILURE:invalid_success_schema")
        if stderr:
            raise ProducerError("UNMAPPED_ROUTE_FAILURE:success_stderr")
        failure = {
            "code": "none",
            "class": "none",
            "exit_code": 0,
            "stderr_sha256": EMPTY_SHA256,
        }
        return "pass", route, failure
    non_empty = [line.strip() for line in stderr_text.splitlines() if line.strip()]
    if (
        completed.returncode == 2
        and non_empty
        and non_empty[0].startswith("usage:")
        and any(line.startswith("error:") or " error:" in line for line in non_empty)
    ):
        failure = {
            "code": "ARGUMENT_ERROR",
            "class": "argument",
            "exit_code": 2,
            "stderr_sha256": sha256_bytes(stderr),
        }
        return "fail", _empty_route(mode), failure
    if completed.returncode == 2:
        if any(line.startswith("ROUTE_SOURCE_ROOT_FAILURE=") for line in non_empty):
            code, failure_class = "ROUTE_SOURCE_ROOT_FAILURE", "source_root"
        elif any(line.startswith("SKILL_ROUTER_ERROR=") for line in non_empty):
            code, failure_class = "SKILL_ROUTER_ERROR", "runtime"
        else:
            raise ProducerError("UNMAPPED_ROUTE_FAILURE:unknown_exit_2")
        failure = {
            "code": code,
            "class": failure_class,
            "exit_code": 2,
            "stderr_sha256": sha256_bytes(stderr),
        }
        return "fail", _empty_route(mode), failure
    raise ProducerError(f"UNMAPPED_ROUTE_FAILURE:exit_{completed.returncode}")


def route_golden(
    root: Path,
    manifest: Path,
    route_cli: Path,
    output: Path,
    runtime_root: Path | str | None = None,
) -> Mapping[str, object]:
    """Run the real route CLI for every frozen manifest case."""
    manifest_data = cast(WorkflowSelectionManifest, load_manifest(manifest))
    if manifest_data.expected_case_count != 525 or manifest_data.expected_generated_case_count != 525:
        raise ProducerError("route_manifest_count_mismatch")
    if len(manifest_data.cases) != 525:
        raise ProducerError("route_case_count_mismatch")
    rows: list[dict[str, object]] = []
    boundary = _runtime_boundary(root, runtime_root)
    temp_parent = boundary.ensure_directory("tmp")
    prompt_root = Path(
        tempfile.mkdtemp(prefix="skill-shim-route-", dir=str(temp_parent))
    )
    # Validate the freshly-created staging directory before any prompt is
    # written.  This keeps the receipt boundary explicit even if a hostile
    # filesystem replaces a component between creation and use.
    prompt_root = boundary.resolve(prompt_root)
    primary_error: BaseException | None = None
    try:
        for case in manifest_data.cases:
            prompt_path = prompt_root / f"{case.case_id}.txt"
            _runtime_write(
                boundary,
                prompt_path,
                case.prompt.encode("utf-8"),
                "skill-shim-route-prompt",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(route_cli.resolve()),
                    "--root",
                    str(root.resolve()),
                    "--prompt-file",
                    str(prompt_path),
                    "--mode",
                    "repo-changing",
                    "--format",
                    "json",
                ],
                cwd=root,
                capture_output=True,
                check=False,
            )
            status, route, failure = normalize_route_result(completed, mode="repo-changing")
            rows.append(
                {
                    "schema": SCHEMA_ROUTE,
                    "case_id": case.case_id,
                    "prompt_sha256": sha256_bytes(case.prompt.encode("utf-8")),
                    "invocation": {
                        "cli": "tools/agent/orchestration/route.py",
                        "mode": "repo-changing",
                        "format": "json",
                    },
                    "status": status,
                    "normalized_route_json_digest": sha256_bytes(canonical_json_bytes(route)),
                    "route": route,
                    "failure": failure,
                }
            )
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        try:
            # prompt_root is a fresh, receipt-bound directory beneath the
            # external runtime root; remove exactly that directory after the
            # subprocess wave and never touch the source checkout.
            if not prompt_root.is_relative_to(boundary.root):
                raise ProducerError("skill-shim-route_cleanup_escape")
            shutil.rmtree(prompt_root)
        except (OSError, ProducerError) as cleanup_error:
            if primary_error is not None:
                raise cleanup_error from primary_error
            raise
    payload = {
        "schema": "agent_canon.route_golden",
        "version": 1,
        "case_count": len(rows),
        "cases": rows,
    }
    _runtime_write(
        boundary,
        output,
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        "skill-shim-route-golden",
    )
    return cast(Mapping[str, object], payload)


def _packet_manifest(path: Path) -> tuple[Mapping[str, object], list[Mapping[str, object]]]:
    """Load and validate the answer-free fresh packet manifest."""
    raw = cast(
        Mapping[str, object],
        tomllib.loads(path.read_text(encoding="utf-8")),
    )
    if set(raw) != {"catalog_kind", "version", "packet_class_order", "packet"}:
        raise ProducerError("packet_manifest_unknown_field")
    if raw.get("catalog_kind") != "agent_canon_skill_runtime_shim_eval" or raw.get("version") != 1:
        raise ProducerError("packet_manifest_identity")
    if raw.get("packet_class_order") != list(PACKET_CLASSES):
        raise ProducerError("packet_class_order")
    packets_value = raw.get("packet")
    if not isinstance(packets_value, list):
        raise ProducerError("packet_count")
    packets = cast(list[object], packets_value)
    if len(packets) != len(SCENARIO_CATEGORIES):
        raise ProducerError("packet_count")
    required = {
        "id", "packet_class", "prompt_path", "canonical_target_files", "prompt_dependency_files",
        "scenario_id", "category", "target_skill_id", "iteration_ids", "prompt_digest",
        "method", "requirements", "report_grammar", "packet_digest",
    }
    rows: list[Mapping[str, object]] = []
    for item in packets:
        if not isinstance(item, Mapping):
            raise ProducerError("packet_manifest_packet_fields")
        row = cast(Mapping[str, object], item)
        if set(row) != required:
            raise ProducerError("packet_manifest_packet_fields")
        packet_path = (path.parent.parent.parent / str(row["prompt_path"])).resolve()
        if not packet_path.is_file():
            raise ProducerError(f"missing_packet:{row['id']}")
        content = packet_path.read_text(encoding="utf-8")
        lowered = content.lower()
        if any(token in lowered for token in ("expected_answer", "expected command", "oracle_", "prior reasoning")):
            raise ProducerError(f"answer_in_packet:{row['id']}")
        if sha256_bytes(content.encode("utf-8")) != row["packet_digest"]:
            raise ProducerError(f"packet_digest_mismatch:{row['id']}")
        if row["packet_class"] not in PACKET_CLASSES:
            raise ProducerError(f"packet_class:{row['id']}")
        if row["scenario_id"] != row["category"] or row["category"] not in SCENARIO_CATEGORIES:
            raise ProducerError(f"packet_category:{row['id']}")
        packet_prompt = _prompt_under_test(content, cast(str, row["id"]))
        prompt_digest = sha256_bytes(packet_prompt.encode("utf-8"))
        if row["prompt_digest"] != prompt_digest:
            raise ProducerError(f"packet_prompt_digest_mismatch:{row['id']}")
        target_files_value = row["canonical_target_files"]
        if not isinstance(target_files_value, list):
            raise ProducerError(f"packet_target_files:{row['id']}")
        target_file_items = cast(list[object], target_files_value)
        if not all(isinstance(target, str) for target in target_file_items):
            raise ProducerError(f"packet_target_files:{row['id']}")
        target_files = cast(list[str], target_file_items)
        target_skill_id = row["target_skill_id"]
        if (
            not isinstance(target_skill_id, str)
            or _expected_skill_id_from_targets(target_files, cast(str, row["id"]))
            != target_skill_id
        ):
            raise ProducerError(f"packet_target_skill_id_mismatch:{row['id']}")
        iteration_ids_value = row["iteration_ids"]
        if not isinstance(iteration_ids_value, Mapping):
            raise ProducerError(f"packet_iteration_ids:{row['id']}")
        iteration_ids = cast(Mapping[str, object], iteration_ids_value)
        if (
            set(iteration_ids) != set(VARIANTS)
            or not all(isinstance(value, str) and value for value in iteration_ids.values())
            or len(set(iteration_ids.values())) != len(VARIANTS)
        ):
            raise ProducerError(f"packet_iteration_ids:{row['id']}")
        rows.append(
            {
                "id": row["id"],
                "scenario_id": row["scenario_id"],
                "category": row["category"],
                "packet_class": row["packet_class"],
                "packet_prompt": packet_prompt,
                "packet_prompt_sha256": prompt_digest,
                "prompt_path": str(row["prompt_path"]),
                "canonical_target_files": target_files,
                "prompt_dependency_files": row["prompt_dependency_files"],
                "target_skill_id": target_skill_id,
                "iteration_ids": dict(iteration_ids),
                "method": row["method"],
                "requirements": row["requirements"],
                "report_grammar": row["report_grammar"],
                "packet_digest": row["packet_digest"],
            }
        )
    if {str(row["packet_class"]) for row in rows} != set(PACKET_CLASSES):
        raise ProducerError("packet_class_coverage")
    if {str(row["scenario_id"]) for row in rows} != set(SCENARIO_CATEGORIES):
        raise ProducerError("packet_scenario_coverage")
    if len({str(row["id"]) for row in rows}) != len(rows):
        raise ProducerError("packet_id_duplicate")
    if len({str(row["scenario_id"]) for row in rows}) != len(rows):
        raise ProducerError("packet_scenario_duplicate")
    return raw, rows


def packet_receipt(
    root: Path,
    manifest: Path,
    model: str,
    profile: str,
    output_dir: Path,
    runtime_root: Path | str | None = None,
) -> Mapping[str, object]:
    """Emit packet receipts without adding answers or expected commands."""
    if model != MODEL_ID or profile != HOST_PROFILE:
        raise ProducerError("fresh_model_profile_mismatch")
    _, packets = _packet_manifest(manifest)
    rows: list[dict[str, object]] = []
    for packet in packets:
        rows.append({"id": packet["id"], "packet_class": packet["packet_class"], "prompt_path": packet["prompt_path"], "packet_digest": packet["packet_digest"]})
    payload = {
        "schema": SCHEMA_PACKETS,
        "version": 1,
        "model_id": model,
        "host_profile": profile,
        "packet_count": len(rows),
        "packets": rows,
    }
    _runtime_write(
        _runtime_boundary(root, runtime_root),
        output_dir / "packet-receipt.json",
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        "skill-shim-packet-receipt",
    )
    return cast(Mapping[str, object], payload)


def _canonical_skill_content(context: BuildContext, root: Path, skill: str) -> bytes:
    """Read the current candidate from the catalog's canonical owner.

    The materializer owns the public projection.  Reading an historical Git
    revision here would silently reintroduce a stale parent/source report as
    the baseline and would make the measurement depend on network refs.
    """
    entry = context.catalog_entries.get(skill)
    if entry is None:
        raise ProducerError(f"unknown_skill:{skill}")
    canonical = entry.get("canonical_doc")
    if not isinstance(canonical, str) or not canonical:
        raise ProducerError(f"canonical_doc_missing:{skill}")
    path = root / canonical
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ProducerError(f"canonical_doc_unreadable:{skill}") from exc


def _host_envelope(
    context: BuildContext,
    records: Mapping[str, Mapping[str, object]],
    skill: str,
    model: str,
    profile: str,
    prompt_sha: str,
) -> tuple[dict[str, object], bytes, int, int, bytes]:
    """Build candidate-independent host input from the canonical projection."""
    try:
        provenance = cast(Mapping[str, object], records[skill]["provenance"])
        projection_digest = provenance["record_digest"]
        materializer_id = provenance["materializer_id"]
    except (KeyError, TypeError) as exc:
        raise ProducerError(f"skill_projection_missing:{skill}") from exc
    if not isinstance(projection_digest, str) or not isinstance(materializer_id, str):
        raise ProducerError(f"skill_projection_invalid:{skill}")
    envelope_value = {
        "model_id": model,
        "host_profile": profile,
        "skill_id": skill,
        "skill_projection_digest": projection_digest,
        "materializer_id": materializer_id,
        "prompt_sha256": prompt_sha,
    }
    envelope_bytes = canonical_json_bytes(envelope_value)
    host_bytes, host_scalars, normalized_envelope = deterministic_measure(
        envelope_bytes.decode("utf-8")
    )
    return envelope_value, envelope_bytes, host_bytes, host_scalars, normalized_envelope


def _host_observation(path: Path) -> dict[str, object]:
    """Read one fresh host evaluation observation."""
    raw = cast(Mapping[str, object], json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(raw, dict):
        raise ProducerError(f"host_evaluation_not_object:{path.name}")
    required = {
        "schema", "version", "scenario_id", "category", "packet_id", "iteration_id",
        "packet_class", "skill_id", "variant", "prompt", "prompt_digest", "input_tokens",
        "model_id", "host_profile",
        "method", "observation_status",
    }
    if set(raw) - {"schema", "version", "scenario_id", "category", "packet_id", "iteration_id", "packet_class", "skill_id", "variant", "prompt", "prompt_digest", "input_tokens", "canonical_followup_input_tokens", "cache_fields_observed", "model_id", "host_profile", "method", "observation_status"} or not required.issubset(raw):
        raise ProducerError(f"host_observation_incomplete:{path.name}")
    if raw["schema"] != HOST_OBSERVATION_SCHEMA or raw["version"] != 1:
        raise ProducerError(f"host_schema:{path.name}")
    if not isinstance(raw["category"], str) or not isinstance(raw["scenario_id"], str):
        raise ProducerError(f"host_category:{path.name}")
    if not isinstance(raw["prompt"], str) or not raw["prompt"]:
        raise ProducerError(f"host_prompt:{path.name}")
    if (
        not isinstance(raw["prompt_digest"], str)
        or sha256_bytes(normalize_text(raw["prompt"]).encode("utf-8"))
        != raw["prompt_digest"]
    ):
        raise ProducerError(f"host_prompt_digest:{path.name}")
    if raw["model_id"] != MODEL_ID or raw["host_profile"] != HOST_PROFILE or raw["method"] != "fresh_read_only" or raw["observation_status"] != "pass":
        raise ProducerError(f"host_metadata:{path.name}")
    if raw["variant"] not in VARIANTS:
        raise ProducerError(f"host_variant:{path.name}")
    if not isinstance(raw["skill_id"], str) or not raw["skill_id"]:
        raise ProducerError(f"host_skill_id:{path.name}")
    if isinstance(raw["input_tokens"], bool) or not isinstance(raw["input_tokens"], int) or raw["input_tokens"] < 0:
        raise ProducerError(f"host_input_tokens_invalid:{path.name}")
    followup = raw.get("canonical_followup_input_tokens", 0)
    if isinstance(followup, bool) or not isinstance(followup, int) or followup < 0:
        raise ProducerError(f"canonical_followup_input_tokens_invalid:{path.name}")
    cache = raw.get("cache_fields_observed", {})
    if not isinstance(cache, dict):
        raise ProducerError(f"cache_fields_observed_invalid:{path.name}")
    return {**raw, "canonical_followup_input_tokens": followup, "cache_fields_observed": cache}


def _validate_host_observations(
    observations: Sequence[Mapping[str, object]], packets: Sequence[Mapping[str, object]]
) -> None:
    """Require one current/generated fresh observation for every manifest scenario."""
    expected = {
        cast(str, packet["scenario_id"]): {
            "packet_id": cast(str, packet["id"]),
            "category": cast(str, packet["category"]),
            "packet_class": cast(str, packet["packet_class"]),
            "packet_prompt_sha256": cast(str, packet["packet_prompt_sha256"]),
            "target_skill_id": cast(str, packet["target_skill_id"]),
            "iteration_ids": cast(Mapping[str, object], packet["iteration_ids"]),
        }
        for packet in packets
    }
    seen: set[tuple[str, str]] = set()
    for observation in observations:
        scenario_id = cast(str, observation["scenario_id"])
        variant = cast(str, observation["variant"])
        if scenario_id not in expected:
            raise ProducerError(f"host_observation_mismatch:unknown_scenario:{scenario_id}")
        pair = (scenario_id, variant)
        if pair in seen:
            raise ProducerError(f"host_observation_duplicate:{scenario_id}:{variant}")
        seen.add(pair)
        requirement = expected[scenario_id]
        observed_prompt_digest = sha256_bytes(normalize_text(str(observation["prompt"])).encode("utf-8"))
        if (
            observation["packet_id"] != requirement["packet_id"]
            or observation["category"] != requirement["category"]
            or observation["packet_class"] != requirement["packet_class"]
        ):
            raise ProducerError(f"host_observation_mismatch:{scenario_id}:{variant}")
        if observation["skill_id"] != requirement["target_skill_id"]:
            raise ProducerError(f"host_observation_wrong_skill_id:{scenario_id}:{variant}")
        if (
            observation["prompt_digest"] != requirement["packet_prompt_sha256"]
            or observed_prompt_digest != requirement["packet_prompt_sha256"]
        ):
            raise ProducerError(f"host_observation_unrelated_prompt:{scenario_id}:{variant}")
        iteration_ids = cast(Mapping[str, object], requirement["iteration_ids"])
        if observation["iteration_id"] != iteration_ids.get(variant):
            raise ProducerError(f"host_iteration_mismatch:{scenario_id}:{variant}")
    required_pairs: set[tuple[str, str]] = set()
    for scenario_id in expected:
        for variant in VARIANTS:
            required_pairs.add((scenario_id, variant))
    missing = sorted(required_pairs - seen)
    if missing:
        scenario_id, variant = missing[0]
        raise ProducerError(f"host_observation_missing:{scenario_id}:{variant}")
    if len(observations) != len(required_pairs):
        raise ProducerError("host_observation_incomplete")


def _paired_reduction_summary(
    candidate_rows: Sequence[Mapping[str, object]],
    scenario_rows: Sequence[Mapping[str, object]] = (),
) -> tuple[str, int, int]:
    """Validate every current/generated pair and return status/counts."""
    candidates: dict[str, Mapping[str, object]] = {}
    for row in candidate_rows:
        if row.get("row_type") != "candidate":
            raise ProducerError("candidate_row_type")
        candidate_id = row.get("candidate_row_id")
        if not isinstance(candidate_id, str):
            raise ProducerError("candidate_row_id")
        if candidate_id in candidates:
            raise ProducerError(f"candidate_row_duplicate:{candidate_id}")
        candidates[candidate_id] = row

    pairs: dict[str, dict[str, Mapping[str, object]]] = {}
    paired_candidate_ids: set[str] = set()
    for scenario in scenario_rows:
        scenario_id = scenario.get("scenario_id")
        candidate_id = scenario.get("candidate_row_id")
        variant = scenario.get("variant")
        if (
            not isinstance(scenario_id, str)
            or not isinstance(candidate_id, str)
            or variant not in VARIANTS
        ):
            raise ProducerError("scenario_candidate_identity")
        candidate = candidates.get(candidate_id)
        if candidate is None or candidate.get("variant") != variant:
            raise ProducerError(f"scenario_candidate_mismatch:{scenario_id}:{variant}")
        pair_id = f"scenario:{scenario_id}"
        pair_values = pairs.setdefault(pair_id, {})
        if cast(str, variant) in pair_values:
            raise ProducerError(f"candidate_pair_duplicate:{pair_id}:{variant}")
        pair_values[cast(str, variant)] = candidate
        paired_candidate_ids.add(candidate_id)

    for candidate_id, row in candidates.items():
        if candidate_id in paired_candidate_ids:
            continue
        host_envelope_id = row.get("host_envelope_id")
        if not isinstance(host_envelope_id, str) or not host_envelope_id.startswith("deterministic-"):
            raise ProducerError(f"candidate_pair_unmapped:{candidate_id}")
        skill_id = row.get("skill_id")
        variant = row.get("variant")
        if not isinstance(skill_id, str) or variant not in VARIANTS:
            raise ProducerError(f"deterministic_candidate_identity:{candidate_id}")
        if host_envelope_id != f"deterministic-{skill_id}-{variant}":
            raise ProducerError(f"deterministic_candidate_envelope:{candidate_id}")
        pair_id = f"deterministic:{skill_id}"
        pair_values = pairs.setdefault(pair_id, {})
        if cast(str, variant) in pair_values:
            raise ProducerError(f"candidate_pair_duplicate:{pair_id}:{variant}")
        pair_values[cast(str, variant)] = row
        paired_candidate_ids.add(candidate_id)

    positive_count = 0
    non_positive_count = 0
    for pair_id, pair_values in pairs.items():
        missing: list[str] = [variant for variant in VARIANTS if variant not in pair_values]
        if missing:
            raise ProducerError(f"candidate_pair_missing:{pair_id}:{','.join(missing)}")
        current = pair_values["current"]
        generated = pair_values["generated"]
        if current.get("skill_id") != generated.get("skill_id"):
            raise ProducerError(f"candidate_pair_skill_mismatch:{pair_id}")
        values = (
            current.get("utf8_bytes"),
            generated.get("utf8_bytes"),
            current.get("unicode_scalars"),
            generated.get("unicode_scalars"),
        )
        if not all(isinstance(value, int) for value in values):
            raise ProducerError(f"candidate_pair_measure_invalid:{pair_id}")
        current_bytes, generated_bytes, current_scalars, generated_scalars = cast(
            tuple[int, int, int, int], values
        )
        if (
            current.get("denominator_status") == "valid"
            and generated.get("denominator_status") == "valid"
            and current_bytes > generated_bytes
            and current_scalars > generated_scalars
        ):
            positive_count += 1
        else:
            non_positive_count += 1
    if paired_candidate_ids != set(candidates) or not pairs:
        raise ProducerError("candidate_pair_incomplete")
    return (
        "pass" if non_positive_count == 0 else "fail",
        positive_count,
        non_positive_count,
    )


def measurement(
    root: Path,
    model: str,
    profile: str,
    manifest: Path,
    host_dir: Path,
    output: Path,
    runtime_root: Path | str | None = None,
) -> Mapping[str, object]:
    """Build paired deterministic measurements from observed host token usage."""
    if model != MODEL_ID or profile != HOST_PROFILE:
        raise ProducerError("measurement_model_profile_mismatch")
    _, packets = _packet_manifest(manifest)
    context = build_context(root)
    observations = [_host_observation(path) for path in sorted(host_dir.glob("*.json"))]
    if not observations:
        raise ProducerError("host_evaluations_empty")
    _validate_host_observations(observations, packets)
    host_envelopes: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    scenario_rows: list[dict[str, object]] = []
    records = {skill: build_record(context, skill) for skill in context.skill_ids}
    generated_contents = {skill: render_shim(records[skill]) for skill in context.skill_ids}
    for index, observation in enumerate(observations):
        skill = str(observation["skill_id"])
        if skill not in records:
            raise ProducerError(f"unknown_skill:{skill}")
        variant = cast(str, observation["variant"])
        prompt = str(observation["prompt"])
        prompt_sha = sha256_bytes(prompt.encode("utf-8"))
        envelope_id = f"host-{index:04d}-{observation['scenario_id']}-{variant}"
        envelope_value, envelope_bytes, host_bytes, host_scalars, normalized_envelope = _host_envelope(
            context, cast(Mapping[str, Mapping[str, object]], records), skill, model, profile, prompt_sha
        )
        host_envelopes.append(
            {
                "row_type": "host_envelope",
                "host_envelope_id": envelope_id,
                **envelope_value,
                "prompt_sha256": prompt_sha,
                "host_envelope_sha256": sha256_bytes(normalized_envelope),
                "host_utf8_bytes": host_bytes,
                "host_unicode_scalars": host_scalars,
            }
        )
        if variant == "generated":
            candidate_text = generated_contents[skill]
        else:
            candidate_text = _canonical_skill_content(context, root, skill).decode("utf-8")
        _, _, normalized_candidate = deterministic_measure(candidate_text)
        combined = normalize_text(envelope_bytes.decode("utf-8") + "\n" + candidate_text).encode("utf-8")
        candidate_row_id = f"candidate-{index:04d}"
        candidate_rows.append(
            {
                "row_type": "candidate",
                "candidate_row_id": candidate_row_id,
                "host_envelope_id": envelope_id,
                "skill_id": skill,
                "variant": variant,
                "content_sha256": sha256_bytes(normalized_candidate),
                "measured_input": "host_envelope_plus_candidate",
                "utf8_bytes": len(combined),
                "unicode_scalars": len(normalize_text(envelope_bytes.decode("utf-8") + "\n" + candidate_text)),
                "denominator_status": "valid" if len(combined) > 0 else "not_applicable",
            }
        )
        scenario_rows.append(
            {
                "row_type": "scenario",
                "scenario_row_id": f"scenario-{index:04d}",
                "scenario_id": observation["scenario_id"],
                "packet_id": observation["packet_id"],
                "iteration_id": observation["iteration_id"],
                "provenance": "fresh",
                "candidate_row_id": candidate_row_id,
                "host_envelope_id": envelope_id,
                "variant": variant,
                "host_input_tokens": observation["input_tokens"],
                "host_usage_source": "fresh_host_evaluation",
                "canonical_followup_input_tokens": observation["canonical_followup_input_tokens"],
                "cache_fields_observed": observation["cache_fields_observed"],
                "observation_status": "pass",
            }
        )
    # The deterministic comparison covers every public skill; fresh host observations
    # cover the six manifest scenarios without inventing token usage or answers.
    baseline_prompt = "agent-canon.skill-runtime-shim.deterministic-measurement"
    baseline_prompt_sha = sha256_bytes(baseline_prompt.encode("utf-8"))
    for skill in context.skill_ids:
        envelope_value, envelope_bytes, host_bytes, host_scalars, normalized_envelope = _host_envelope(
            context,
            cast(Mapping[str, Mapping[str, object]], records),
            skill,
            model,
            profile,
            baseline_prompt_sha,
        )
        for variant in VARIANTS:
            envelope_id = f"deterministic-{skill}-{variant}"
            host_envelopes.append(
                {
                    "row_type": "host_envelope",
                    "host_envelope_id": envelope_id,
                    **envelope_value,
                    "prompt_sha256": baseline_prompt_sha,
                    "host_envelope_sha256": sha256_bytes(normalized_envelope),
                    "host_utf8_bytes": host_bytes,
                    "host_unicode_scalars": host_scalars,
                }
            )
            if variant == "generated":
                candidate_text = generated_contents[skill]
            else:
                candidate_text = _canonical_skill_content(context, root, skill).decode("utf-8")
            _, _, normalized_candidate = deterministic_measure(candidate_text)
            combined = normalize_text(envelope_bytes.decode("utf-8") + "\n" + candidate_text)
            candidate_rows.append(
                {
                    "row_type": "candidate",
                    "candidate_row_id": f"candidate-deterministic-{skill}-{variant}",
                    "host_envelope_id": envelope_id,
                    "skill_id": skill,
                    "variant": variant,
                    "content_sha256": sha256_bytes(normalized_candidate),
                    "measured_input": "host_envelope_plus_candidate",
                    "utf8_bytes": len(combined.encode("utf-8")),
                    "unicode_scalars": len(combined),
                    "denominator_status": "valid" if combined else "not_applicable",
                }
            )
    current = [row for row in candidate_rows if row["variant"] == "current"]
    generated = [row for row in candidate_rows if row["variant"] == "generated"]
    current_bytes = sum(cast(int, row["utf8_bytes"]) for row in current)
    generated_bytes = sum(cast(int, row["utf8_bytes"]) for row in generated)
    current_scalars = sum(cast(int, row["unicode_scalars"]) for row in current)
    generated_scalars = sum(cast(int, row["unicode_scalars"]) for row in generated)
    valid_rows = sum(row["denominator_status"] == "valid" for row in candidate_rows)
    pair_status, positive_pair_count, non_positive_pair_count = (
        _paired_reduction_summary(candidate_rows, scenario_rows)
    )
    summary = {
        "host_envelope_count": len(host_envelopes),
        "candidate_row_count": len(candidate_rows),
        "scenario_row_count": len(scenario_rows),
        "valid_denominator_row_count": valid_rows,
        "not_applicable_row_count": len(candidate_rows) - valid_rows,
        "current_utf8_bytes_total": current_bytes,
        "generated_utf8_bytes_total": generated_bytes,
        "current_unicode_scalars_total": current_scalars,
        "generated_unicode_scalars_total": generated_scalars,
        "observed_host_input_tokens_total": sum(cast(int, row["host_input_tokens"]) for row in scenario_rows),
        "paired_reduction_row_count": positive_pair_count + non_positive_pair_count,
        "non_positive_reduction_row_count": non_positive_pair_count,
        "deterministic_reduction_status": (
            "pass"
            if current_bytes > 0
            and generated_bytes < current_bytes
            and (current_bytes - generated_bytes) / current_bytes >= 0.70
            and pair_status == "pass"
            else "fail"
        ),
    }
    run_id = output.stem or f"skill-shim-{context.source_snapshot_digest[:10]}"
    payload = {
        "schema": SCHEMA_MEASUREMENT,
        "version": 1,
        "run_id": run_id,
        "source_snapshot_digest": context.source_snapshot_digest,
        "model_id": model,
        "host_profile": profile,
        "normalization": NORMALIZATION,
        "host_envelopes": host_envelopes,
        "candidate_rows": candidate_rows,
        "scenario_rows": scenario_rows,
        "summary": summary,
    }
    _runtime_write(
        _runtime_boundary(root, runtime_root),
        output,
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        "skill-shim-measurement",
    )
    return cast(Mapping[str, object], payload)


def build_parser() -> argparse.ArgumentParser:
    """Build the evaluation producer CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    route = subparsers.add_parser("route-golden")
    route.add_argument("--root", type=Path, default=Path.cwd())
    route.add_argument("--manifest", type=Path, required=True)
    route.add_argument("--route-cli", type=Path, required=True)
    route.add_argument("--output", type=Path, required=True)
    route.add_argument("--runtime-root", type=Path)
    packets = subparsers.add_parser("packets")
    packets.add_argument("--root", type=Path, default=Path.cwd())
    packets.add_argument("--manifest", type=Path, required=True)
    packets.add_argument("--model", default=MODEL_ID)
    packets.add_argument("--profile", default=HOST_PROFILE)
    packets.add_argument("--output-dir", type=Path, required=True)
    packets.add_argument("--runtime-root", type=Path)
    tokens = subparsers.add_parser("tokens")
    tokens.add_argument("--root", type=Path, default=Path.cwd())
    tokens.add_argument("--model", default=MODEL_ID)
    tokens.add_argument("--profile", default=HOST_PROFILE)
    tokens.add_argument("--manifest", type=Path, required=True)
    tokens.add_argument("--host-evaluation-dir", type=Path, required=True)
    tokens.add_argument("--output", type=Path, required=True)
    tokens.add_argument("--runtime-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one producer command."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "route-golden":
            payload = route_golden(
                args.root.resolve(),
                args.manifest.resolve(),
                args.route_cli,
                args.output.resolve(),
                args.runtime_root,
            )
        elif args.command == "packets":
            payload = packet_receipt(
                args.root.resolve(),
                args.manifest.resolve(),
                args.model,
                args.profile,
                args.output_dir.resolve(),
                args.runtime_root,
            )
        else:
            payload = measurement(
                args.root.resolve(),
                args.model,
                args.profile,
                args.manifest.resolve(),
                args.host_evaluation_dir.resolve(),
                args.output.resolve(),
                args.runtime_root,
            )
    except (OSError, ProducerError, ValueError, json.JSONDecodeError) as exc:
        print(f"SKILL_SHIM_EVALUATION_FAILURE={exc}")
        return 2
    print(json.dumps({"status": "pass", "schema": payload["schema"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
