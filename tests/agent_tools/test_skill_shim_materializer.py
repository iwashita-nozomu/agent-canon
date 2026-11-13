"""Consumer oracles for the native Skill shim materializer CLI."""

# @dependency-start
# contract test
# responsibility Verifies catalog-derived materializer fixed-point, readback, and fail-closed legacy evidence.
# upstream design ../../documents/design/skill-runtime-shim-materialization.md owns the v3 schema and migration contract
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/catalog/skill_materialization.rs owns rendering and materialization
# downstream reference ../../tests/fixtures/skill-runtime-shim/host-evaluations freezes measured host scenarios
# @dependency-end

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")


def selected_cli() -> str:
    if AGENT_CANON_CLI is None:
        raise RuntimeError("AGENT_CANON_CLI must select the current native executable")
    return AGENT_CANON_CLI


@contextmanager
def source_fixture() -> Iterator[Path]:
    """Yield a disposable source tree for the native CLI."""
    with tempfile.TemporaryDirectory(prefix="agent-canon-materializer-") as temporary:
        source = Path(temporary) / "source"
        shutil.copytree(
            PROJECT_ROOT,
            source,
            symlinks=True,
            ignore=shutil.ignore_patterns(
                ".git", ".runtime", ".ruff_cache", ".pytest_cache", "__pycache__"
            ),
        )
        yield source


