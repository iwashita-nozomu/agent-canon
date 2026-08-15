#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates centralized experiment template copying in a temporary parent-shaped repository.
# upstream design ../../documents/experiments/experiment-registry.md registry schema and path contract
# upstream design ../../templates/README.md centralized template owner and copy boundary
# upstream implementation ../experiments/create_experiment_topic.py canonical topic creation and copy route
# upstream implementation ../agent_tools/parent_root_side_effects.py owns smoke-fixture allocation and exact cleanup
# upstream implementation ./check_experiment_registry.py validates the temporary registry identity
# downstream implementation ../../tests/tools/test_check_experiment_template.py tests this smoke checker
# @dependency-end

"""中央 experiment template を parent route 経由で smoke-check します."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

import yaml

AGENT_TOOLS_ROOT = Path(__file__).resolve().parents[1] / "agent_tools"
if str(AGENT_TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_TOOLS_ROOT))

from parent_root_side_effects import (  # noqa: E402
    ParentRootSideEffectBoundary,
    SessionResolutionResult,
    public_session,
)

TOPIC = "template-smoke"
VARIANT = "smoke.v1"


def build_parser() -> argparse.ArgumentParser:
    """チェッカー CLI の parser を構築します."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        default=str(Path(__file__).resolve().parents[2]),
        help="AgentCanon source root. Defaults to this checkout.",
    )
    return parser


def run_checked(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """GPU を使わない validation command 一つを strict failure semantics で実行します."""
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n{output}"
        )
    return result


def write_parent_registry(parent_root: Path) -> Path:
    """一時的な parent-owned registry fixture だけを作成します."""
    registry_path = parent_root / "experiments" / "registry.toml"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        "\n".join(
            (
                "schema_version = 1",
                "topics = []",
                "",
                "[defaults]",
                'registry_identity = "template-smoke-parent"',
                'managed_runner = "tools/experiments/run_managed_experiment.py"',
                'report_root = "experiments/report"',
                'topic_template_dir = "vendor/agent-canon/templates/experiments/_template"',
                'required_eval_artifacts = ["summary.json", "cases.jsonl"]',
                "",
            )
        ),
        encoding="utf-8",
    )
    (parent_root / "experiments" / "report").mkdir(parents=True, exist_ok=True)
    return registry_path


def materialize_parent_fixture(source_root: Path, parent_root: Path) -> None:
    """最小の parent-shaped source と runner surface を materialize します."""
    canon_root = parent_root / "vendor" / "agent-canon"
    shutil.copytree(source_root / "templates", canon_root / "templates")
    runner_path = parent_root / "tools" / "experiments" / "run_managed_experiment.py"
    runner_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_root / "tools" / "experiments" / "run_managed_experiment.py", runner_path)


