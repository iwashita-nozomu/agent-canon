"""Focused schema, identity, and reference tests for the semantic contract checker."""

# @dependency-start
# contract test
# responsibility Tests focused semantic responsibility contract validation.
# upstream implementation ../../tools/agent_tools/check_semantic_responsibility_contract.py validates schema, identity, and references
# upstream design ../../documents/design/semantic-responsibility-contract.md canonical semantic responsibility contract
# downstream design ../../templates/documents/semantic-responsibility-contract.template.toml reusable instance shape
# @dependency-end

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "tools/agent_tools/check_semantic_responsibility_contract.py"
TEMPLATE = ROOT / "templates/documents/semantic-responsibility-contract.template.toml"
FIXTURE = ROOT / "tests/fixtures/semantic_responsibility_contract/task_instance.toml"
ARTIFACT_ROOT = FIXTURE.parent


def run_checker(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the focused checker with repository-rooted paths."""
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(ROOT), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_valid_template_and_task_instance() -> None:
    """Accept the empty template and a populated task instance."""
    result = run_checker(
        "--template",
        str(TEMPLATE),
        "--instance",
        str(FIXTURE),
        "--artifact-root",
        str(ARTIFACT_ROOT),
    )

    assert result.returncode == 0, result.stderr
    assert "SEMANTIC_RESPONSIBILITY_CONTRACT=pass" in result.stdout


def test_rejects_invalid_reference(tmp_path: Path) -> None:
    """Reject a reference that traverses outside its allowed root."""
    invalid = tmp_path / "invalid.toml"
    invalid.write_text(
        FIXTURE.read_text(encoding="utf-8").replace(
            "repo:tools/agent_tools/check_semantic_responsibility_contract.py#symbol:validate_document",
            "repo:../outside.py#symbol:missing",
            1,
        ),
        encoding="utf-8",
    )

    result = run_checker(
        "--instance",
        str(invalid),
        "--artifact-root",
        str(ARTIFACT_ROOT),
    )

    assert result.returncode != 0
    assert "unsafe_reference" in result.stderr


def test_rejects_existing_test_without_removal_witness(tmp_path: Path) -> None:
    """Reject an existing-test obligation without a removal witness."""
    invalid = tmp_path / "invalid.toml"
    invalid.write_text(
        FIXTURE.read_text(encoding="utf-8").replace(
            'removal_witness = "repo:tests/agent_tools/test_check_semantic_responsibility_contract.py#symbol:test_rejects_invalid_reference"',
            'removal_witness = ""',
            1,
        ),
        encoding="utf-8",
    )

    result = run_checker(
        "--instance",
        str(invalid),
        "--artifact-root",
        str(ARTIFACT_ROOT),
    )

    assert result.returncode != 0
    assert "removal_witness" in result.stderr
