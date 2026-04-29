# @dependency-start
# upstream design ../../tools/README.md validated automation surface
# upstream implementation ../../tools/ci/check_experiment_registry.py checker under test
# @dependency-end

"""Tests for the managed experiment run helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CHECK_SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "ci" / "check_experiment_registry.py"
CREATE_TOPIC_SCRIPT = (
    Path(__file__).resolve().parents[2] / "tools" / "experiments" / "create_experiment_topic.py"
)
SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "experiments" / "run_managed_experiment.py"
SYNC_CONTEXT_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "experiments"
    / "sync_experiment_registry_context.py"
)
CANONICAL_ENTRYPOINT = "experiments/demo_topic/experimentcode.py"
SMOKE_INNER_COMMAND = f"python3 {CANONICAL_ENTRYPOINT} --run-dir {{run_dir}} --mode smoke"
FORMAL_INNER_COMMAND = f"python3 {CANONICAL_ENTRYPOINT} --run-dir {{run_dir}} --mode formal"
RECURSIVE_RUNNER_COMMAND = "python3 tools/experiments/run_managed_experiment.py --topic demo_topic"


def build_repo(tmp_path: Path) -> Path:
    """Create a minimal fake repo layout for the helper."""
    repo_root = tmp_path / "repo"
    (repo_root / "experiments" / "_template" / "result").mkdir(parents=True)
    (repo_root / "experiments" / "demo_topic" / "result").mkdir(parents=True)
    (repo_root / "experiments" / "report").mkdir(parents=True)
    (repo_root / "tools" / "experiments").mkdir(parents=True)
    (repo_root / "experiments" / "_template" / "README.md").write_text(
        "# Experiment Topic Template\n\n"
        "smoke: `python3 tools/experiments/run_managed_experiment.py "
        "--topic <topic> --use-registered-command smoke`\n",
        encoding="utf-8",
    )
    (repo_root / "experiments" / "_template" / "cases.py").write_text(
        "from __future__ import annotations\n",
        encoding="utf-8",
    )
    (repo_root / "experiments" / "_template" / "experimentcode.py").write_text(
        "from __future__ import annotations\n",
        encoding="utf-8",
    )
    (repo_root / "experiments" / "_template" / "result" / "README.md").write_text(
        "# Result Directory\n",
        encoding="utf-8",
    )
    (repo_root / "experiments" / "demo_topic" / "README.md").write_text(
        "# Demo Topic\n",
        encoding="utf-8",
    )
    (repo_root / "tools" / "experiments" / "run_managed_experiment.py").write_text(
        "# placeholder\n",
        encoding="utf-8",
    )
    (repo_root / "experiments" / "demo_topic" / "experimentcode.py").write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "import argparse",
                "import json",
                "from pathlib import Path",
                "",
                "parser = argparse.ArgumentParser()",
                'parser.add_argument("--run-dir", required=True)',
                'parser.add_argument("--mode", required=True)',
                "args = parser.parse_args()",
                "run_dir = Path(args.run_dir)",
                "run_dir.mkdir(parents=True, exist_ok=True)",
                "(run_dir / 'marker.txt').write_text(args.mode, encoding='utf-8')",
                "(run_dir / 'summary.json').write_text(",
                (
                    "    json.dumps({'status': 'completed', 'mode': args.mode}, "
                    "ensure_ascii=True) + '\\n',"
                ),
                "    encoding='utf-8',",
                ")",
                "(run_dir / 'cases.jsonl').write_text(",
                (
                    "    json.dumps({'case_id': 'demo-1', 'status': 'ok', "
                    "'mode': args.mode}, ensure_ascii=True) + '\\n',"
                ),
                "    encoding='utf-8',",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "experiments" / "registry.toml").write_text(
        "\n".join(
            [
                "schema_version = 1",
                "",
                "[defaults]",
                'managed_runner = "tools/experiments/run_managed_experiment.py"',
                'report_root = "experiments/report"',
                'integration_branch = "main"',
                'topic_template_dir = "experiments/_template"',
                'required_eval_artifacts = ["summary.json", "cases.jsonl"]',
                "",
                "[[topics]]",
                'name = "demo_topic"',
                'status = "active"',
                'topic_dir = "experiments/demo_topic"',
                'topic_readme = "experiments/demo_topic/README.md"',
                f'canonical_entrypoint = "{CANONICAL_ENTRYPOINT}"',
                'result_root = "experiments/demo_topic/result"',
                'report_root = "experiments/report"',
                'default_variant = "formal"',
                f'smoke_inner_command = "{SMOKE_INNER_COMMAND}"',
                f'formal_inner_command = "{FORMAL_INNER_COMMAND}"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    return repo_root


def test_run_managed_experiment_uses_registered_command_and_writes_manifest(tmp_path: Path) -> None:
    """The helper should create canonical files for one successful registered run."""
    repo_root = build_repo(tmp_path)
    run_name = "demo_topic_smoke_20260406T000000Z"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo_root),
            "--topic",
            "demo_topic",
            "--run-name",
            run_name,
            "--use-registered-command",
            "smoke",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    result_dir = repo_root / "experiments" / "demo_topic" / "result" / run_name
    manifest = json.loads((result_dir / "run_manifest.json").read_text(encoding="utf-8"))
    eval_manifest = json.loads((result_dir / "eval_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["exit_code"] == 0
    assert manifest["command_source"] == "registered:smoke"
    assert manifest["registered_command_match"] == "smoke"
    assert manifest["registry"]["canonical_entrypoint"] == CANONICAL_ENTRYPOINT
    assert manifest["eval_artifacts"]["collected_artifact_count"] == 2
    assert manifest["eval_artifacts"]["missing_required_patterns"] == []
    assert (result_dir / "run.log").is_file()
    assert (result_dir / "marker.txt").read_text(encoding="utf-8") == "smoke"
    assert eval_manifest["missing_required_patterns"] == []
    collected_paths = {artifact["relative_path"] for artifact in eval_manifest["artifacts"]}
    assert collected_paths == {"summary.json", "cases.jsonl"}
    report_path = repo_root / "experiments" / "report" / f"{run_name}.md"
    assert report_path.is_file()
    assert run_name in report_path.read_text(encoding="utf-8")


def test_run_managed_experiment_propagates_failure(tmp_path: Path) -> None:
    """The helper should return the child exit code and mark the run failed."""
    repo_root = build_repo(tmp_path)
    run_name = "demo_topic_fail_20260406T000000Z"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo_root),
            "--topic",
            "demo_topic",
            "--run-name",
            run_name,
            "--",
            sys.executable,
            "-c",
            "import sys; sys.exit(7)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 7
    manifest_path = (
        repo_root / "experiments" / "demo_topic" / "result" / run_name / "run_manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    eval_manifest = json.loads(
        (
            repo_root / "experiments" / "demo_topic" / "result" / run_name / "eval_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["status"] == "failed"
    assert manifest["exit_code"] == 7
    assert manifest["command_source"] == "manual"
    assert manifest["eval_artifacts"]["missing_required_patterns"] == [
        "summary.json",
        "cases.jsonl",
    ]
    assert eval_manifest["artifact_count"] == 0


def test_run_managed_experiment_collects_topic_specific_optional_eval_artifacts(
    tmp_path: Path,
) -> None:
    """The helper should collect topic-specific optional eval artifacts from the registry."""
    repo_root = build_repo(tmp_path)
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_text = registry_path.read_text(encoding="utf-8").replace(
        f'formal_inner_command = "{FORMAL_INNER_COMMAND}"',
        (
            f'formal_inner_command = "{FORMAL_INNER_COMMAND}"\n'
            'optional_eval_artifacts = ["marker.txt"]'
        ),
    )
    registry_path.write_text(registry_text, encoding="utf-8")
    run_name = "demo_topic_formal_20260406T000000Z"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo_root),
            "--topic",
            "demo_topic",
            "--run-name",
            run_name,
            "--use-registered-command",
            "formal",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    result_dir = repo_root / "experiments" / "demo_topic" / "result" / run_name
    eval_manifest = json.loads((result_dir / "eval_manifest.json").read_text(encoding="utf-8"))
    artifacts = {artifact["relative_path"]: artifact for artifact in eval_manifest["artifacts"]}
    assert "marker.txt" in artifacts
    assert artifacts["marker.txt"]["matched_patterns"] == ["marker.txt"]
    assert artifacts["marker.txt"]["line_count"] == 1


def test_run_managed_experiment_collects_binary_named_optional_artifact_without_crashing(
    tmp_path: Path,
) -> None:
    """The helper should not crash when one matched artifact contains non-UTF8 bytes."""
    repo_root = build_repo(tmp_path)
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_text = registry_path.read_text(encoding="utf-8").replace(
        f'formal_inner_command = "{FORMAL_INNER_COMMAND}"',
        (
            f'formal_inner_command = "{FORMAL_INNER_COMMAND}"\n'
            'optional_eval_artifacts = ["binary.txt"]'
        ),
    )
    registry_path.write_text(registry_text, encoding="utf-8")
    experiment_path = repo_root / "experiments" / "demo_topic" / "experimentcode.py"
    experiment_path.write_text(
        experiment_path.read_text(encoding="utf-8")
        + "\n(run_dir / 'binary.txt').write_bytes(b'\\xff\\xfe\\n')\n",
        encoding="utf-8",
    )
    run_name = "demo_topic_formal_binary_20260406T000000Z"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo_root),
            "--topic",
            "demo_topic",
            "--run-name",
            run_name,
            "--use-registered-command",
            "formal",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    result_dir = repo_root / "experiments" / "demo_topic" / "result" / run_name
    manifest = json.loads((result_dir / "run_manifest.json").read_text(encoding="utf-8"))
    eval_manifest = json.loads((result_dir / "eval_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    artifacts = {artifact["relative_path"]: artifact for artifact in eval_manifest["artifacts"]}
    assert "binary.txt" in artifacts
    assert artifacts["binary.txt"]["line_count"] == 1


def test_run_managed_experiment_excludes_managed_files_from_optional_wildcards(
    tmp_path: Path,
) -> None:
    """The helper should not inventory its own managed files via wildcard patterns."""
    repo_root = build_repo(tmp_path)
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_text = registry_path.read_text(encoding="utf-8").replace(
        f'formal_inner_command = "{FORMAL_INNER_COMMAND}"',
        f'formal_inner_command = "{FORMAL_INNER_COMMAND}"\noptional_eval_artifacts = ["*.json"]',
    )
    registry_path.write_text(registry_text, encoding="utf-8")
    run_name = "demo_topic_formal_jsonwild_20260406T000000Z"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo_root),
            "--topic",
            "demo_topic",
            "--run-name",
            run_name,
            "--use-registered-command",
            "formal",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    result_dir = repo_root / "experiments" / "demo_topic" / "result" / run_name
    eval_manifest = json.loads((result_dir / "eval_manifest.json").read_text(encoding="utf-8"))
    collected_paths = {artifact["relative_path"] for artifact in eval_manifest["artifacts"]}
    assert "summary.json" in collected_paths
    assert "run_manifest.json" not in collected_paths
    assert "eval_manifest.json" not in collected_paths


def test_run_managed_experiment_keeps_nested_run_log_artifacts_collectable(
    tmp_path: Path,
) -> None:
    """The helper should keep nested log artifacts collectable."""
    repo_root = build_repo(tmp_path)
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_text = registry_path.read_text(encoding="utf-8").replace(
        f'formal_inner_command = "{FORMAL_INNER_COMMAND}"',
        (
            f'formal_inner_command = "{FORMAL_INNER_COMMAND}"\n'
            'optional_eval_artifacts = ["logs/run.log"]'
        ),
    )
    registry_path.write_text(registry_text, encoding="utf-8")
    experiment_path = repo_root / "experiments" / "demo_topic" / "experimentcode.py"
    experiment_path.write_text(
        experiment_path.read_text(encoding="utf-8")
        + "\n(run_dir / 'logs').mkdir(parents=True, exist_ok=True)\n"
        + "(run_dir / 'logs' / 'run.log').write_text('nested\\nlog', encoding='utf-8')\n",
        encoding="utf-8",
    )
    run_name = "demo_topic_formal_nestedlog_20260406T000000Z"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo_root),
            "--topic",
            "demo_topic",
            "--run-name",
            run_name,
            "--use-registered-command",
            "formal",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    result_dir = repo_root / "experiments" / "demo_topic" / "result" / run_name
    eval_manifest = json.loads((result_dir / "eval_manifest.json").read_text(encoding="utf-8"))
    assert "logs/run.log" in {artifact["relative_path"] for artifact in eval_manifest["artifacts"]}


def test_check_experiment_registry_accepts_valid_registry(tmp_path: Path) -> None:
    """The registry checker should pass for the generated demo registry."""
    repo_root = build_repo(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--repo-root",
            str(repo_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "OK: experiment registry is valid" in result.stdout


def test_check_experiment_registry_accepts_valid_branch_topic(tmp_path: Path) -> None:
    """The registry checker should accept branch-only topic entries."""
    repo_root = build_repo(tmp_path)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Registry Test",
            "-c",
            "user.email=registry-test@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "initial",
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "branch", "experiment/branch-only"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    (repo_root / "notes" / "branches").mkdir(parents=True)
    (repo_root / "notes" / "branches" / "branch_only.md").write_text(
        "# Branch Only\n",
        encoding="utf-8",
    )
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_path.write_text(
        registry_path.read_text(encoding="utf-8")
        + "\n".join(
            [
                "[[branch_topics]]",
                'name = "branch_only"',
                'status = "active"',
                'remote_branch = "experiment/branch-only"',
                'primary_note = "notes/branches/branch_only.md"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--repo-root",
            str(repo_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "OK: experiment registry is valid" in result.stdout


def test_check_experiment_registry_rejects_duplicate_branch_topic_name(
    tmp_path: Path,
) -> None:
    """The registry checker should reject duplicate names across topic tables."""
    repo_root = build_repo(tmp_path)
    (repo_root / "notes" / "branches").mkdir(parents=True)
    (repo_root / "notes" / "branches" / "demo_topic.md").write_text(
        "# Demo Topic Branch\n",
        encoding="utf-8",
    )
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_path.write_text(
        registry_path.read_text(encoding="utf-8")
        + "\n".join(
            [
                "[[branch_topics]]",
                'name = "demo_topic"',
                'status = "active"',
                'remote_branch = "experiment/demo-topic"',
                'primary_note = "notes/branches/demo_topic.md"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--repo-root",
            str(repo_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "duplicate topic name: demo_topic" in result.stdout


def test_check_experiment_registry_defaults_to_repo_root_via_symlink(
    tmp_path: Path,
) -> None:
    """The checker should infer the derived repo root from the invoked symlink path."""
    repo_root = build_repo(tmp_path)
    script_path = repo_root / "tools" / "ci" / "check_experiment_registry.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.symlink_to(CHECK_SCRIPT)

    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert f"repo_root={repo_root}" in result.stdout
    assert "OK: experiment registry is valid" in result.stdout


def test_check_experiment_registry_rejects_recursive_runner_command(tmp_path: Path) -> None:
    """The checker should fail when an inner command recursively calls the wrapper."""
    repo_root = build_repo(tmp_path)
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_text = registry_path.read_text(encoding="utf-8").replace(
        f'smoke_inner_command = "{SMOKE_INNER_COMMAND}"',
        f'smoke_inner_command = "{RECURSIVE_RUNNER_COMMAND}"',
    )
    registry_path.write_text(registry_text, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--repo-root",
            str(repo_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "must not call the managed runner recursively" in result.stdout


def test_check_experiment_registry_rejects_reserved_eval_artifact_pattern(tmp_path: Path) -> None:
    """The registry checker should reject reserved top-level managed artifact patterns."""
    repo_root = build_repo(tmp_path)
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_text = registry_path.read_text(encoding="utf-8").replace(
        'required_eval_artifacts = ["summary.json", "cases.jsonl"]',
        'required_eval_artifacts = ["summary.json", "cases.jsonl", "run.log"]',
    )
    registry_path.write_text(registry_text, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--repo-root",
            str(repo_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "reserved top-level managed artifacts" in result.stdout


def test_create_experiment_topic_scaffolds_directory_and_registry(tmp_path: Path) -> None:
    """The scaffold script should copy the template and append a registry entry."""
    repo_root = build_repo(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(CREATE_TOPIC_SCRIPT),
            "--repo-root",
            str(repo_root),
            "--active-branch",
            "work/new-topic-20260406",
            "new_topic",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    topic_dir = repo_root / "experiments" / "new_topic"
    assert topic_dir.is_dir()
    readme_text = (topic_dir / "README.md").read_text(encoding="utf-8")
    assert "# new_topic" in readme_text
    assert "<topic>" not in readme_text
    registry_text = (repo_root / "experiments" / "registry.toml").read_text(encoding="utf-8")
    assert 'name = "new_topic"' in registry_text
    assert 'active_branch = "work/new-topic-20260406"' in registry_text


def test_sync_experiment_registry_context_updates_branch_scope_and_worktree(tmp_path: Path) -> None:
    """The sync script should update branch and worktree metadata for one topic."""
    repo_root = build_repo(tmp_path)
    workspace_root = repo_root / ".worktrees" / "demo-topic"
    workspace_root.mkdir(parents=True)
    (workspace_root / "WORKTREE_SCOPE.md").write_text("# Scope\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SYNC_CONTEXT_SCRIPT),
            "--repo-root",
            str(repo_root),
            "--workspace-root",
            str(workspace_root),
            "--branch",
            "work/demo-topic-20260406",
            "--branch-note",
            "notes/branches/demo_topic.md",
            "--topic",
            "demo_topic",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    registry_text = (repo_root / "experiments" / "registry.toml").read_text(encoding="utf-8")
    assert 'active_branch = "work/demo-topic-20260406"' in registry_text
    assert 'active_worktree = ".worktrees/demo-topic"' in registry_text
    assert 'scope_file = ".worktrees/demo-topic/WORKTREE_SCOPE.md"' in registry_text
    assert 'branch_note = "notes/branches/demo_topic.md"' in registry_text