def complete_template_fixture(topic_dir: Path) -> None:
    """テスト専用に semantic completion field を個別 materialize します."""
    config_path = topic_dir / "config.yaml"
    config_object: object = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config_object, dict):
        raise RuntimeError("completion fixture requires a YAML mapping")
    config = cast(dict[str, object], config_object)
    config.update(
        {
            "template_complete": True,
            "cases": {"example": {"values": [1.0, 2.0], "unit": "unitless", "shape": [2]}},
            "metric": {"name": "sum", "direction": "higher_is_better"},
            "runtime": {"entrypoint": "run.py", "managed": True},
            "algorithm_contract": {
                "public_entrypoint": "run_case_worker",
                "state_transition": "case_to_terminal_record",
            },
            "oracle": {"necessary": ["case record"], "sufficient": ["digest readback"]},
            "provenance": {"source": "smoke fixture", "owner": "checker"},
            "failure": {"classification": "expected_contract", "evidence": "failure-evidence.json"},
            "lifecycle": {"retention": "test run", "cleanup": "temporary directory"},
        }
    )
    config_path.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    provenance_path = topic_dir / "provenance.toml"
    provenance_text = provenance_path.read_text(encoding="utf-8")
    provenance_text = provenance_text.replace("template_complete = false", "template_complete = true", 1)
    provenance_text = provenance_text.replace(
        'completion_status = "incomplete"', 'completion_status = "complete"', 1
    )
    placeholder_values = {
        "topic": "template-smoke",
        "owner": "smoke-owner",
        "question": "does the scaffold publish a typed result",
        "hypothesis": "complete provenance permits one case",
        "sha256": "a" * 64,
        "non-goal": "production benchmark",
        "baseline": "baseline",
        "candidate": "candidate",
        "case-id": "example",
        "metric": "sum",
        "stopping-rule": "one case",
        "oracle": "summary and manifest readback",
        "entrypoint": "run_case_worker",
        "input-schema": "CaseSpec",
        "state-transition-or-recurrence": "case to terminal record",
        "invariant": "terminal state is explicit",
        "typed-failure-and-preserved-state": "failure record is preserved",
        "observation": "typed case observation",
        "claim-outside-oracle": "performance claim",
        "required-or-not-applicable-with-reason": "required for smoke",
        "mechanism-and-cost": "local case worker",
        "rationale-or-none": "not selected",
        "evidence-path-or-record": "summary.json",
        "option-id": "option-a",
        "why-other-options-were-rejected": "not selected",
        "cpu-memory-gpu-request": "cpu-only smoke",
        "capability-or-scheduler-reason": "no device required",
        "none-or-recorded-limit": "none",
        "caller-or-scheduler-record": "smoke caller",
        "repository": "agent-canon",
        "branch": "codex/template-canon-refresh",
        "commit-sha": "a" * 40,
        "config-path": "experiments/template-smoke/config.yaml",
        "result-path": f"result/{VARIANT}/template-smoke-run",
        "exit-status": "0",
        "required-close-condition": "rerun after contract repair",
        "required-oracle-and-observation": "summary and manifest pass",
        "preserved-intent-or-none": "none",
        "none-or-description": "none",
        "evidence-path-or-command": "summary.json",
        "seed-policy": "deterministic fixture",
        "managed-runner": "tools/experiments/run_managed_experiment.py",
        "exact-command": "python3 experiments/template-smoke/run.py",
        "run-id": "template-smoke-run",
        "RFC3339": "2026-08-04T00:00:00Z",
        "expected|infrastructure|implementation|oracle|unknown|none": "none",
        "required-path-or-none": "none",
        "required-reason-or-none": "none",
        "policy": "retain until checker exits",
        "command": "temporary directory cleanup",
        "reviewer": "independent-smoke-reviewer",
        "commit-or-artifact": "a" * 40,
        "pass-or-revise-or-reject": "pass",
        "parameter-record": "values=[1.0, 2.0]",
        "expected-observation": "sum=3.0",
    }
    for token, value in placeholder_values.items():
        provenance_text = provenance_text.replace(f'"<{token}>"', f'"{value}"')
    provenance_text = provenance_text.replace(
        "<result-path>", f"result/{VARIANT}/template-smoke-run"
    )
    provenance_text = provenance_text.replace(
        'status = "selected-or-rejected"', 'status = "rejected"'
    )
    provenance_text = provenance_text.replace('status = "rejected"', 'status = "selected"', 1)
    provenance_path.write_text(provenance_text, encoding="utf-8")


