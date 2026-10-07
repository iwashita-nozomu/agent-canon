"""Focused contract tests for the read-only full-check execution route."""

# @dependency-start
# contract test
# responsibility Verifies full checks are admitted only after a read-only target mount proof and reuse the existing full-check body without checkout mutation.
# upstream implementation ../../tools/validation/ci/runners/run_standalone_static_gate_unit.sh owns target admission and full-check dispatch
# upstream implementation ../../tools/validation/ci/runners/run_all_checks.sh owns the existing full-confidence check body
# @dependency-end

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = (
    ROOT
    / "tools"
    / "validation"
    / "ci"
    / "runners"
    / "run_standalone_static_gate_unit.sh"
)


def runner_text() -> str:
    """Read the canonical shared-runtime unit runner."""
    return RUNNER.read_text(encoding="utf-8")


def executable_fixture_bin(tmp_path: Path) -> Path:
    """Place fake executables on the external runtime's executable filesystem."""
    runtime_root = os.environ.get("AGENT_CANON_RUNTIME_ROOT", "").strip()
    if not runtime_root:
        return tmp_path / "bin"
    return (
        Path(runtime_root) / "tasks" / f"read-only-full-check-{tmp_path.name}" / "bin"
    )


def test_full_unit_is_guarded_by_read_only_mount_proof() -> None:
    """The full body cannot run before the visible source mount proves `ro`."""
    text = runner_text()
    assert "\nassert_read_only_target\n" in text
    assert text.index("\nassert_read_only_target\n") < text.index('cd "${ROOT}"')
    assert text.index("\nassert_read_only_target\n") < text.index("run_full()")


@pytest.mark.parametrize(
    ("reply", "status", "admitted"),
    [
        ('{"filesystems":[{"target":"/source","vfs-options":"ro,relatime"}]}', 0, True),
        (
            '{"filesystems":[{"target":"/source","vfs-options":"rw,relatime","options":"ro"}]}',
            0,
            False,
        ),
        (
            '{"filesystems":[{"target":"/source","vfs-options":"errors=remount-ro"}]}',
            0,
            False,
        ),
        ('{"filesystems":[{"target":"/source","vfs-options":"ro,rw"}]}', 0, False),
        ('{"filesystems":[{"target":"/source","options":"ro"}]}', 0, False),
        ('{"filesystems":[{"target":"/source","vfs-options":null}]}', 0, False),
        ('{"filesystems":[]}', 0, False),
        ('{"filesystems":[{},{}]}', 0, False),
        ('{"filesystems":[null]}', 0, False),
        ("[]", 0, False),
        ("not JSON", 0, False),
        ('{"filesystems":[{"target":"/source","vfs-options":"ro"}]}', 1, False),
    ],
)
def test_mount_admission_consumes_native_result_before_body(
    tmp_path: Path,
    reply: str,
    status: int,
    admitted: bool,
) -> None:
    """Run the production guard; only the external findmnt observation is faked."""
    target = tmp_path / "source with space\\backslash"
    target.mkdir()
    fake_bin = executable_fixture_bin(tmp_path)
    fake_bin.mkdir(parents=True, exist_ok=True)
    fake_findmnt = fake_bin / "findmnt"
    capture = tmp_path / "argv.json"
    fake_findmnt.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['FINDMNT_CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n"
        "print(os.environ['FINDMNT_REPLY'])\n"
        "sys.exit(int(os.environ['FINDMNT_STATUS']))\n",
        encoding="utf-8",
    )
    fake_findmnt.chmod(0o755)
    text = runner_text()
    guard = text.split("assert_read_only_target() {", 1)[1].split(
        "\n}\n\nassert_read_only_target", 1
    )[0]
    result = subprocess.run(
        [
            "bash",
            "-c",
            "set -euo pipefail\nassert_read_only_target() {"
            + guard
            + "\n}\nassert_read_only_target\nprintf 'CHECK_BODY_STARTED\\n'\n",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "ROOT": str(target),
            "FINDMNT_CAPTURE": str(capture),
            "FINDMNT_REPLY": reply,
            "FINDMNT_STATUS": str(status),
        },
    )
    assert (result.returncode == 0) is admitted, result.stderr
    assert ("CHECK_BODY_STARTED" in result.stdout) is admitted
    assert json.loads(capture.read_text(encoding="utf-8")) == [
        "--kernel",
        "--first-only",
        "--direction",
        "backward",
        "--list",
        "--target",
        str(target.resolve()),
        "--json",
        "--output",
        "TARGET,VFS-OPTIONS",
    ]


