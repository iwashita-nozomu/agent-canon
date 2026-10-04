# @dependency-start
# contract test
# responsibility Verifies standalone static-gate unit ownership, canonical selection, workflow activation, and full-confidence parity.
# upstream implementation ../../tools/validation/semantic/path/classify_path_risk.py canonical selector and unit mapping
# upstream implementation ../../tools/validation/ci/runners/run_standalone_static_gate_unit.sh unit executor
# upstream implementation ../../tools/validation/ci/checks/check_agent_canon_pr.sh manual full-confidence aggregate
# upstream implementation ../../.github/workflows/agent-canon-static-gates.yml remote selected-unit shared runtime
# @dependency-end

from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path

import pytest
import yaml

from tools.validation.semantic.path.classify_path_risk import STATIC_GATE_UNITS

ROOT = Path(__file__).resolve().parents[2]
SELECTOR = ROOT / "tools/validation/semantic/path/classify_path_risk.py"
RUNNER = ROOT / "tools/validation/ci/runners/run_standalone_static_gate_unit.sh"
FULL_WRAPPER = ROOT / "tools/validation/ci/checks/check_agent_canon_pr.sh"
WORKFLOW = ROOT / ".github/workflows/agent-canon-static-gates.yml"


def workflow() -> dict:
    """Load strings without YAML 1.1 interpreting the Actions `on` key as true."""
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def step(name: str) -> dict:
    return next(
        item for item in workflow()["jobs"]["static-gates"]["steps"]
        if item["name"] == name
    )


def run_shell(script: str, *, root: Path, **environment: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        cwd=root, env={**os.environ, **environment}, capture_output=True,
        text=True, check=False,
    )


