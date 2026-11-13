# @dependency-start
# contract test
# responsibility Tests the standalone AgentCanon GitHub workflow convention checker.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/github_workflow_check.rs native checker
# upstream implementation ../../.github/workflows/agent-runtime-dashboard.yml dashboard event contract
# upstream implementation ../../.github/workflows/agent-canon-native-release.yml native publication planning
# downstream implementation ../../.github/workflows/agent-canon-static-gates.yml standalone gate workflow
# @dependency-end

"""Tests for standalone AgentCanon GitHub workflow conventions."""

from __future__ import annotations

import os
import subprocess
import tempfile
import tomllib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")
RUNTIME_DASHBOARD_WORKFLOW = (
    ROOT / ".github" / "workflows" / "agent-runtime-dashboard.yml"
)


def _native_cli() -> str:
    if not AGENT_CANON_CLI:
        raise RuntimeError("AGENT_CANON_CLI must select the current native executable")
    executable = Path(AGENT_CANON_CLI)
    if (
        not executable.is_absolute()
        or not executable.is_file()
        or not os.access(executable, os.X_OK)
    ):
        raise RuntimeError("AGENT_CANON_CLI must select an absolute executable file")
    return str(executable)


def test_native_build_toolchain_matches_canonical_image_pin() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/agent-canon-native-release.yml").read_text()
    )
    manifest = tomllib.loads(
        (ROOT / "bootstrap/container/image/dependencies.toml").read_text(
            encoding="utf-8"
        )
    )
    rust_toolchain = next(
        record["version"]
        for record in manifest["records"]
        if record.get("id") == "rust-toolchain"
    )
    compiling_jobs = {"prepare", "build", "publish-release"}

    assert {
        workflow["jobs"][job]["env"]["RUSTUP_TOOLCHAIN"] for job in compiling_jobs
    } == {rust_toolchain}


def test_native_publication_plan_honors_the_event_and_manual_choice() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/agent-canon-native-release.yml").read_text()
    )
    step = next(
        value
        for value in workflow["jobs"]["prepare"]["steps"]
        if value.get("id") == "plan"
    )
    cases = (
        ("main", "push", "refs/heads/main", "false", "", True, "v1.2.3"),
        ("pr", "pull_request", "refs/pull/1/merge", "false", "", False, ""),
        ("tag", "push", "refs/tags/v1.2.3", "false", "", True, "v1.2.3"),
        (
            "manual-check-tag",
            "workflow_dispatch",
            "refs/tags/v1.2.3",
            "false",
            "",
            False,
            "",
        ),
        (
            "manual-publish",
            "workflow_dispatch",
            "refs/heads/main",
            "true",
            "v1.2.3",
            True,
            "v1.2.3",
        ),
        (
            "manual-publish-tag",
            "workflow_dispatch",
            "refs/tags/v1.2.3",
            "true",
            "",
            True,
            "v1.2.3",
        ),
        ("wrong-tag", "push", "refs/tags/v9.9.9", "false", "", None, ""),
        ("missing-tag", "workflow_dispatch", "refs/heads/main", "true", "", None, ""),
    )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        commands = root / "bin"
        commands.mkdir()
        cargo = commands / "cargo"
        cargo.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'if [[ "$#" -lt 6 || "$1" != run || "$2" != --locked ||\n'
            '      "$3" != --manifest-path ||\n'
            '      "$4" != tools/runtime/dispatch/agent-canon/Cargo.toml ||\n'
            '      "$5" != -- ]]; then\n'
            "  echo 'unexpected cargo invocation in native workflow test' >&2\n"
            "  exit 2\n"
            "fi\n"
            "shift 5\n"
            'exec "${AGENT_CANON_CLI:?}" "$@"\n',
            encoding="utf-8",
        )
        cargo.chmod(0o755)
        manifest = root / "tools/runtime/dispatch/agent-canon/Cargo.toml"
        manifest.parent.mkdir(parents=True)
        manifest.write_text('[package]\nversion = "1.2.3"\n')
        for args in (
            ["init", "-q"],
            ["config", "user.name", "Plan Fixture"],
            ["config", "user.email", "plan@example.invalid"],
            ["add", "tools"],
            ["commit", "-qm", "baseline"],
            ["update-ref", "refs/remotes/origin/main", "HEAD"],
        ):
            subprocess.run(
                ["git", "-C", str(root), *args], check=True, capture_output=True
            )

        for name, event, ref, requested, tag_input, published, tag in cases:
            output = root / (name + ".output")
            env = {
                **os.environ,
                "AGENT_CANON_CLI": _native_cli(),
                "PATH": str(commands) + os.pathsep + os.environ.get("PATH", ""),
                "GITHUB_WORKSPACE": str(root),
                "GITHUB_EVENT_NAME": event,
                "GITHUB_REF": ref,
                "GITHUB_REF_NAME": ref.rsplit("/", 1)[-1],
                "GITHUB_OUTPUT": str(output),
                "PUBLISH_REQUEST": requested,
                "RELEASE_TAG_INPUT": tag_input,
                "MATRIX_JSON": step["env"]["MATRIX_JSON"],
            }
            result = subprocess.run(
                ["bash", "-c", step["run"]],
                cwd=ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            if published is None:
                assert result.returncode != 0, name
                assert not output.exists(), name
            else:
                assert result.returncode == 0, (name, result.stderr)
                values = dict(
                    line.split("=", 1) for line in output.read_text().splitlines()
                )
                assert values["publish"] == str(published).lower(), name
                assert values["tag"] == tag, name
                assert values["version"] == "1.2.3", name


def test_windows_rebuild_comparison_rejects_changed_or_missing_output() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/agent-canon-native-release.yml").read_text()
    )
    step = next(
        value
        for value in workflow["jobs"]["build"]["steps"]
        if value["name"] == "Rebuild Windows archives and require byte equality"
    )
    assert "native-release compare-reproducible" in step["run"]
    native_cli = _native_cli()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for changed in (
            None,
            "agent-canon.exe",
            "release.zip",
            "release.zip.sha256",
            "missing",
        ):
            original = root / "original-build"
            rebuilt = root / "rebuilt-build"
            packages = root / "packages"
            rebuilt_packages = root / "rebuilt-packages"
            pairs = [
                (original / "agent-canon.exe", rebuilt / "agent-canon.exe"),
                (packages / "release.zip", rebuilt_packages / "release.zip"),
                (packages / "release.tar.gz", rebuilt_packages / "release.tar.gz"),
                (
                    packages / "release.zip.sha256",
                    rebuilt_packages / "release.zip.sha256",
                ),
                (
                    packages / "release.tar.gz.sha256",
                    rebuilt_packages / "release.tar.gz.sha256",
                ),
            ]
            for first, second in pairs:
                first.parent.mkdir(parents=True, exist_ok=True)
                second.parent.mkdir(parents=True, exist_ok=True)
                first.write_bytes(b"same bytes\n")
                second.write_bytes(b"same bytes\n")
                if second.name == changed:
                    second.write_bytes(b"diff bytes\n")
            if changed == "missing":
                (rebuilt_packages / "release.tar.gz").unlink()
            result = subprocess.run(
                [
                    native_cli,
                    "native-release",
                    "compare-reproducible",
                    "--binary",
                    str(original / "agent-canon.exe"),
                    "--rebuilt-binary",
                    str(rebuilt / "agent-canon.exe"),
                    "--packages",
                    str(packages),
                    "--rebuilt-packages",
                    str(rebuilt_packages),
                ],
                cwd=ROOT,
                env=os.environ.copy(),
                capture_output=True,
                text=True,
                check=False,
            )
            if changed is None:
                assert result.returncode == 0, result.stderr
                assert len(result.stdout.splitlines()) == 5
            else:
                assert result.returncode != 0, changed
                expected = (
                    "package file set differs" if changed == "missing" else changed
                )
                assert expected in result.stderr