def validate_run_state(result_dir: Path, expected_state: str, expected_case_count: int) -> None:
    """生成済み run の state、case 数、completion provenance を検証します."""
    summary = json.loads((result_dir / "summary.json").read_text(encoding="utf-8"))
    if summary.get("status") != expected_state:
        raise RuntimeError(
            f"expected run state {expected_state}, got {summary.get('status')}"
        )
    if summary.get("case_count") != expected_case_count:
        raise RuntimeError("materialized experiment run has an unexpected case count")
    if summary.get("template_complete") != (expected_state == "success"):
        raise RuntimeError("run state and template completion provenance disagree")
    if expected_state == "incomplete":
        if not (result_dir / "failure-evidence.json").is_file():
            raise RuntimeError("incomplete run must preserve failure evidence")
        if (result_dir / "cases.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("incomplete run must not execute cases")


def validate_generated_topic(parent_root: Path, registry_path: Path) -> None:
    """生成した registry identity、topic structure、run artifact を検証します."""
    topic_dir = parent_root / "experiments" / TOPIC
    required_files = (
        topic_dir / "README.md",
        topic_dir / "provenance.toml",
        topic_dir / "run.py",
        topic_dir / "cases.py",
        topic_dir / "case_model.py",
        topic_dir / "case_execution.py",
        topic_dir / "artifact_schema.py",
        topic_dir / "artifact_io.py",
        topic_dir / "visualization.py",
        topic_dir / "config.yaml",
        topic_dir / "visualize.ipynb",
        topic_dir / "result" / ".gitkeep",
    )
    missing = [str(path.relative_to(parent_root)) for path in required_files if not path.is_file()]
    if missing:
        raise RuntimeError(f"generated topic is missing required files: {', '.join(missing)}")

    registry_text = registry_path.read_text(encoding="utf-8")
    if 'registry_identity = "template-smoke-parent"' not in registry_text:
        raise RuntimeError("temporary registry identity was not preserved")
    if f'name = "{TOPIC}"' not in registry_text:
        raise RuntimeError("canonical create route did not register template-smoke")

    notebook = json.loads((topic_dir / "visualize.ipynb").read_text(encoding="utf-8"))
    if not isinstance(notebook.get("cells"), list) or not notebook["cells"]:
        raise RuntimeError("generated notebook has no cells")
    if notebook.get("nbformat") != 4:
        raise RuntimeError("generated notebook must use nbformat 4")

    result_dir = topic_dir / "result" / VARIANT / "template-smoke-run"
    required_artifacts = (
        "summary.json",
        "cases.jsonl",
        "artifact-manifest.json",
        "config_snapshot.json",
        "provenance_snapshot.toml",
        "environment.json",
        "visualization-status.json",
    )
    missing_artifacts = [
        name for name in required_artifacts if not (result_dir / name).is_file()
    ]
    if missing_artifacts:
        raise RuntimeError(
            "materialized experiment run is missing artifacts: "
            + ", ".join(missing_artifacts)
        )
    validate_run_state(result_dir, "success", 1)


def main() -> int:
    """Enter the public source-root session before running the smoke check."""
    with public_session(
        invocation_script=Path(__file__),
        purpose="experiment-template-smoke",
    ) as session:
        return _main_authenticated(session)


def _main_authenticated(session: SessionResolutionResult) -> int:
    """分離した parent-shaped fixture を作成、検証、削除します."""
    args = build_parser().parse_args()
    source_root = Path(args.source_root).resolve()
    create_tool = source_root / "tools" / "experiments" / "create_experiment_topic.py"
    registry_checker = source_root / "tools" / "ci" / "check_experiment_registry.py"
    if not source_root.is_dir() or not create_tool.is_file() or not registry_checker.is_file():
        raise SystemExit("AgentCanon source root or canonical experiment tools are missing")

    selected_parent = session.parent_root
    boundary = ParentRootSideEffectBoundary()
    attestation = session.attestation
    temporary = boundary.create_parent_owned_temp_directory(
        attestation,
        selected_parent / ".agent-canon" / "tmp",
        "experiment-template-smoke",
        "template-smoke",
    )
    try:
        parent_root = temporary.physical_path
        runtime_tmp = parent_root / ".runtime" / "tmp"
        runtime_cache = parent_root / ".runtime" / "cache"
        runtime_pycache = runtime_cache / "pycache"
        runtime_tmp.mkdir(parents=True)
        runtime_pycache.mkdir(parents=True)
        run_env = boundary.child_environment(
            session.attestation,
            os.environ,
            issue_handoff=False,
        )
        run_env.update(
            {
                "PYTHONPYCACHEPREFIX": str(runtime_pycache),
                "TEMP": str(runtime_tmp),
                "TMP": str(runtime_tmp),
                "TMPDIR": str(runtime_tmp),
                "XDG_CACHE_HOME": str(runtime_cache),
            }
        )
        materialize_parent_fixture(source_root, parent_root)
        registry_path = write_parent_registry(parent_root)

        run_checked(
            [
                sys.executable,
                "-m",
                "tools.experiments.create_experiment_topic",
                "--repo-root",
                str(parent_root),
                "--status",
                "template",
                "--default-variant",
                VARIANT,
                TOPIC,
            ],
            cwd=source_root,
            env=run_env,
        )
        topic_dir = parent_root / "experiments" / TOPIC
        incomplete_run_dir = topic_dir / "result" / VARIANT / "template-smoke-incomplete"
        run_env["EXPERIMENT_RUN_MANIFEST"] = str(parent_root / "manifest.json")
        run_env["EXPERIMENT_VARIANT"] = VARIANT
        run_env["EXPERIMENT_RUN_DIR"] = str(incomplete_run_dir)
        incomplete_result = subprocess.run(
            [sys.executable, str(topic_dir / "run.py")],
            cwd=source_root,
            check=False,
            capture_output=True,
            text=True,
            env=run_env,
        )
        if incomplete_result.returncode == 0:
            raise RuntimeError("incomplete template scaffold must not report success")
        validate_run_state(incomplete_run_dir, "incomplete", 0)

        complete_template_fixture(topic_dir)
        run_dir = topic_dir / "result" / VARIANT / "template-smoke-run"
        run_env["EXPERIMENT_RUN_DIR"] = str(run_dir)
        run_checked([sys.executable, str(topic_dir / "run.py")], cwd=source_root, env=run_env)
        validate_generated_topic(parent_root, registry_path)
        run_checked(
            [
                sys.executable,
                "-m",
                "tools.ci.check_experiment_registry",
                "--repo-root",
                str(parent_root),
                "--registry",
                str(registry_path),
            ],
            cwd=source_root,
            env=run_env,
        )
        run_checked(
            [
                sys.executable,
                "-m",
                "py_compile",
                str(parent_root / "experiments" / TOPIC / "run.py"),
                str(parent_root / "experiments" / TOPIC / "cases.py"),
            ],
            cwd=source_root,
            env=run_env,
        )
    finally:
        boundary.remove_parent_owned_tree(
            attestation,
            temporary,
            "experiment-template-smoke-cleanup",
        )

    print("EXPERIMENT_TEMPLATE_SMOKE=pass")
    print(f"EXPERIMENT_TEMPLATE_TOPIC=experiments/{TOPIC}")
    print("EXPERIMENT_TEMPLATE_EXECUTION=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
