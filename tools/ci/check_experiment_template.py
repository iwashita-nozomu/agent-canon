#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates centralized experiment template copying in a temporary parent-shaped repository.
# upstream design ../../documents/experiments/experiment-registry.md registry schema and path contract
# upstream design ../../templates/README.md centralized template owner and copy boundary
# upstream implementation ../experiments/create_experiment_topic.py canonical topic creation and copy route
# upstream implementation ./check_experiment_registry.py validates the temporary registry identity
# downstream implementation ../../tests/tools/test_check_experiment_template.py tests this smoke checker
# @dependency-end

"""Smoke-check the centralized experiment template through the parent route."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOPIC = "template-smoke"


def build_parser() -> argparse.ArgumentParser:
    """Build the checker CLI."""
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
    """Run one non-GPU validation command with strict failure semantics."""
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
    """Create only the temporary parent-owned registry fixture."""
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
    """Materialize the minimum parent-shaped source and runner surfaces."""
    canon_root = parent_root / "vendor" / "agent-canon"
    shutil.copytree(source_root / "templates", canon_root / "templates")
    runner_path = parent_root / "tools" / "experiments" / "run_managed_experiment.py"
    runner_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_root / "tools" / "experiments" / "run_managed_experiment.py", runner_path)


def validate_generated_topic(parent_root: Path, registry_path: Path) -> None:
    """Validate generated registry identity, topic structure, and run artifacts."""
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

    result_dir = topic_dir / "result" / "template-smoke-run"
    required_artifacts = (
        "summary.json",
        "cases.jsonl",
        "artifact-manifest.json",
        "config_snapshot.json",
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
    summary = json.loads((result_dir / "summary.json").read_text(encoding="utf-8"))
    if summary.get("status") != "success" or summary.get("case_count") != 1:
        raise RuntimeError("materialized experiment run did not produce one successful case")


def main() -> int:
    """Create, validate, and remove an isolated parent-shaped fixture."""
    args = build_parser().parse_args()
    source_root = Path(args.source_root).resolve()
    create_tool = source_root / "tools" / "experiments" / "create_experiment_topic.py"
    registry_checker = source_root / "tools" / "ci" / "check_experiment_registry.py"
    if not source_root.is_dir() or not create_tool.is_file() or not registry_checker.is_file():
        raise SystemExit("AgentCanon source root or canonical experiment tools are missing")

    with tempfile.TemporaryDirectory(prefix="agent-canon-template-smoke-") as temporary:
        parent_root = Path(temporary)
        materialize_parent_fixture(source_root, parent_root)
        registry_path = write_parent_registry(parent_root)

        run_checked(
            [
                sys.executable,
                str(create_tool),
                "--repo-root",
                str(parent_root),
                "--status",
                "template",
                TOPIC,
            ],
            cwd=source_root,
        )
        topic_dir = parent_root / "experiments" / TOPIC
        run_dir = topic_dir / "result" / "template-smoke-run"
        run_env = dict(os.environ)
        run_env["EXPERIMENT_RUN_MANIFEST"] = str(parent_root / "manifest.json")
        run_env["EXPERIMENT_RUN_DIR"] = str(run_dir)
        run_checked(
            [sys.executable, str(topic_dir / "run.py")],
            cwd=source_root,
            env=run_env,
        )
        validate_generated_topic(parent_root, registry_path)
        run_checked(
            [
                sys.executable,
                str(registry_checker),
                "--repo-root",
                str(parent_root),
                "--registry",
                str(registry_path),
            ],
            cwd=source_root,
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
        )

    print("EXPERIMENT_TEMPLATE_SMOKE=pass")
    print(f"EXPERIMENT_TEMPLATE_TOPIC=experiments/{TOPIC}")
    print("EXPERIMENT_TEMPLATE_EXECUTION=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