@pytest.mark.parametrize("visible_options", ("ro", "rw"))
@pytest.mark.parametrize("layout", ("ordinary", "nested", "overmount"))
def test_native_findmnt_resolves_visible_mount_fixture(
    tmp_path: Path,
    visible_options: str,
    layout: str,
) -> None:
    """Exercise libmount fixtures, not real mounts or a duplicate mount parser."""
    target = tmp_path / "source with space\\backslash"
    target.mkdir()
    nested = target / "nested"
    nested.mkdir()
    selected = target if layout == "ordinary" else nested
    encoded_target = str(target.resolve()).replace("\\", "\\134").replace(" ", "\\040")
    encoded_selected = (
        str(selected.resolve()).replace("\\", "\\134").replace(" ", "\\040")
    )
    rows = ["1 0 0:1 / / rw - tmpfs tmpfs rw"]
    parent_options = visible_options if layout == "ordinary" else "rw"
    rows.append(f"2 1 0:2 / {encoded_target} {parent_options} - tmpfs tmpfs rw")
    if layout != "ordinary":
        hidden_options = "rw" if visible_options == "ro" else "ro"
        options = hidden_options if layout == "overmount" else visible_options
        rows.append(f"3 2 0:3 / {encoded_selected} {options} - tmpfs tmpfs rw")
    if layout == "overmount":
        rows.append(f"4 3 0:4 / {encoded_selected} {visible_options} - tmpfs tmpfs rw")
    table = tmp_path / "mountinfo.fixture"
    table.write_text("\n".join(rows) + "\n", encoding="utf-8")
    result = subprocess.run(
        [
            "findmnt",
            "--kernel",
            "--first-only",
            "--direction",
            "backward",
            "--list",
            "--tab-file",
            str(table),
            "--target",
            str(selected),
            "--json",
            "--output",
            "TARGET,VFS-OPTIONS",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    mounts = json.loads(result.stdout)["filesystems"]
    assert len(mounts) == 1
    assert mounts[0]["target"] == str(selected.resolve())
    assert mounts[0]["vfs-options"].split(",")[0] == visible_options


def test_full_unit_reuses_existing_body_and_forwards_options() -> None:
    """The adapter adds only an effect boundary; it does not duplicate checks."""
    text = runner_text()
    body = text.split("run_full() {", 1)[1].split("\n}\n\nrun_docs()", 1)[0]

    assert (
        'bash "${ROOT}/tools/validation/ci/runners/run_all_checks.sh" "${UNIT_ARGS[@]}"'
        in body
    )
    assert 'AGENT_CANON_CONTROL_PARENT_ROOT="${control_parent_root}"' in body
    assert (
        "AGENT_CANON_CONTROL_PARENT_ROOT:?AGENT_CANON_CONTROL_PARENT_ROOT is required"
        in body
    )
    assert 'AGENT_CANON_CHILD_PURPOSE="standalone-static-gate-unit"' in body
    assert 'AGENT_CANON_CLI_CMD="${AGENT_CANON_CACHE_ROOT}/bin/agent-canon"' in body
    assert "CARGO_HOME=" not in body
    assert "RUSTUP_HOME=" not in body
    assert 'AGENT_CANON_RUNTIME_ROOT="${AGENT_CANON_STATIC_RUNTIME_ROOT}"' in body
    assert "full) run_full" in text
    assert '"${UNIT}" != "full"' in text
    assert 'cd "${AGENT_CANON_STATIC_RUNTIME_ROOT}/.."' not in body


@pytest.mark.parametrize("body_status", (0, 17))
def test_full_unit_preserves_body_status_without_target_mutation(
    tmp_path: Path,
    body_status: int,
) -> None:
    """The adapter forwards capabilities and preserves the body result."""
    target = tmp_path / "target"
    target.mkdir()
    subprocess.run(["git", "init", "-q", str(target)], check=True)
    tracked = target / "tracked.txt"
    tracked.write_text("unchanged\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(target), "add", "tracked.txt"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(target),
            "-c",
            "user.email=agent-canon@example.invalid",
            "-c",
            "user.name=AgentCanon",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        check=True,
    )

    runner_parent = target / "tools" / "validation" / "ci" / "runners"
    runner_parent.mkdir(parents=True)
    runner = runner_parent / RUNNER.name
    runner_text = RUNNER.read_text(encoding="utf-8").replace(
        "/usr/local/share/agent-canon/.agent-canon-tool-container",
        str(tmp_path / "tool-container-marker"),
    )
    runner.write_text(runner_text, encoding="utf-8")
    runner.chmod(0o755)
    (tmp_path / "tool-container-marker").touch()

    capture = tmp_path / "capture.txt"
    fake_checks = (
        target / "tools" / "validation" / "ci" / "runners" / "run_all_checks.sh"
    )
    fake_checks.parent.mkdir(parents=True, exist_ok=True)
    fake_checks.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        ': > "${FAKE_CAPTURE}"\n'
        'printf \'control=%s\\n\' "${AGENT_CANON_CONTROL_PARENT_ROOT}" >> "${FAKE_CAPTURE}"\n'
        'printf \'runtime=%s\\n\' "${AGENT_CANON_RUNTIME_ROOT}" >> "${FAKE_CAPTURE}"\n'
        'printf \'purpose=%s\\n\' "${AGENT_CANON_CHILD_PURPOSE}" >> "${FAKE_CAPTURE}"\n'
        'printf \'handoff=%s\\n\' "${AGENT_CANON_CHILD_HANDOFF}" >> "${FAKE_CAPTURE}"\n'
        'printf \'cli=%s\\n\' "${AGENT_CANON_CLI_CMD}" >> "${FAKE_CAPTURE}"\n'
        'printf \'cargo=%s\\n\' "${CARGO_HOME}" >> "${FAKE_CAPTURE}"\n'
        'printf \'rustup=%s\\n\' "${RUSTUP_HOME}" >> "${FAKE_CAPTURE}"\n'
        'printf \'args=%s\\n\' "$*" >> "${FAKE_CAPTURE}"\n'
        "printf 'RUN_ALL_CHECKS_BODY=completed\\n'\n"
        'exit "${FAKE_BODY_STATUS}"\n',
        encoding="utf-8",
    )
    fake_checks.chmod(0o755)

    fake_bin = executable_fixture_bin(tmp_path)
    fake_bin.mkdir(parents=True, exist_ok=True)
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "payload=$(cat)\n"
        "if [[ \"${payload}\" == *'runtime_artifact_boundary'* ]]; then\n"
        '  if [[ "$#" -ge 4 ]]; then printf \'%s\\n\' "${4}"; else printf \'%s\\n\' "${3}"; fi\n'
        "else\n"
        "  exit 0\n"
        "fi\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    control = tmp_path / "home"
    runtime = control / "workspace" / "full-check"
    before_tree = subprocess.run(
        ["git", "-C", str(target), "write-tree"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    before_index = (target / ".git" / "index").read_bytes()
    result = subprocess.run(
        ["bash", str(runner), "full", "--quick", "--skip-docs"],
        cwd=target,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "AGENT_CANON_TARGET_ROOT": str(target),
            "AGENT_CANON_CONTROL_PARENT_ROOT": str(control),
            "AGENT_CANON_RUNTIME_ROOT": str(runtime),
            "AGENT_CANON_CACHE_ROOT": str(control / "cache"),
            "CARGO_HOME": str(control / "cache" / "cargo"),
            "RUSTUP_HOME": str(control / "image" / "rustup"),
            "AGENT_CANON_CHILD_HANDOFF": "authenticated-handoff",
            "AGENT_CANON_HANDOFF_AUDIENCE": "standalone-static-gate-unit",
            "FAKE_CAPTURE": str(capture),
            "FAKE_BODY_STATUS": str(body_status),
        },
    )
    assert result.returncode == body_status, result.stderr
    assert "RUN_ALL_CHECKS_BODY=completed" in result.stdout
    observed = dict(
        line.split("=", 1) for line in capture.read_text(encoding="utf-8").splitlines()
    )
    assert observed == {
        "control": str(control),
        "runtime": str(runtime),
        "purpose": "standalone-static-gate-unit",
        "handoff": "authenticated-handoff",
        "cli": str(control / "cache" / "bin" / "agent-canon"),
        "cargo": str(control / "cache" / "cargo"),
        "rustup": str(control / "image" / "rustup"),
        "args": "--quick --skip-docs",
    }
    after_tree = subprocess.run(
        ["git", "-C", str(target), "write-tree"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert after_tree == before_tree
    assert (target / ".git" / "index").read_bytes() == before_index
    assert (
        hashlib.sha256(tracked.read_bytes()).hexdigest()
        == hashlib.sha256(b"unchanged\n").hexdigest()
    )


def test_read_only_route_never_repairs_the_caller_checkout() -> None:
    """Isolation must not be replaced by destructive Git rollback."""
    text = runner_text()
    for command in ("git restore", "git reset", "git clean", "git stash"):
        assert command not in text


def test_host_execution_fails_before_any_check_body() -> None:
    """The unit runner is not a writable-Host fallback."""
    marker = Path("/usr/local/share/agent-canon/.agent-canon-tool-container")
    if marker.is_file():
        return
    result = subprocess.run(
        ["bash", str(RUNNER), "full", "--quick"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "shared_tool_runtime_required" in result.stderr


def test_shell_syntax() -> None:
    """The read-only runner remains valid Bash."""
    result = subprocess.run(
        ["bash", "-n", str(RUNNER)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
