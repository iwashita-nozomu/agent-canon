"""Focused schema, identity, and reference tests for the semantic contract checker."""

# @dependency-start
# contract test
# responsibility Tests focused semantic responsibility contract validation.
# upstream implementation ../../tools/validation/semantic/responsibility/check_semantic_responsibility_contract.py validates schema, identity, and references
# upstream design ../../documents/design/semantic-responsibility-contract.md canonical semantic responsibility contract
# downstream design ../../templates/documents/semantic-responsibility-contract.template.toml reusable instance shape
# @dependency-end

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "tools/validation/semantic/responsibility/check_semantic_responsibility_contract.py"
TEMPLATE = ROOT / "templates/documents/semantic-responsibility-contract.template.toml"


def run_checker(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the focused checker with repository-rooted paths."""
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(ROOT), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def materialize_task_instance(
    tmp_path: Path, *, existing_test: bool = False
) -> tuple[Path, Path]:
    """Materialize one populated task instance and its artifact root in tmp_path."""
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    (artifact_root / "team_manifest.yaml").write_text(
        "run:\n  active_design_packet: {}\n", encoding="utf-8"
    )
    text = TEMPLATE.read_text(encoding="utf-8")
    replacements = {
        'instance_kind = "template"': 'instance_kind = "task"',
        'policy_ref = "documents/design/semantic-responsibility-contract.md"': 'policy_ref = "repo:documents/design/semantic-responsibility-contract.md#section:目的"',
        'active_design_packet_ref = ""': 'active_design_packet_ref = "artifact:team_manifest.yaml#section:run.active_design_packet"',
        'run_id = ""': 'run_id = "tmp-run"',
        'task_id = ""': 'task_id = "tmp-task"',
        'responsibility_id = ""': 'responsibility_id = "tmp-responsibility"',
        'semantic_grouping = ""': 'semantic_grouping = "tmp semantic grouping"',
        'summary = ""': 'summary = "tmp semantic delta"',
        'implementation_action = ""': 'implementation_action = "extend"',
        'design_refs = []': 'design_refs = ["repo:documents/design/semantic-responsibility-contract.md#section:Semantic-delta"]',
        'claim = ""': 'claim = "tmp contract claim"',
        'verification_owner_kind = ""': 'verification_owner_kind = "static_checker"',
        'verification_owner = ""': 'verification_owner = "checker"',
        'primary_verification_ref = ""': 'primary_verification_ref = "repo:tools/validation/semantic/responsibility/check_semantic_responsibility_contract.py#symbol:validate_document"',
    }
    for before, after in replacements.items():
        if before not in text:
            raise AssertionError(f"template shape changed: {before}")
        text = text.replace(before, after, 1)
    text = text.replace('id = ""', 'id = "tmp-delta"', 1)
    text = text.replace('id = ""', 'id = "tmp-obligation"', 1)
    if existing_test:
        existing_replacements = {
            'verification_owner_kind = "static_checker"': 'verification_owner_kind = "existing_test"',
            'verification_owner = "checker"': 'verification_owner = "tests"',
            'primary_verification_ref = "repo:tools/validation/semantic/responsibility/check_semantic_responsibility_contract.py#symbol:validate_document"': 'primary_verification_ref = "repo:tests/agent_tools/test_check_semantic_responsibility_contract.py#symbol:test_accepts_single_obligation"',
            'contract_ref = ""': 'contract_ref = "repo:documents/design/semantic-responsibility-contract.md#section:既存-test-の証跡"',
            'changed_mechanism_ref = ""': 'changed_mechanism_ref = "repo:tools/validation/semantic/responsibility/check_semantic_responsibility_contract.py#symbol:validate_document"',
            'observable_assertion = ""': 'observable_assertion = "valid task instance passes"',
            'decidable_oracle = ""': 'decidable_oracle = "pytest return code"',
            'removal_witness = ""': 'removal_witness = "repo:tests/agent_tools/test_check_semantic_responsibility_contract.py#symbol:test_rejects_existing_test_without_removal_witness"',
        }
        for before, after in existing_replacements.items():
            if before not in text:
                raise AssertionError(f"template shape changed: {before}")
            text = text.replace(before, after, 1)
    instance = tmp_path / "semantic_responsibility_contract.toml"
    instance.write_text(text, encoding="utf-8")
    return instance, artifact_root


def test_accepts_single_obligation(tmp_path: Path) -> None:
    """Accept a populated task delta with one obligation."""
    instance, artifact_root = materialize_task_instance(tmp_path)
    result = run_checker(
        "--template",
        str(TEMPLATE),
        "--instance",
        str(instance),
        "--artifact-root",
        str(artifact_root),
    )

    assert result.returncode == 0, result.stderr
    assert "SEMANTIC_RESPONSIBILITY_CONTRACT=pass" in result.stdout


def test_rejects_invalid_reference(tmp_path: Path) -> None:
    """Reject a reference that traverses outside its allowed root."""
    instance, artifact_root = materialize_task_instance(tmp_path)
    invalid = tmp_path / "invalid.toml"
    invalid.write_text(
        instance.read_text(encoding="utf-8").replace(
            "repo:tools/validation/semantic/responsibility/check_semantic_responsibility_contract.py#symbol:validate_document",
            "repo:../outside.py#symbol:missing",
            1,
        ),
        encoding="utf-8",
    )

    result = run_checker(
        "--instance",
        str(invalid),
        "--artifact-root",
        str(artifact_root),
    )

    assert result.returncode != 0
    assert "unsafe_reference" in result.stderr


def test_rejects_existing_test_without_removal_witness(tmp_path: Path) -> None:
    """Reject an existing-test obligation without a removal witness."""
    instance, artifact_root = materialize_task_instance(tmp_path, existing_test=True)
    invalid = tmp_path / "invalid.toml"
    invalid.write_text(
        instance.read_text(encoding="utf-8").replace(
            'removal_witness = "repo:tests/agent_tools/test_check_semantic_responsibility_contract.py#symbol:test_rejects_existing_test_without_removal_witness"',
            'removal_witness = ""',
            1,
        ),
        encoding="utf-8",
    )

    result = run_checker(
        "--instance",
        str(invalid),
        "--artifact-root",
        str(artifact_root),
    )

    assert result.returncode != 0
    assert "removal_witness" in result.stderr