def selected_units(*paths: str) -> tuple[str, ...]:
    result = subprocess.run(
        ["python3", str(SELECTOR), "--format", "json",
         *(arg for path in paths for arg in ("--path", path))],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    return tuple(json.loads(result.stdout)["units"])


@pytest.mark.parametrize(("paths", "units"), [
    (("documents/design/example.md",), ("docs",)),
    (("tools/analysis/example.py",), ("contracts",)),
    (("tools/runtime/dispatch/agent-canon/src/main.rs",), ("rust",)),
    (("eval/definitions/example.toml",), ("eval",)),
    ((".github/PULL_REQUEST_TEMPLATE.md",), ("docs", "workflow-container")),
    (("bootstrap/container/image/Dockerfile",), ("workflow-container",)),
    (("documents/notes/example.yaml",), ("contracts",)),
    (("documents/example.rst",), ("contracts",)),
    (("documents/example.md", "tools/runtime/dispatch/agent-canon/src/main.rs"), ("docs", "rust")),
    (("documents/example.md", "tools/unknown.sh"), ("docs", "contracts")),
    (("tools/runtime/dispatch/agent-canon/src/docs.rs",), ("docs", "rust")),
    (("documents/runtime/runtime-profiles-and-check-matrix.json",), ("docs",)),
    ((), ()),
])
def test_selector_routes_each_surface_and_mixed_unknowns(paths, units) -> None:
    assert selected_units(*paths) == units


def test_selector_boundary_and_manual_dispatch_select_all_units() -> None:
    for path in (str(SELECTOR.relative_to(ROOT)), str(WORKFLOW.relative_to(ROOT))):
        assert selected_units(path) == STATIC_GATE_UNITS
    result = subprocess.run(
        ["python3", str(SELECTOR), "--full-confidence", "--format", "github-output"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    outputs = dict(line.split("=", 1) for line in result.stdout.splitlines())
    assert outputs["units"].split(",") == list(STATIC_GATE_UNITS)
    assert json.loads(outputs["docs_paths"]) == []


def test_selector_preserves_document_arguments_and_full_docs_inputs() -> None:
    from tools.validation.semantic.path.classify_path_risk import render_github_output
    paths = ("documents/has space.md", "documents/日本語.md", "documents/$data.md")
    outputs = dict(line.split("=", 1) for line in render_github_output(paths, ("docs",)).splitlines())
    assert json.loads(outputs["docs_paths"]) == list(paths)
    outputs = dict(line.split("=", 1) for line in render_github_output(
        (*paths, "tools/runtime/dispatch/agent-canon/src/docs.rs"), ("docs", "rust")
    ).splitlines())
    assert json.loads(outputs["docs_paths"]) == []


def test_workflow_triggers_and_one_authoritative_selector() -> None:
    config = workflow()
    assert set(config["on"]) == {"pull_request", "workflow_dispatch"}
    assert config["permissions"] == {"contents": "read"}
    assert set(config["jobs"]) == {"select-static-units", "static-gates"}
    selector = config["jobs"]["select-static-units"]
    assert "if" not in selector
    assert "--full-confidence" in str(selector)
    assert '"${BASE_SHA}" HEAD' in str(selector)
    assert config["jobs"]["static-gates"]["needs"] == "select-static-units"
    assert config["jobs"]["static-gates"]["if"] == "always()"
    assert "rust,contracts,eval,workflow-container" not in WORKFLOW.read_text()
    for job in config["jobs"].values():
        for item in job["steps"]:
            if item.get("uses", "").startswith("actions/checkout@"):
                assert item["with"]["persist-credentials"] == "false"


@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped", "unknown", "success"])
def test_selector_failure_cannot_become_a_successful_required_check(result) -> None:
    actual = run_shell(step("Require successful unit selection")["run"], root=ROOT,
                       SELECTION_RESULT=result, SELECTED_UNITS="")
    assert (actual.returncode == 0) == (result == "success")
    if result == "success":
        assert "selected_units=none" in actual.stdout


def test_empty_selection_does_not_start_a_runtime() -> None:
    for item in workflow()["jobs"]["static-gates"]["steps"]:
        if item["name"] in {"Require successful unit selection", "Release shared tool runtime"}:
            continue
        if item["name"] in {"Capture shared runtime validation output", "Upload static validation evidence"}:
            assert item["if"] == "always() && steps.start_runtime.outcome == 'success'"
        else:
            assert item["if"] == "needs.select-static-units.outputs.units != ''"


def test_candidate_preparation_preserves_head_and_target_base(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(target), *args], text=True).strip()
    git("init", "-b", "main")
    git("config", "user.name", "CI fixture")
    git("config", "user.email", "ci@example.invalid")
    (target / "README.md").write_text("base\n")
    git("add", ".")
    git("commit", "-m", "base")
    base = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/main", base)
    (target / "README.md").write_text("candidate\n")
    git("commit", "-am", "candidate")
    head = git("rev-parse", "HEAD")
    env_file = tmp_path / "env"
    result = run_shell(step("Prepare candidate source for bootstrap main synchronization")["run"],
                       root=target, AGENT_CANON_CONTROL_PARENT_ROOT=str(tmp_path),
                       GITHUB_RUN_ID="1", GITHUB_RUN_ATTEMPT="1", GITHUB_ENV=str(env_file))
    assert result.returncode == 0, result.stderr
    environment = dict(line.split("=", 1) for line in env_file.read_text().splitlines())
    source = Path(environment["AGENT_CANON_CANDIDATE_SOURCE"])
    assert source.parent == target.parent and source != target
    assert subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() == head
    assert subprocess.check_output(["git", "-C", str(source), "branch", "--show-current"], text=True).strip() == "main"
    assert git("rev-parse", "origin/main") == base
    assert git("status", "--porcelain") == ""
    cleanup = run_shell(step("Release shared tool runtime")["run"], root=target, **environment)
    assert cleanup.returncode == 0, cleanup.stderr
    assert not source.exists()
    assert not Path(environment["AGENT_CANON_CANDIDATE_BARE"]).exists()


def test_unit_failures_are_aggregated_without_skipping_later_units(tmp_path: Path) -> None:
    source = tmp_path / "candidate"
    source.mkdir()
    bootstrap = source / "bootstrap.sh"
    bootstrap.write_text(
        '#!/usr/bin/env bash\n'
        'printf "%s\\n" "$*" >> "$CALLS"\n'
        'printf "receipt for %s\\n" "$*"\n'
        'printf "native stderr\\n" >&2\n'
        '[[ "$*" != *".sh docs "* ]] || exit 7\n'
    )
    bootstrap.chmod(0o755)
    calls, summary = tmp_path / "calls", tmp_path / "summary"
    result = run_shell(step("Run selected units in the shared runtime")["run"], root=ROOT,
                       AGENT_CANON_CANDIDATE_SOURCE=str(source),
                       AGENT_CANON_CONTROL_PARENT_ROOT=str(tmp_path), GITHUB_WORKSPACE=str(ROOT),
                       RUNNER_TEMP=str(tmp_path), SELECTED_UNITS="docs,contracts,eval",
                       DOCS_PATHS='["documents/has space.md", "documents/$data.md"]',
                       BASE_SHA="fixed-base", GITHUB_STEP_SUMMARY=str(summary), CALLS=str(calls))
    assert result.returncode == 1, result.stderr
    assert len(calls.read_text().splitlines()) == 3
    assert ".sh contracts fixed-base" in calls.read_text()
    assert summary.read_text().splitlines() == [
        "unit=docs status=fail exit=7", "unit=contracts status=pass", "unit=eval status=pass"]
    evidence = tmp_path / "agent-canon-static-evidence"
    receipts = sorted(evidence.glob("unit-*.log"))
    assert len(receipts) == 3
    assert all("native stderr" in path.read_text() for path in receipts)
    assert "receipt for" in result.stdout
    assert "base=fixed-base" in (evidence / "source-identity.txt").read_text()


@pytest.mark.parametrize("paths", [[], ["has space.md"], ["deleted.md"]])
def test_docs_unit_executes_native_checker_and_propagates_failure(tmp_path: Path, paths) -> None:
    root, cache = tmp_path / "target", tmp_path / "cache"
    root.mkdir()
    (cache / "bin").mkdir(parents=True)
    (root / "has space.md").write_text("# Document\n")
    cli = cache / "bin/agent-canon"
    cli.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$CALLS"\nexit 9\n')
    cli.chmod(0o755)
    calls = tmp_path / "args"
    text = RUNNER.read_text()
    body = "run_docs() {" + text.split("run_docs() {", 1)[1].split("\n}\n\nrun_rust()", 1)[0] + "\n}\n"
    result = run_shell(body + "UNIT_ARGS=(" + shlex.join(paths) + "); run_docs",
                       root=root, ROOT=str(root), AGENT_CANON_CACHE_ROOT=str(cache), CALLS=str(calls))
    assert result.returncode == 9
    expected = ["docs", "check", "--root", str(root)]
    if paths == ["has space.md"]:
        expected.append("./has space.md")
    assert calls.read_text().splitlines() == expected


def test_contract_collection_and_source_toolchain_owners() -> None:
    text = RUNNER.read_text()
    body = text.split("run_contracts() {", 1)[1].split("\n}\n\nrun_eval()", 1)[0]
    assert "python3 -m pytest -p no:cacheprovider --pyargs" in body
    assert "python3 -m unittest" not in body
    assert "tests.tools.test_standalone_static_gate_source_runtime_contract" in body
    assert "tests/agent_tools/test_dependency_*.py" in body
    assert 'local base_ref="${UNIT_ARGS[0]:-origin/main}"' in body
    assert "RUNTIME_ROOT=/usr/local/share/agent-canon/runtime" not in text
    assert "export RUSTUP_HOME=" not in text
    assert "export CARGO_HOME=" not in text
    assert "/opt/agent-canon/source/tools/validation/ci/runners/" in WORKFLOW.read_text()


def test_runner_rejects_host_before_executing_units() -> None:
    if Path("/usr/local/share/agent-canon/.agent-canon-tool-container").is_file():
        pytest.skip("Host rejection does not apply inside the shared runtime")
    result = subprocess.run(["bash", str(RUNNER), "eval"], cwd=ROOT,
                            capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert "shared_tool_runtime_required" in result.stderr


def test_shell_syntax_and_single_runtime_install() -> None:
    scripts = [RUNNER.read_text(), FULL_WRAPPER.read_text()]
    for job in workflow()["jobs"].values():
        scripts.extend(item["run"] for item in job["steps"] if "run" in item)
    for script in scripts:
        result = subprocess.run(["bash", "-n"], input=script, text=True,
                                capture_output=True, check=False)
        assert result.returncode == 0, result.stderr
    assert WORKFLOW.read_text().count(" install\n") == 1


def test_pytest_is_provisioned_for_the_system_interpreter() -> None:
    import tomllib

    manifest = tomllib.loads((ROOT / "bootstrap/container/image/dependencies.toml").read_text())
    record = next(row for row in manifest["records"] if row["id"] == "python3-pytest")
    assert record["method"] == "apt-package"
    assert record["package"] == "python3-pytest"
    assert record["failure_policy"] == "fail"
    assert record["verification"]["executable"] == "pytest"


def test_units_do_not_duplicate_rust_or_full_wrapper_commands() -> None:
    text = RUNNER.read_text()
    for unit in STATIC_GATE_UNITS:
        assert f"{unit})" in text
    assert "unknown standalone static-gate unit" in text
    rust = text.split("run_rust() {", 1)[1].split("\n}\n\nrun_contracts()", 1)[0]
    remainder = text.replace(rust, "", 1)
    for command in ("cargo build --manifest-path", "cargo fmt --manifest-path", "cargo clippy --manifest-path", "cargo test --manifest-path"):
        assert command in rust
        assert command not in remainder
    wrapper = FULL_WRAPPER.read_text().split("run_standalone_static_gate_ci() {", 1)[1].split("\n}\n\ngithub_repo_security_status()", 1)[0]
    assert "owned_by_bootstrap_container_workflow" in wrapper
    for command in ("cargo build", "tool_catalog.py", "run_accumulated_agent_evals.py", "check_github_workflows.py"):
        assert command not in wrapper


@pytest.mark.parametrize(("remote_status", "bootstrap_status"), [(0, 0), (1, 0), (1, 17)])
def test_unpublished_environment_uses_native_local_build(tmp_path: Path, remote_status, bootstrap_status) -> None:
    source = tmp_path / "candidate"
    image = source / "bootstrap/container/image"
    image.mkdir(parents=True)
    (image / "digest.sh").write_text("printf 'fixture-key\\n'\n")
    bootstrap = source / "bootstrap.sh"
    bootstrap.write_text(
        '#!/usr/bin/env bash\n'
        'printf "%s\\n" "$*" >> "$CALLS"\n'
        'exit "$BOOTSTRAP_STATUS"\n'
    )
    bootstrap.chmod(0o755)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text('#!/usr/bin/env bash\nexit "$REMOTE_STATUS"\n')
    docker.chmod(0o755)
    calls = tmp_path / "calls"
    result = run_shell(step("Start one shared tool runtime")["run"], root=ROOT,
                       AGENT_CANON_CANDIDATE_SOURCE=str(source),
                       AGENT_CANON_CONTROL_PARENT_ROOT=str(tmp_path),
                       GITHUB_WORKSPACE=str(ROOT), GITHUB_REPOSITORY="iwashita-nozomu/agent-canon",
                       PATH=f"{bin_dir}:{os.environ['PATH']}", CALLS=str(calls),
                       REMOTE_STATUS=str(remote_status), BOOTSTRAP_STATUS=str(bootstrap_status))
    assert result.returncode == bootstrap_status
    commands = calls.read_text().splitlines()
    assert commands[0].endswith("install" if remote_status == 0 else "update --local-build")
    assert len(commands) == (3 if bootstrap_status == 0 else 1)


def test_output_is_uploaded_before_cleanup_even_when_unit_execution_fails() -> None:
    steps = workflow()["jobs"]["static-gates"]["steps"]
    names = [item["name"] for item in steps]
    execute = names.index("Run selected units in the shared runtime")
    capture = names.index("Capture shared runtime validation output")
    upload = names.index("Upload static validation evidence")
    cleanup = names.index("Release shared tool runtime")
    assert execute < capture < upload < cleanup
    assert step("Start one shared tool runtime")["id"] == "start_runtime"
    for index in (capture, upload):
        assert steps[index]["if"] == "always() && steps.start_runtime.outcome == 'success'"
        assert "continue-on-error" not in steps[index]
    assert steps[cleanup]["if"] == "always()"
    assert steps[upload]["uses"] == "actions/upload-artifact@v4"
    assert steps[upload]["with"]["retention-days"] == "7"
    assert steps[upload]["with"]["if-no-files-found"] == "error"
    assert "github.run_attempt" in steps[upload]["with"]["name"]


@pytest.mark.parametrize(
    ("container", "status_exit", "copy_exit", "copied"),
    [
        ({"owned": True, "id": "a" * 64}, 0, 0, True),
        ({"owned": True, "id": "a" * 64}, 0, 17, True),
        ({"owned": True, "id": "a" * 64}, 9, 0, False),
        ({"owned": False, "id": "a" * 64}, 0, 0, False),
        ({"owned": True, "id": "guessed-name"}, 0, 0, False),
        ({}, 0, 0, False),
    ],
)
def test_capture_exports_only_the_bootstrap_owned_container(
    tmp_path: Path, container, status_exit: int, copy_exit: int, copied: bool,
) -> None:
    source = tmp_path / "candidate"
    source.mkdir()
    bootstrap = source / "bootstrap.sh"
    bootstrap.write_text(
        '#!/usr/bin/env bash\n'
        '[[ "${@: -1}" == status ]] || exit 99\n'
        'printf "%s\\n" "$STATUS_JSON"\n'
        'exit "$STATUS_EXIT"\n'
    )
    bootstrap.chmod(0o755)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        '#!/usr/bin/env bash\n'
        'printf "%s\\n" "$@" > "$CALLS"\n'
        'printf "archive-stream"\n'
        'exit "$COPY_EXIT"\n'
    )
    docker.chmod(0o755)
    calls = tmp_path / "calls"
    result = run_shell(
        step("Capture shared runtime validation output")["run"], root=ROOT,
        AGENT_CANON_CANDIDATE_SOURCE=str(source),
        AGENT_CANON_CONTROL_PARENT_ROOT=str(tmp_path), RUNNER_TEMP=str(tmp_path),
        PATH=f"{bin_dir}:{os.environ['PATH']}", CALLS=str(calls),
        STATUS_JSON=json.dumps({"resource_ids": {"container": container}}),
        STATUS_EXIT=str(status_exit), COPY_EXIT=str(copy_exit),
    )
    assert calls.exists() == copied
    evidence = tmp_path / "agent-canon-static-evidence"
    assert (evidence / "runtime-status.json").is_file()
    archive = evidence / "runtime-task-output.tar"
    if copied:
        assert calls.read_text().splitlines() == [
            "cp", f"{'a' * 64}:/var/lib/agent-canon/runtime/tasks", "-",
        ]
        assert result.returncode == copy_exit
        assert archive.exists() == (copy_exit == 0)
        if copy_exit == 0:
            assert archive.read_bytes() == b"archive-stream"
        else:
            assert (evidence / "runtime-task-output.tar.part").read_bytes() == b"archive-stream"
    else:
        assert result.returncode != 0
        assert not archive.exists()
