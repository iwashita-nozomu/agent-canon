"""Black-box tests for the native artifact identity command."""

# @dependency-start
# contract test
# responsibility Tests native artifact identity CLI bytes and source readback.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/artifacts/artifact_identity.rs materializes and verifies artifact identities
# @dependency-end

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from tests.agent_tools.rust_cli_fixture import standalone_agent_canon

OWNER_PATH = "tools/runtime/dispatch/agent-canon/src/artifacts/artifact_identity.rs"


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _repository(root: Path) -> Path:
    root.mkdir()
    _git(root, "init", "--initial-branch=main")
    _git(root, "config", "user.name", "AgentCanon test")
    _git(root, "config", "user.email", "test@example.invalid")
    owner = root / OWNER_PATH
    owner.parent.mkdir(parents=True)
    owner.write_text("// native owner fixture\n", encoding="utf-8")
    (root / "review-target.md").write_text("review input\n", encoding="utf-8")
    _git(root, "add", OWNER_PATH, "review-target.md")
    _git(root, "commit", "-m", "fixture")
    return root


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(standalone_agent_canon()),
            "artifact-identity",
            "--root",
            str(root),
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_native_cli_materializes_and_verifies_committed_artifact(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")

    materialized = _run(root, "materialize", "review-target.md")

    assert materialized.returncode == 0, materialized.stderr
    marker, encoded = materialized.stdout.splitlines()
    assert marker == "ARTIFACT_IDENTITY=pass"
    assert '"artifact_path": "review-target.md"' in encoded
    assert ", " in encoded
    record = json.loads(encoded)
    assert record["schema"] == "agent-canon.artifact-identity.v1"
    assert record["artifact_path"] == "review-target.md"
    artifact_bytes = b"review input\n"
    assert record["artifact_role"] == "review_target"
    assert record["byte_size"] == len(artifact_bytes)
    assert record["sha256"] == hashlib.sha256(artifact_bytes).hexdigest()
    expected_blob = hashlib.sha1(
        b"blob " + str(len(artifact_bytes)).encode() + b"\0" + artifact_bytes,
        usedforsecurity=False,
    ).hexdigest()
    assert record["git_blob"] == expected_blob
    assert record["source_binding"]["kind"] == "git_commit_path"
    assert record["filesystem_readback"]["nofollow"] is True
    assert record["materializer"]["owner_tool"] == OWNER_PATH

    record_path = root / "identity.json"
    record_path.write_text(encoded + "\n", encoding="utf-8")
    verified = _run(root, "verify", "identity.json")

    assert verified.returncode == 0, verified.stderr
    verify_marker, verify_json = verified.stdout.splitlines()
    assert verify_marker == "ARTIFACT_IDENTITY=pass"
    verification = json.loads(verify_json)
    assert verification["ok"] is True
    assert verification["identity_record_id"] == record["identity_record_id"]


def test_native_cli_keeps_help_argument_and_failure_exit_contracts(
    tmp_path: Path,
) -> None:
    executable = standalone_agent_canon()

    global_help = subprocess.run(
        [str(executable), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert global_help.returncode == 0
    assert "artifact-identity [--root ROOT]" in global_help.stdout

    help_result = subprocess.run(
        [str(executable), "artifact-identity", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0
    assert "materialize ARTIFACT" in help_result.stdout
    assert "verify RECORD" in help_result.stdout

    invalid = _run(tmp_path, "unknown", "x")
    assert invalid.returncode == 2
    assert "usage:" in invalid.stderr

    root = _repository(tmp_path / "bad-repo")
    bad_record = root / "bad.json"
    bad_record.write_text("{}\n", encoding="utf-8")
    failed = _run(root, "verify", "bad.json")
    assert failed.returncode == 1
    assert failed.stdout.splitlines()[0] == "ARTIFACT_IDENTITY=fail"
    assert "ARTIFACT_IDENTITY_FINDING=artifact_identity:" in failed.stdout
