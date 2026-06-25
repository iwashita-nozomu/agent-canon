# @dependency-start
# contract test
# responsibility Tests test run managed experiment behavior.
# upstream design ../../tools/README.md validated automation surface
# upstream implementation ../../tools/ci/check_experiment_registry.py checker under test
# @dependency-end

"""Tests for the managed experiment run helper."""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import cast

CHECK_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "ci"
    / "check_experiment_registry.py"
)
CREATE_TOPIC_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "experiments"
    / "create_experiment_topic.py"
)
SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "experiments"
    / "run_managed_experiment.py"
)
SYNC_CONTEXT_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "experiments"
    / "sync_experiment_registry_context.py"
)
CANONICAL_ENTRYPOINT = "experiments/demo_topic/run.py"
DEFAULT_INNER_COMMAND = (
    f"python3 {CANONICAL_ENTRYPOINT} --run-dir {{run_dir}} "
    "--config {config_path} --mode default"
)
FORMAL_INNER_COMMAND = (
    f"python3 {CANONICAL_ENTRYPOINT} --run-dir {{run_dir}} "
    "--config {config_path} --mode formal"
)
RECURSIVE_RUNNER_COMMAND = (
    "python3 tools/experiments/run_managed_experiment.py --topic demo_topic"
)


def create_fake_repo_dirs(repo_root: Path) -> None:
    """Create the minimal fake repo directory layout."""
    (
        repo_root
        / "vendor"
        / "agent-canon"
        / "experiments"
        / "_template"
        / "result"
    ).mkdir(parents=True)
    (repo_root / "experiments" / "demo_topic" / "result").mkdir(parents=True)
    (repo_root / "experiments" / "report").mkdir(parents=True)
    (repo_root / "tools" / "experiments").mkdir(parents=True)


def write_template_topic(repo_root: Path) -> None:
    """Write the fake template experiment topic."""
    template_dir = repo_root / "vendor" / "agent-canon" / "experiments" / "_template"
    (template_dir / "README.md").write_text(
        "# Experiment Topic Template\n\n"
        "registered command: `python3 tools/experiments/run_managed_experiment.py "
        "--topic <topic> --use-registered-command <registered-command>`\n",
        encoding="utf-8",
    )
    (template_dir / "cases.py").write_text(
        "from __future__ import annotations\n",
        encoding="utf-8",
    )
    (template_dir / "config.yaml").write_text(
        "mode: template\n",
        encoding="utf-8",
    )
    (template_dir / "run.py").write_text(
        "from __future__ import annotations\n",
        encoding="utf-8",
    )
    (template_dir / "result" / "README.md").write_text(
        "# Result Directory\n",
        encoding="utf-8",
    )


def write_demo_topic_base(repo_root: Path) -> None:
    """Write non-executable fake demo topic files."""
    (repo_root / "experiments" / "demo_topic" / "README.md").write_text(
        "# Demo Topic\n",
        encoding="utf-8",
    )
    (repo_root / "experiments" / "demo_topic" / "config.yaml").write_text(
        "mode: demo\n",
        encoding="utf-8",
    )
    (repo_root / "experiments" / "demo_topic" / "cases.py").write_text(
        "from __future__ import annotations\n",
        encoding="utf-8",
    )
    (repo_root / "tools" / "experiments" / "run_managed_experiment.py").write_text(
        "# placeholder\n",
        encoding="utf-8",
    )