def mutation_capability(root: Path) -> str:
    catalog = yaml.safe_load((root / "agents/skills/catalog.yaml").read_text(encoding="utf-8"))
    paths = [entry["shim"] for entry in catalog["skill_families"]]
    return json.dumps(
        {
            "allowed_paths": paths,
            "purpose": "skill-shim-materializer-test",
            "authority": "isolated fixture",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def run_materializer(
    root: Path,
    command: str,
    *arguments: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            selected_cli(),
            "skill-shim-materializer",
            command,
            "--root",
            str(root),
            *arguments,
        ],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def report(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    if result.returncode not in {0, 1}:
        raise AssertionError(result.stdout + result.stderr)
    return json.loads(result.stdout)


def materialize(root: Path) -> subprocess.CompletedProcess[str]:
    return run_materializer(
        root,
        "materialize",
        "--all",
        "--format",
        "json",
        "--source-mutation-capability-json",
        mutation_capability(root),
    )


def legacy_receipt(result: subprocess.CompletedProcess[str]) -> list[dict[str, Any]]:
    prefix = "SKILL_SHIM_MATERIALIZER_LEGACY_RECEIPT="
    line = next((line for line in result.stdout.splitlines() if line.startswith(prefix)), None)
    if line is None:
        raise AssertionError(result.stdout + result.stderr)
    return json.loads(line[len(prefix) :])


class SkillShimMaterializerTest(unittest.TestCase):
    """Verify the native materializer converges and refuses unmatched legacy prose."""

    def test_explicit_authoring_root_ignores_runtime_source_aliases(self) -> None:
        environment = os.environ.copy()
        environment["AGENT_CANON_SOURCE_ROOT"] = "/opt/agent-canon/source"
        environment["AGENT_CANON_CANON_ROOT"] = "/opt/agent-canon/source"
        with source_fixture() as source:
            aliased = run_materializer(source, "check", "--all", "--format", "json", env=environment)
            explicit = run_materializer(source, "check", "--all", "--format", "json")
        self.assertEqual(report(aliased), report(explicit))

    def test_check_does_not_launch_catalog_validators(self) -> None:
        with source_fixture() as source, tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "validator-was-run"
            fake_bin = Path(temporary) / "bin"
            fake_bin.mkdir()
            for name in ("yamllint", "check-jsonschema"):
                tool = fake_bin / name
                tool.write_text(f"#!/bin/sh\n: > '{marker}'\n", encoding="utf-8")
                tool.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = str(fake_bin)
            result = run_materializer(source, "check", "--all", "--format", "json", env=environment)
        self.assertIn(report(result)["status"], {"pass", "fail"})
        self.assertFalse(marker.exists())

    def test_materialize_reaches_a_fixed_point(self) -> None:
        with source_fixture() as source:
            first = report(materialize(source))
            second = report(materialize(source))
        self.assertEqual(first["schema"], "agent_canon.skill_runtime_shim.materialize")
        self.assertEqual(first["version"], 3)
        self.assertEqual(second["content_delta_count"], 0)
        self.assertEqual(second["content_delta_paths"], [])
        self.assertEqual(first["record_digests"], second["record_digests"])
        self.assertEqual(first["projection_digests"], second["projection_digests"])
        self.assertEqual(first["readback_digest"], second["readback_digest"])
        self.assertEqual(set(first["record_digests"]), set(first["projection_digests"]))
        self.assertEqual(second["status"], "pass")

    def test_readback_manifest_covers_every_catalog_skill(self) -> None:
        with source_fixture() as source:
            materialize(source)
            readback = report(
                run_materializer(source, "readback", "--all", "--format", "json")
            )
        self.assertEqual(readback["schema"], "agent_canon.skill_runtime_shim.readback")
        self.assertEqual(readback["status"], "pass")
        self.assertEqual(readback["readback_count"], len(readback["record_digests"]))
        self.assertEqual(set(readback["record_digests"]), set(readback["projection_digests"]))

    def test_record_digest_drift_is_detected_from_generated_bytes(self) -> None:
        with source_fixture() as source:
            initial = report(materialize(source))
            skill = "agent-orchestration"
            digest = initial["record_digests"][skill]
            path = source / ".codex/personal/skills" / skill / "SKILL.md"
            original = path.read_text(encoding="utf-8")
            self.assertIn(f'"record_digest":"{digest}"', original)
            path.write_text(original.replace(digest, "0" * 64, 1), encoding="utf-8")
            result = report(run_materializer(source, "check", "--all", "--format", "json"))
        self.assertEqual(result["status"], "fail")
        self.assertIn(path.relative_to(source).as_posix(), result["content_delta_paths"])

    def test_legacy_tool_commands_are_blocked_with_locators(self) -> None:
        with source_fixture() as source:
            skill = "agent-orchestration"
            path = source / ".codex/personal/skills" / skill / "SKILL.md"
            path.write_text(
                "<!-- generated: agent_canon.skill_runtime_shim.v1 -->\n"
                "## Tool Commands\n"
                "python3 tools/agent/skills/skill_tool_commands.py show --skill agent-orchestration --format text\n",
                encoding="utf-8",
            )
            result = materialize(source)
            receipt = legacy_receipt(result)
        self.assertEqual(result.returncode, 2)
        row = next(item for item in receipt if item["skill_id"] == skill)
        self.assertEqual(row["resolution"], "blocked")
        self.assertEqual(row["classification"], "legacy_schema_mismatch")
        blocks = row["unmatched_blocks"]
        self.assertEqual(len(blocks), 2)
        locators = [entry["locator"] for entry in blocks]
        self.assertIn(f"{path.relative_to(source).as_posix()}#preamble", locators)
        self.assertIn(f"{path.relative_to(source).as_posix()}#L2-L3", locators)

    def test_legacy_receipt_lists_every_unmatched_block(self) -> None:
        with source_fixture() as source:
            skill = "agent-orchestration"
            path = source / ".codex/personal/skills" / skill / "SKILL.md"
            path.write_text(
                "---\nname: agent-orchestration\ndescription: \"Legacy\"\n---\n"
                "# Legacy\n\n## Reader Map\n\nUnmatched prose.\n",
                encoding="utf-8",
            )
            receipt = legacy_receipt(materialize(source))
        row = next(item for item in receipt if item["skill_id"] == skill)
        blocks = row["unmatched_blocks"]
        self.assertEqual(len(blocks), 2)
        self.assertTrue(all("locator" in block and "digest" in block for block in blocks))

    def test_legacy_complete_schema_without_owner_link_is_blocked(self) -> None:
        with source_fixture() as source:
            report(materialize(source))
            skill = "agent-orchestration"
            path = source / ".codex/personal/skills" / skill / "SKILL.md"
            original = path.read_text(encoding="utf-8")
            owner_line = (
                "Canonical workflow and policy: "
                "[agent-orchestration](../../../../agents/skills/agent-orchestration.md).\n"
            )
            self.assertIn(owner_line, original)
            path.write_text(original.replace(owner_line, "", 1), encoding="utf-8")
            result = materialize(source)
            receipt = legacy_receipt(result)
        self.assertEqual(result.returncode, 2)
        row = next(item for item in receipt if item["skill_id"] == skill)
        self.assertEqual(row["classification"], "legacy_schema_mismatch")
        self.assertEqual(row["resolution"], "blocked")
        self.assertGreater(len(row["unmatched_blocks"]), 0)

    def test_generated_shim_contains_its_canonical_dependency_manifest(self) -> None:
        path = PROJECT_ROOT / ".codex/personal/skills/agent-orchestration/SKILL.md"
        rendered = path.read_text(encoding="utf-8")
        self.assertIn(
            "\n".join(
                (
                    "<!--",
                    "@dependency-start",
                    "contract skill",
                    "responsibility Exposes agent-orchestration for runtime discovery.",
                    "upstream design ../../../../agents/skills/agent-orchestration.md owner",
                    "@dependency-end",
                    "-->",
                )
            ),
            rendered,
        )


if __name__ == "__main__":
    unittest.main()