def run_checker(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_native_cli(), "check-github-workflows", "--root", str(root)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_native_checker_cli_help_and_argparse_root_spellings() -> None:
    for option in ("-h", "--help"):
        help_result = subprocess.run(
            [_native_cli(), "check-github-workflows", option],
            check=False,
            capture_output=True,
            text=True,
        )
        assert help_result.returncode == 0, help_result.stderr
        assert "usage:" in help_result.stdout
        assert "--root ROOT" in help_result.stdout

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        copy_required_surfaces(root)
        for root_args in ((f"--root={root}",), ("--r", str(root))):
            result = subprocess.run(
                [_native_cli(), "check-github-workflows", *root_args],
                check=False,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            assert "GITHUB_WORKFLOWS_CHECKED=0" in result.stdout


def copy_required_surfaces(root: Path) -> None:
    """Copy only standalone surfaces consumed by the checker."""
    for relative in (
        ".github/AGENTS.md",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",
        "templates/documents/github/pull-request/agent_canon.md",
        "agents/skills/agent-canon-update.md",
        "README.md",
    ):
        source = ROOT / relative
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())


def write_workflow(root: Path, text: str) -> None:
    path = root / ".github" / "workflows" / "ci.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_dashboard_workflow(root: Path, text: str) -> Path:
    """Write a dashboard workflow fixture for the focused header checker."""
    path = root / ".github" / "workflows" / "agent-runtime-dashboard.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


VALID_WORKFLOW = """\
name: CI
on: [push]
permissions:
  contents: read
concurrency:
  group: ci-${{ github.ref }}
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
        with:
          persist-credentials: false
      - run: echo standalone
"""


def test_standalone_repository_passes() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        copy_required_surfaces(root)
        write_workflow(root, VALID_WORKFLOW)
        result = run_checker(root)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "GITHUB_WORKFLOW_TOOL_EXIT=actionlint code=0" in result.stdout
        assert "GITHUB_WORKFLOW_TOOL_EXIT=zizmor code=0" in result.stdout
        assert "GITHUB_WORKFLOWS=pass" in result.stdout


def test_checker_only_scans_standalone_workflows() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        copy_required_surfaces(root)
        write_workflow(root, VALID_WORKFLOW)
        vendor = root / "vendor" / "agent-canon" / ".github" / "workflows"
        vendor.mkdir(parents=True)
        (vendor / "obsolete.yml").write_text("not: yaml\n", encoding="utf-8")
        result = run_checker(root)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "GITHUB_WORKFLOWS_CHECKED=1" in result.stdout


def test_native_actionlint_failure_is_visible() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        copy_required_surfaces(root)
        write_workflow(root, "name: Broken\njobs: [\n")
        result = run_checker(root)
        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert "GITHUB_WORKFLOW_TOOL_EXIT=actionlint code=" in output
        assert "GITHUB_WORKFLOW_TOOL_EXIT=actionlint code=0" not in output
        assert "GITHUB_WORKFLOWS=fail" in output


def test_native_zizmor_rejects_default_checkout_credentials_in_artifact() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        copy_required_surfaces(root)
        vulnerable_workflow = VALID_WORKFLOW.replace(
            "        with:\n          persist-credentials: false\n", ""
        ).replace(
            "      - run: echo standalone\n",
            "      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2\n"
            "        with:\n"
            "          name: checkout-git-config\n"
            "          path: .\n"
            "          include-hidden-files: true\n",
        )
        write_workflow(root, vulnerable_workflow)
        result = run_checker(root)
        output = result.stdout + result.stderr
        assert result.returncode != 0, f"checker args={result.args!r}\n{output}"
        assert "artipacked" in output
        assert "GITHUB_WORKFLOW_TOOL_EXIT=zizmor code=" in output
        assert "GITHUB_WORKFLOW_TOOL_EXIT=zizmor code=0" not in output


def test_static_gate_uses_bootstrap_container_units() -> None:
    path = ROOT / ".github" / "workflows" / "agent-canon-static-gates.yml"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    runs = [
        str(step.get("run", ""))
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
    ]
    assert not any("check_agent_canon_pr.sh" in run for run in runs)
    assert sum("run_standalone_static_gate_unit.sh" in run for run in runs) == 1


def test_no_submodule_checkout_helper_remains() -> None:
    forbidden = (
        ROOT / ".github" / "scripts" / "checkout_agent_canon_submodule.sh",
        ROOT / "tools" / "ci" / "checkout_agent_canon_submodule.sh",
    )
    assert all(not path.exists() for path in forbidden)
    checker = ROOT / "tools/runtime/dispatch/agent-canon/src/github_workflow_check.rs"
    assert "checkout_agent_canon_submodule" not in checker.read_text(encoding="utf-8")


def test_workflows_do_not_restore_workspace_runtime_defaults() -> None:
    """GitHub workflows keep runtime state at each checked-out install root."""
    workflow_root = ROOT / ".github" / "workflows"
    for path in workflow_root.glob("*.y*ml"):
        assert "workspace/agent-canon-runtime" not in path.read_text(encoding="utf-8")


def test_runtime_dashboard_preserves_pr_context_and_skips_diagnostics_for_prs() -> None:
    """Keep the dashboard PR check while diagnostics run on manual/schedule events."""
    workflow = yaml.load(
        RUNTIME_DASHBOARD_WORKFLOW.read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )

    events = set(workflow["on"])
    assert events == {"pull_request", "workflow_dispatch", "schedule"}
    assert "dashboard" in workflow["jobs"]
    dashboard_job = workflow["jobs"]["dashboard"]
    assert dashboard_job["if"] == "github.event_name != 'pull_request'"


def test_dashboard_header_checker_rejects_missing_pr_trigger_or_job_guard() -> None:
    """Require both the PR context and the diagnostic exclusion at their owner."""
    source = RUNTIME_DASHBOARD_WORKFLOW.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        copy_required_surfaces(root)
        write_workflow(root, VALID_WORKFLOW)
        write_dashboard_workflow(root, source)
        assert run_checker(root).returncode == 0

        ordered_job = (
            "  dashboard:\n"
            "    if: github.event_name != 'pull_request'\n"
            "    runs-on: ubuntu-latest\n"
        )
        reordered_job = (
            "  dashboard:\n"
            "    runs-on: ubuntu-latest\n"
            "    if: github.event_name != 'pull_request'\n"
        )
        reordered = source.replace(ordered_job, reordered_job, 1)
        assert reordered != source
        write_dashboard_workflow(root, reordered)
        assert run_checker(root).returncode == 0

        mutations = (
            (
                "missing_text:pull_request:",
                "  pull_request:\n",
                "",
            ),
            (
                "missing_dashboard_pr_job_exclusion",
                "jobs:\n  dashboard:\n    if: github.event_name != 'pull_request'\n",
                "jobs:\n  dashboard:\n",
            ),
        )
        for expected_message, removed_text, replacement in mutations:
            mutated = source.replace(removed_text, replacement, 1)
            assert mutated != source
            write_dashboard_workflow(root, mutated)
            result = run_checker(root)
            assert expected_message in result.stdout + result.stderr