def demo_run_script_text() -> str:
    """Return the fake demo topic runner source."""
    return (
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
                'parser.add_argument("--config", required=True)',
                'parser.add_argument("--mode", required=True)',
                "args = parser.parse_args()",
                "run_dir = Path(args.run_dir)",
                "run_dir.mkdir(parents=True, exist_ok=True)",
                "config = json.loads(Path(args.config).read_text(encoding='utf-8'))",
                "(run_dir / 'marker.txt').write_text(args.mode, encoding='utf-8')",
                "(run_dir / 'summary.json').write_text(",
                (
                    "    json.dumps({'status': 'completed', 'mode': args.mode, "
                    "'config_topic': config['topic']}, "
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
        + "\n"
    )


def write_demo_runner(repo_root: Path) -> None:
    """Write the fake demo topic executable runner."""
    (repo_root / "experiments" / "demo_topic" / "run.py").write_text(
        demo_run_script_text(),
        encoding="utf-8",
    )


def write_demo_registry(repo_root: Path) -> None:
    """Write the fake experiment registry."""
    (repo_root / "experiments" / "registry.toml").write_text(
        "\n".join(
            [
                "schema_version = 1",
                "",
                "[defaults]",
                'managed_runner = "tools/experiments/run_managed_experiment.py"',
                'report_root = "experiments/report"',
                'integration_branch = "main"',
                'topic_template_dir = "vendor/agent-canon/experiments/_template"',
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
                f'default_inner_command = "{DEFAULT_INNER_COMMAND}"',
                f'formal_inner_command = "{FORMAL_INNER_COMMAND}"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def init_fake_git_repo(repo_root: Path) -> None:
    """Initialize git metadata for the fake repo."""
    subprocess.run(
        ["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True
    )


def build_repo(tmp_path: Path) -> Path:
    """Create a minimal fake repo layout for the helper."""
    repo_root = tmp_path / "repo"
    create_fake_repo_dirs(repo_root)
    write_template_topic(repo_root)
    write_demo_topic_base(repo_root)
    write_demo_runner(repo_root)
    write_demo_registry(repo_root)
    init_fake_git_repo(repo_root)
    return repo_root


def load_json(path: Path) -> dict[str, object]:
    """Load one JSON object fixture artifact."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return cast(dict[str, object], payload)


def require_json_object(value: object) -> dict[str, object]:
    """Return a JSON object from a fixture value."""
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def require_json_list(value: object) -> list[object]:
    """Return a JSON list from a fixture value."""
    assert isinstance(value, list)
    return cast(list[object], value)


def require_string(value: object) -> str:
    """Return a string from a fixture value."""
    assert isinstance(value, str)
    return value


def artifact_relative_paths(manifest: dict[str, object]) -> set[str]:
    """Return relative paths from an artifact manifest-like object."""
    paths: set[str] = set()
    for artifact in require_json_list(manifest["artifacts"]):
        artifact_object = require_json_object(artifact)
        paths.add(require_string(artifact_object["relative_path"]))
    return paths


def artifacts_by_relative_path(
    manifest: dict[str, object],
) -> dict[str, dict[str, object]]:
    """Return artifact objects keyed by relative path."""
    artifacts: dict[str, dict[str, object]] = {}
    for artifact in require_json_list(manifest["artifacts"]):
        artifact_object = require_json_object(artifact)
        artifacts[require_string(artifact_object["relative_path"])] = artifact_object
    return artifacts


def load_startup_events(result_dir: Path) -> list[dict[str, object]]:
    """Load managed startup chronology events."""
    return [
        json.loads(line)
        for line in (result_dir / "logs" / "startup.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]


def assert_manifest_records_reproducibility_paths(
    manifest: dict[str, object],
    result_dir: Path,
) -> None:
    """Check manifest paths for managed reproducibility artifacts."""
    assert manifest["log_dir"] == str(result_dir / "logs")
    assert manifest["config_path"] == str(result_dir / "config.json")
    assert manifest["config_source_path"] == str(result_dir / "config_source.yaml")
    assert manifest["artifact_manifest_path"] == str(result_dir / "artifact_manifest.json")
    assert manifest["command_manifest_path"] == str(result_dir / "command.json")
    assert manifest["environment_manifest_path"] == str(result_dir / "environment.json")
    assert manifest["source_snapshot_path"] == str(result_dir / "source_snapshot.json")
    assert manifest["stdout_log_path"] == str(result_dir / "logs" / "stdout.log")
    assert manifest["stderr_log_path"] == str(result_dir / "logs" / "stderr.log")
    assert manifest["startup_log_path"] == str(result_dir / "logs" / "startup.jsonl")


def assert_managed_run_files_exist(result_dir: Path) -> None:
    """Check managed run files are created before closeout."""
    for relative_path in (
        "config.json",
        "config_source.yaml",
        "command.json",
        "environment.json",
        "source_snapshot.json",
        "artifact_manifest.json",
        "run.log",
        "logs/startup.jsonl",
        "logs/stdout.log",
        "logs/stderr.log",
    ):
        assert (result_dir / relative_path).is_file()


def assert_default_command_manifest(
    command_manifest: dict[str, object],
    result_dir: Path,
) -> None:
    """Check the saved resolved command for the default run."""
    assert command_manifest["command"] == [
        "python3",
        CANONICAL_ENTRYPOINT,
        "--run-dir",
        str(result_dir),
        "--config",
        str(result_dir / "config.json"),
        "--mode",
        "default",
    ]


def assert_source_snapshot_covers_topic(
    source_snapshot: dict[str, object],
) -> None:
    """Check the source snapshot includes rerun inputs."""
    file_records = require_json_list(source_snapshot["files"])
    assert {
        require_string(require_json_object(file_record)["relative_path"])
        for file_record in file_records
    } >= {
        "experiments/demo_topic/README.md",
        "experiments/demo_topic/cases.py",
        "experiments/demo_topic/config.yaml",
        "experiments/demo_topic/run.py",
        "experiments/registry.toml",
    }


def assert_artifact_manifest_covers_success_run(
    artifact_manifest: dict[str, object],
) -> None:
    """Check final digest inventory covers managed and produced artifacts."""
    assert artifact_relative_paths(artifact_manifest) >= {
        "command.json",
        "config.json",
        "config_source.yaml",
        "environment.json",
        "eval_manifest.json",
        "logs/startup.jsonl",
        "logs/stderr.log",
        "logs/stdout.log",
        "run.log",
        "run_manifest.json",
        "source_snapshot.json",
        "summary.json",
        "cases.jsonl",
    }


def test_run_managed_experiment_uses_registered_command_and_writes_manifest(
    tmp_path: Path,
) -> None:
    """The helper should create canonical files for one successful registered run."""
    repo_root = build_repo(tmp_path)
    run_name = "demo_topic_default_20260406T000000Z"

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
            "default",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    result_dir = repo_root / "experiments" / "demo_topic" / "result" / run_name
    manifest = load_json(result_dir / "run_manifest.json")
    eval_manifest = load_json(result_dir / "eval_manifest.json")
    assert manifest["status"] == "completed"
    assert manifest["exit_code"] == 0
    assert manifest["command_source"] == "registered:default"
    assert manifest["registered_command_match"] == "default"
    registry = require_json_object(manifest["registry"])
    assert registry["canonical_entrypoint"] == CANONICAL_ENTRYPOINT
    assert_manifest_records_reproducibility_paths(manifest, result_dir)
    source_config = require_json_object(manifest["source_config"])
    config = require_json_object(manifest["config"])
    config_paths = require_json_object(config["paths"])
    eval_artifacts = require_json_object(manifest["eval_artifacts"])
    assert source_config["status"] == "copied"
    assert config_paths["log_dir"] == str(result_dir / "logs")
    assert config_paths["config"] == str(result_dir / "config.json")
    assert config_paths["source_config"] == str(result_dir / "config_source.yaml")
    assert eval_artifacts["collected_artifact_count"] == 3
    assert eval_artifacts["missing_required_patterns"] == []
    assert_managed_run_files_exist(result_dir)
    assert (result_dir / "marker.txt").read_text(encoding="utf-8") == "default"
    assert eval_manifest["missing_required_patterns"] == []
    collected_paths = artifact_relative_paths(eval_manifest)
    assert collected_paths == {"summary.json", "cases.jsonl", "config.json"}
    command_manifest = load_json(result_dir / "command.json")
    environment_manifest = load_json(result_dir / "environment.json")
    source_snapshot = load_json(result_dir / "source_snapshot.json")
    artifact_manifest = load_json(result_dir / "artifact_manifest.json")
    startup_events = load_startup_events(result_dir)
    assert_default_command_manifest(command_manifest, result_dir)
    assert environment_manifest["policy"] == "full_environment_with_key_secret_redaction"
    environment_values = require_json_object(environment_manifest["values"])
    command_source_files = require_json_list(source_snapshot["command_source_files"])
    external_file_count = source_snapshot["external_file_count"]
    git_snapshot = require_json_object(source_snapshot["git"])
    assert "EXPERIMENT_RUN_NAME" in environment_values
    assert "experiments/demo_topic/run.py" in command_source_files
    assert isinstance(external_file_count, int)
    assert external_file_count >= 1
    assert git_snapshot["dirty"] is True
    assert_source_snapshot_covers_topic(source_snapshot)
    assert_artifact_manifest_covers_success_run(artifact_manifest)
    assert [event["event"] for event in startup_events] == [
        "initialized",
        "command_start",
        "command_exit",
    ]
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
        repo_root
        / "experiments"
        / "demo_topic"
        / "result"
        / run_name
        / "run_manifest.json"
    )
    eval_manifest_path = (
        repo_root
        / "experiments"
        / "demo_topic"
        / "result"
        / run_name
        / "eval_manifest.json"
    )
    manifest = load_json(manifest_path)
    eval_manifest = load_json(eval_manifest_path)
    eval_artifacts = require_json_object(manifest["eval_artifacts"])
    assert manifest["status"] == "failed"
    assert manifest["exit_code"] == 7
    assert manifest["command_source"] == "manual"
    assert (manifest_path.parent / "artifact_manifest.json").is_file()
    assert (manifest_path.parent / "logs" / "stdout.log").is_file()
    assert (manifest_path.parent / "logs" / "stderr.log").is_file()
    assert eval_artifacts["missing_required_patterns"] == [
        "summary.json",
        "cases.jsonl",
    ]
    assert eval_manifest["artifact_count"] == 1
    assert artifact_relative_paths(eval_manifest) == {"config.json"}


def test_run_managed_experiment_records_command_start_failure(
    tmp_path: Path,
) -> None:
    """The helper should close manifests even when the command cannot start."""
    repo_root = build_repo(tmp_path)
    run_name = "demo_topic_start_fail_20260406T000000Z"

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
            str(repo_root / "missing-command"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 127
    result_dir = repo_root / "experiments" / "demo_topic" / "result" / run_name
    manifest = load_json(result_dir / "run_manifest.json")
    eval_manifest = load_json(result_dir / "eval_manifest.json")
    stderr_log = (result_dir / "logs" / "stderr.log").read_text(encoding="utf-8")
    startup_events = load_startup_events(result_dir)
    eval_artifacts = require_json_object(manifest["eval_artifacts"])
    assert manifest["status"] == "failed"
    assert manifest["exit_code"] == 127
    assert eval_artifacts["missing_required_patterns"] == [
        "summary.json",
        "cases.jsonl",
    ]
    assert eval_manifest["artifact_count"] == 1
    assert "command_start_error=FileNotFoundError" in stderr_log
    assert [event["event"] for event in startup_events] == [
        "initialized",
        "command_start",
        "command_exit",
    ]


def test_run_managed_experiment_fails_preflight_when_source_config_is_missing(
    tmp_path: Path,
) -> None:
    """The helper should stop before child launch when config.yaml is absent."""
    repo_root = build_repo(tmp_path)
    (repo_root / "experiments" / "demo_topic" / "config.yaml").unlink()
    run_name = "demo_topic_missing_config_20260406T000000Z"

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
            "default",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "missing required source config.yaml" in result.stderr
    result_dir = repo_root / "experiments" / "demo_topic" / "result" / run_name
    manifest = load_json(result_dir / "run_manifest.json")
    eval_manifest = load_json(result_dir / "eval_manifest.json")
    artifact_manifest = load_json(result_dir / "artifact_manifest.json")
    startup_events = load_startup_events(result_dir)
    source_config = require_json_object(manifest["source_config"])
    preflight_error = require_json_object(manifest["preflight_error"])
    assert manifest["status"] == "failed"
    assert manifest["exit_code"] == 2
    assert source_config["status"] == "missing"
    assert preflight_error["kind"] == "missing_source_config"
    assert eval_manifest["artifact_count"] == 1
    assert [event["event"] for event in startup_events] == [
        "initialized",
        "preflight_failed",
    ]
    assert "logs/startup.jsonl" in artifact_relative_paths(artifact_manifest)


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
    eval_manifest = load_json(result_dir / "eval_manifest.json")
    artifacts = artifacts_by_relative_path(eval_manifest)
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
    experiment_path = repo_root / "experiments" / "demo_topic" / "run.py"
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
    manifest = load_json(result_dir / "run_manifest.json")
    eval_manifest = load_json(result_dir / "eval_manifest.json")
    assert manifest["status"] == "completed"
    artifacts = artifacts_by_relative_path(eval_manifest)
    assert "binary.txt" in artifacts
    assert artifacts["binary.txt"]["line_count"] == 1


def test_run_managed_experiment_excludes_managed_files_from_optional_wildcards(
    tmp_path: Path,
) -> None:
    """The helper should keep managed files out of eval wildcards."""
    repo_root = build_repo(tmp_path)
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_text = registry_path.read_text(encoding="utf-8").replace(
        f'formal_inner_command = "{FORMAL_INNER_COMMAND}"',
        (
            f'formal_inner_command = "{FORMAL_INNER_COMMAND}"\n'
            'optional_eval_artifacts = ["*.json", "logs/*.log", "logs/*.jsonl"]'
        ),
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
    eval_manifest = load_json(result_dir / "eval_manifest.json")
    collected_paths = artifact_relative_paths(eval_manifest)
    assert "summary.json" in collected_paths
    assert "run_manifest.json" not in collected_paths
    assert "eval_manifest.json" not in collected_paths
    assert "artifact_manifest.json" not in collected_paths
    assert "logs/startup.jsonl" not in collected_paths
    assert "logs/stdout.log" not in collected_paths
    assert "logs/stderr.log" not in collected_paths


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
    experiment_path = repo_root / "experiments" / "demo_topic" / "run.py"
    experiment_path.write_text(
        experiment_path.read_text(encoding="utf-8")
        + "\n(run_dir / 'logs' / 'run.log').write_text('nested\\nlog', encoding='utf-8')\n",
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
    eval_manifest = load_json(result_dir / "eval_manifest.json")
    assert "logs/run.log" in artifact_relative_paths(eval_manifest)


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


def test_check_experiment_registry_rejects_recursive_runner_command(
    tmp_path: Path,
) -> None:
    """The checker should fail when an inner command recursively calls the wrapper."""
    repo_root = build_repo(tmp_path)
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_text = registry_path.read_text(encoding="utf-8").replace(
        f'default_inner_command = "{DEFAULT_INNER_COMMAND}"',
        f'default_inner_command = "{RECURSIVE_RUNNER_COMMAND}"',
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


def test_check_experiment_registry_accepts_command_without_run_dir(
    tmp_path: Path,
) -> None:
    """The registry checker should allow a direct entrypoint command."""
    repo_root = build_repo(tmp_path)
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_text = registry_path.read_text(encoding="utf-8").replace(
        f'default_inner_command = "{DEFAULT_INNER_COMMAND}"',
        (
            f'default_inner_command = "/usr/bin/python /workspace/'
            f'{CANONICAL_ENTRYPOINT} --config {{config_path}}"'
        ),
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

    assert result.returncode == 0
    assert "OK: experiment registry is valid" in result.stdout


def test_check_experiment_registry_rejects_command_without_config_path(
    tmp_path: Path,
) -> None:
    """The registry checker should require commands to consume config snapshots."""
    repo_root = build_repo(tmp_path)
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_text = registry_path.read_text(encoding="utf-8").replace(
        f'default_inner_command = "{DEFAULT_INNER_COMMAND}"',
        f'default_inner_command = "/usr/bin/python /workspace/{CANONICAL_ENTRYPOINT}"',
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
    assert "must include {config_path}" in result.stdout


def test_check_experiment_registry_rejects_non_topic_local_entrypoint(
    tmp_path: Path,
) -> None:
    """The registry checker should require experiments/<topic>/run.py entrypoints."""
    repo_root = build_repo(tmp_path)
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_text = registry_path.read_text(encoding="utf-8").replace(
        f'canonical_entrypoint = "{CANONICAL_ENTRYPOINT}"',
        'canonical_entrypoint = "python/package/experiment.py"',
    )
    registry_text = registry_text.replace(
        CANONICAL_ENTRYPOINT, "python/package/experiment.py"
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
    assert "canonical_entrypoint must be the topic-local run.py" in result.stdout


def test_check_experiment_registry_rejects_reserved_eval_artifact_pattern(
    tmp_path: Path,
) -> None:
    """The registry checker should reject reserved managed artifact patterns."""
    repo_root = build_repo(tmp_path)
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_text = registry_path.read_text(encoding="utf-8").replace(
        'required_eval_artifacts = ["summary.json", "cases.jsonl"]',
        (
            'required_eval_artifacts = ["summary.json", "cases.jsonl", '
            '"run.log", "logs/stdout.log"]'
        ),
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
    assert "reserved managed artifacts" in result.stdout


def test_create_experiment_topic_scaffolds_directory_and_registry(
    tmp_path: Path,
) -> None:
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
    registry_text = (repo_root / "experiments" / "registry.toml").read_text(
        encoding="utf-8"
    )
    assert 'name = "new_topic"' in registry_text
    assert 'active_branch = "work/new-topic-20260406"' in registry_text
    registry_data = tomllib.loads(registry_text)
    new_topic = next(
        topic for topic in registry_data["topics"] if topic["name"] == "new_topic"
    )
    assert "formal_inner_command" not in new_topic
    assert "EXPERIMENT_CONFIG_PATH" not in new_topic["default_inner_command"]


def test_sync_experiment_registry_context_updates_branch_scope_and_worktree(
    tmp_path: Path,
) -> None:
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
    registry_text = (repo_root / "experiments" / "registry.toml").read_text(
        encoding="utf-8"
    )
    assert 'active_branch = "work/demo-topic-20260406"' in registry_text
    assert 'active_worktree = ".worktrees/demo-topic"' in registry_text
    assert 'scope_file = ".worktrees/demo-topic/WORKTREE_SCOPE.md"' in registry_text
    assert 'branch_note = "notes/branches/demo_topic.md"' in registry_text
