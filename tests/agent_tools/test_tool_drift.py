"""Tests for tool/convention drift checker."""

# @dependency-start
# contract test
# responsibility Tests tool/convention drift checker behavior.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/tool_drift.rs native checker
# upstream design ../../documents/design/dependency-manifest-design.md manifest trace map
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")


class CheckToolConventionDriftTest(unittest.TestCase):
    """Exercise the tool/convention drift checker."""

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the actual native checker against a fixture root."""
        if not AGENT_CANON_CLI:
            raise RuntimeError("AGENT_CANON_CLI must select the current native executable")
        return subprocess.run(
            [AGENT_CANON_CLI, "tool-drift", "--root", str(root), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_checker_queries_all_nodes_for_bounded_fixture(self) -> None:
        """The native checker completes its all-source query without graph state."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_tool_catalog_contract(root)

            result = self.run_checker(
                root, "--contract", "tool_catalog", "--format", "json"
            )
            self.assertFalse((root / ".agent-canon").exists())

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["findings"], [])

    def test_projected_graph_paths_match_logical_contract_paths(self) -> None:
        """Source and target paths from projected roots match logical contracts."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tool_path = (
                "tools/agent-canon/validation/semantic/convention/"
                "check_convention_compliance.py"
            )
            self.write_file(
                root,
                tool_path,
                "# @dependency-start\n"
                "# contract tool\n"
                "# responsibility Exercises projected path identity.\n"
                "# upstream design ../../../../../vendor/agent-canon/agents/canonical/"
                "CODEX_COMPLETION.md projected target\n"
                "# @dependency-end\n",
            )
            self.write_file(
                root,
                "vendor/agent-canon/agents/canonical/CODEX_COMPLETION.md",
                "# Projected completion contract\n",
            )

            result = self.run_checker(root, "--contract", "convention_compliance")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn(
            "missing-manifest-link:convention_compliance:"
            "tools/validation/semantic/convention/check_convention_compliance.py:"
            "agents/canonical/CODEX_COMPLETION.md",
            result.stdout,
        )

    def test_missing_manifest_link_fails(self) -> None:
        """A required tool/document relationship must be in a manifest."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_convention_contract(root)
            tool = (
                root
                / "tools"
                / "validation"
                / "semantic"
                / "convention"
                / "check_convention_compliance.py"
            )
            tool.write_text(
                tool.read_text(encoding="utf-8").replace(
                    "# upstream design ../../../../agents/canonical/CODEX_COMPLETION.md completion evidence\n",
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "convention_compliance")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("TOOL_CONVENTION_DRIFT=fail", result.stdout)
            self.assertIn(
                "missing-manifest-link:convention_compliance:"
                "tools/validation/semantic/convention/check_convention_compliance.py:"
                "agents/canonical/CODEX_COMPLETION.md",
                result.stdout,
            )
            self.assertNotIn(
                ".codex/personal/skills/agent-orchestration/SKILL.md", result.stdout
            )

    def test_tool_rejection_preflight_checks_communication_protocol(self) -> None:
        """The preflight contract retains its communication-protocol requirement."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_tool_rejection_preflight_contract(root)
            protocol = root / "agents" / "COMMUNICATION_PROTOCOL.md"
            protocol.write_text(
                protocol.read_text(encoding="utf-8").replace(
                    "responsibility_scope",
                    "missing-scope-policy",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "tool_rejection_preflight")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-required-text:tool_rejection_preflight:"
                "agents/COMMUNICATION_PROTOCOL.md:"
                "missing-responsibility-scope-preflight-protocol",
                result.stdout,
            )

    def test_kind_mismatch_is_reported(self) -> None:
        """Reverse manifest edges must not contradict the direct edge kind."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_convention_contract(root)
            target = root / "documents" / "conventions" / "README.md"
            target.write_text(
                "\n".join(
                    [
                        "<!--",
                        "@dependency-start",
                        "responsibility Defines convention index.",
                        "downstream environment ../../tools/validation/semantic/convention/check_convention_compliance.py checker",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "convention_compliance")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("kind-mismatch:convention_compliance", result.stdout)
            self.assertIn("upstream design != downstream environment", result.stdout)

    def test_reverse_required_link_fails_when_only_direct_edge_exists(self) -> None:
        """A bidirectional contract reports a missing reverse manifest edge."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_tool_catalog_contract(root)
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# responsibility Defines fixture tool catalog.",
                        "# upstream design README.md fixture anchor",
                        "# @dependency-end",
                        "",
                        "version: 1",
                        "entries: []",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "tool_catalog")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-reverse-manifest-link:tool_catalog:"
                "tools/runtime/dispatch/agent-canon/src/catalog/tool_catalog.rs:tools/catalog.yaml",
                result.stdout,
            )

    def test_pr_check_command_backslash_space_tab_is_not_a_continuation(self) -> None:
        """Malformed backslash continuation after command lines is rejected for all gate checks."""
        continuation_suffixes = (" \\ \n", " \\\t\n")
        gates = [
            (
                "generated_artifact_guard",
                'python3 "${WORKSPACE_ROOT}/tools/runtime/artifacts/generated_artifact_guard.py" --root "${WORKSPACE_ROOT}"',
                "missing-generated-artifact-pr-guard",
                'python3 "${WORKSPACE_ROOT}/tools/runtime/artifacts/generated_artifact_guard.py"',
                '--root "${WORKSPACE_ROOT}"',
            ),
        ]
        for (
            contract,
            canonical_command,
            detail,
            command_prefix,
            command_tail,
        ) in gates:
            for suffix_name, suffix in (
                ("space", continuation_suffixes[0]),
                ("tab", continuation_suffixes[1]),
            ):
                with self.subTest(contract=contract, detail=detail, suffix=suffix_name):
                    with tempfile.TemporaryDirectory() as tmp_dir:
                        root = Path(tmp_dir)
                        self.write_agent_canon_pr_contract(root)
                        script = (
                            root
                            / "tools"
                            / "validation"
                            / "ci"
                            / "checks"
                            / "check_agent_canon_pr.sh"
                        )
                        malformed = script.read_text(encoding="utf-8").replace(
                            canonical_command,
                            command_prefix + suffix + f"  {command_tail}",
                        )
                        script.write_text(malformed, encoding="utf-8")

                        result = self.run_checker(root, "--contract", contract)

                        self.assertEqual(
                            result.returncode, 1, result.stdout + result.stderr
                        )
                        self.assertIn(
                            f"missing-required-command:{contract}:"
                            "tools/validation/ci/checks/check_agent_canon_pr.sh:"
                            f"{detail}",
                            result.stdout,
                        )

    def test_pr_check_must_run_agent_runtime_alignment(self) -> None:
        """The PR check retains its runtime role-alignment command."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_agent_canon_pr_contract(root)
            script = (
                root
                / "tools"
                / "validation"
                / "ci"
                / "checks"
                / "check_agent_canon_pr.sh"
            )
            text = script.read_text(encoding="utf-8").replace(
                'python3 "${WORKSPACE_ROOT}/tools/validation/semantic/runtime/check_agent_runtime_alignment.py"\n',
                "",
            )
            script.write_text(text, encoding="utf-8")

            result = self.run_checker(root, "--contract", "agent_canon_pr_check")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-required-text:agent_canon_pr_check:"
                "tools/validation/ci/checks/check_agent_canon_pr.sh:"
                "missing-agent-runtime-alignment-check",
                result.stdout,
            )

    def test_pr_check_must_run_generated_artifact_guard(self) -> None:
        """The AgentCanon PR check must reject regenerated report leftovers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_agent_canon_pr_contract(root)
            script = (
                root
                / "tools"
                / "validation"
                / "ci"
                / "checks"
                / "check_agent_canon_pr.sh"
            )
            text = script.read_text(encoding="utf-8").replace(
                'python3 "${WORKSPACE_ROOT}/tools/runtime/artifacts/generated_artifact_guard.py" --root "${WORKSPACE_ROOT}"\n',
                "",
            )
            script.write_text(text, encoding="utf-8")

            result = self.run_checker(root, "--contract", "generated_artifact_guard")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-required-command:generated_artifact_guard:"
                "tools/validation/ci/checks/check_agent_canon_pr.sh:"
                "missing-generated-artifact-pr-guard",
                result.stdout,
            )

    def test_catalog_stale_entry_fails(self) -> None:
        """The drift checker catches stale structured catalog entries."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_tool_catalog_contract(root)
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8").replace(
                    "tools/runtime/dispatch/agent-canon/src/catalog/tool_catalog.rs",
                    "tools/agent_tools/missing_tool.py",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "tool_catalog")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "stale-catalog-entry:tool_catalog:"
                "tools/agent_tools/missing_tool.py:missing-path",
                result.stdout,
            )

    def test_catalog_additional_yaml_document_is_rejected(self) -> None:
        """The catalog loader rejects extra YAML documents instead of ignoring them."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_tool_catalog_contract(root)
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8")
                + "\n---\nversion: 1\nentries: []\n",
                encoding="utf-8",
            )

            result = self.run_checker(
                root, "--contract", "tool_catalog", "--format", "json"
            )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("expected a single YAML document", result.stderr)

    def test_catalog_retired_legacy_fails(self) -> None:
        """Legacy provenance entries and directories are rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_tool_catalog_contract(root)
            self.write_file(root, "tools/legacy/example/README.md", "legacy\n")
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8")
                + "\n".join(
                    [
                        "  - id: legacy-example",
                        "    path: tools/legacy/example",
                        "    status: legacy_provenance",
                        "    callable_by_default: false",
                        "    default_wiring:",
                        "      ci: false",
                        "      pr_check: false",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "tool_catalog")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "retired-legacy-tool:tool_catalog:"
                "tools/legacy/example:legacy-tools-are-retired",
                result.stdout,
            )
            self.assertIn(
                "retired-legacy-tool:tool_catalog:tools/legacy:legacy-directory-present",
                result.stdout,
            )

    def test_orphaned_legacy_token_tool_file_fails(self) -> None:
        """Uncataloged legacy-like tool files must not survive drift checks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_tool_catalog_contract(root)
            self.write_file(root, "tools/search_legacy.py", "print('retired')\n")

            result = self.run_checker(root, "--contract", "tool_catalog")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "retired-legacy-tool:tool_catalog:"
                "tools/search_legacy.py:legacy-tools-are-retired",
                result.stdout,
            )

    def test_cataloged_legacy_token_tool_file_is_not_double_reported(self) -> None:
        """Cataloged retired tool files should produce one catalog finding."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_tool_catalog_contract(root)
            self.write_file(root, "tools/legacysearch.py", "print('retired')\n")
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8")
                + "\n".join(
                    [
                        "  - id: legacysearch",
                        "    path: tools/legacysearch.py",
                        "    status: canonical",
                        "    callable_by_default: false",
                        "    default_wiring:",
                        "      ci: false",
                        "      pr_check: false",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "tool_catalog")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(result.stdout.count("tools/legacysearch.py"), 1)
            self.assertIn(
                "retired-legacy-tool:tool_catalog:"
                "tools/legacysearch.py:legacy-tools-are-retired",
                result.stdout,
            )

    def write_file(self, root: Path, relative: str, text: str) -> None:
        """Write one fixture file."""
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def write_plain_manifest(self, root: Path, relative: str) -> None:
        """Write one non-isolated placeholder manifest."""
        self.write_file(
            root,
            relative,
            "\n".join(
                [
                    "<!--",
                    "@dependency-start",
                    "responsibility Provides a fixture target.",
                    "upstream design README.md fixture anchor",
                    "@dependency-end",
                    "-->",
                    "",
                ]
            ),
        )

    def write_convention_contract(self, root: Path) -> None:
        """Write fixtures for the convention-compliance contract."""
        self.write_file(root, "README.md", "# Fixture\n")
        self.write_file(
            root,
            "tools/validation/semantic/convention/check_convention_compliance.py",
            "\n".join(
                [
                    "# @dependency-start",
                    "# responsibility Checks convention compliance.",
                    "# upstream design ../../../../documents/conventions/README.md conventions",
                    "# upstream design ../../../../agents/canonical/CODEX_COMPLETION.md completion evidence",
                    "# upstream design ../../../../documents/codex/codex-configuration-reference.md Codex configuration",
                    "# upstream design ../../../../documents/conventions/coding-conventions-house-style.md source style",
                    "# upstream design ../../../../.codex/README.md runtime hook behavior",
                    "# upstream design ../../../catalog.yaml tool catalog",
                    "# upstream implementation ./convention_compliance_contracts.toml marker contracts",
                    "# upstream implementation ../skills/check_skill_frontmatter.py skill frontmatter",
                    "# downstream implementation ../../ci/runners/run_all_checks.sh ci",
                    "# downstream implementation ../../../runtime/dispatch/agent-canon/src/tool_drift.rs drift gate",
                    "# downstream implementation ../../../../tests/agent_tools/test_check_convention_compliance.py tests",
                    "# @dependency-end",
                    "",
                ]
            ),
        )
        for relative in [
            "documents/conventions/README.md",
            "agents/canonical/CODEX_COMPLETION.md",
            "documents/codex/codex-configuration-reference.md",
            "documents/conventions/coding-conventions-house-style.md",
            ".codex/README.md",
            "tools/catalog.yaml",
            "tools/validation/semantic/convention/convention_compliance_contracts.toml",
            "tools/validation/semantic/skills/check_skill_frontmatter.py",
            "tools/validation/ci/runners/run_all_checks.sh",
            "tools/runtime/dispatch/agent-canon/src/tool_drift.rs",
            "tests/agent_tools/test_check_convention_compliance.py",
        ]:
            self.write_plain_manifest(root, relative)

    def write_tool_rejection_preflight_contract(self, root: Path) -> None:
        """Write fixtures for the tool rejection preflight contract."""
        self.write_file(
            root,
            "tools/validation/semantic/tools/tool_rejection_preflight.py",
            "\n".join(
                [
                    "# @dependency-start",
                    "# responsibility Prechecks edit-time risk class.",
                    "# upstream design ../../../../agents/COMMUNICATION_PROTOCOL.md protocol",
                    "# upstream design ../../../../agents/skills/codex-task-workflow.md workflow",
                    "# upstream design ../../../../tools/runtime/dispatch/agent-canon/src/responsibility_scope.rs scope",
                    "# upstream design ../../../README.md tool entrypoints",
                    "# upstream design ../../../../documents/tools/README.md user-facing routes",
                    "# upstream implementation ../../../../tests/agent_tools/test_tool_rejection_preflight.py scope preflight",
                    "# @dependency-end",
                    "",
                ]
            ),
        )
        for relative in [
            "agents/COMMUNICATION_PROTOCOL.md",
            "agents/skills/codex-task-workflow.md",
            "tools/runtime/dispatch/agent-canon/src/responsibility_scope.rs",
            "tools/README.md",
            "documents/tools/README.md",
            "tests/agent_tools/test_tool_rejection_preflight.py",
        ]:
            if relative == "agents/COMMUNICATION_PROTOCOL.md":
                snippet = "`responsibility_scope` gate records"
                self.write_file(
                    root,
                    relative,
                    "\n".join(
                        [
                            "<!--",
                            "@dependency-start",
                            "responsibility Provides preflight fixture.",
                            "upstream design README.md fixture anchor",
                            "@dependency-end",
                            "-->",
                            snippet,
                            "",
                        ]
                    ),
                )
            elif relative.endswith(".rs"):
                self.write_file(
                    root,
                    relative,
                    "\n".join(
                        [
                            "// @dependency-start",
                            "// responsibility Provides a native scope fixture.",
                            "// upstream design README.md fixture anchor",
                            "// @dependency-end",
                            "",
                        ]
                    ),
                )
            else:
                self.write_plain_manifest(root, relative)

    def write_agent_canon_pr_contract(self, root: Path) -> None:
        """Write fixtures for the AgentCanon PR check contract."""
        self.write_file(root, "README.md", "# Fixture\n")
        self.write_file(
            root,
            "tools/validation/ci/checks/check_agent_canon_pr.sh",
            "\n".join(
                [
                    "# @dependency-start",
                    "# responsibility Checks AgentCanon PR readiness.",
                    "# upstream design ../../../../agents/skills/agent-canon-update.md workflow",
                    "# upstream design ../../../../.github/PULL_REQUEST_TEMPLATE.md standalone template",
                    "# upstream implementation ../../../repository/workspace/parent_root_side_effects.py parent-root boundary",
                    "# upstream implementation ../../../runtime/artifacts/runtime_artifacts.py runtime output boundary",
                    "# upstream implementation ../../../runtime/artifacts/generated_artifact_guard.py generated artifact guard",
                    "# upstream implementation ../../semantic/runtime/check_agent_runtime_alignment.py runtime alignment",
                    "# upstream implementation ../../semantic/convention/check_convention_compliance.py convention gate",
                    "# upstream implementation ../../../runtime/lifecycle/update_lifecycle_contract.py lifecycle receipt",
                    "# upstream implementation ../../../runtime/dispatch/agent-canon/src/main.rs CLI build gate",
                    "# upstream implementation ./check_github_workflows.py github checks",
                    "# upstream implementation ./run_python_quality_checks.sh python quality",
                    "# @dependency-end",
                    'python3 "${WORKSPACE_ROOT}/tools/runtime/artifacts/generated_artifact_guard.py" --root "${WORKSPACE_ROOT}"',
                    'python3 "${WORKSPACE_ROOT}/tools/validation/semantic/runtime/check_agent_runtime_alignment.py"',
                    "",
                ]
            ),
        )
        for relative in [
            "agents/skills/agent-canon-update.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            "tools/repository/workspace/parent_root_side_effects.py",
            "tools/runtime/artifacts/runtime_artifacts.py",
            "tools/runtime/artifacts/generated_artifact_guard.py",
            "tools/validation/semantic/runtime/check_agent_runtime_alignment.py",
            "tools/validation/semantic/convention/check_convention_compliance.py",
            "tools/runtime/lifecycle/update_lifecycle_contract.py",
            "tools/runtime/dispatch/agent-canon/src/main.rs",
            "tools/validation/ci/checks/check_github_workflows.py",
            "tools/validation/ci/checks/run_python_quality_checks.sh",
        ]:
            self.write_plain_manifest(root, relative)

    def write_tool_catalog_contract(self, root: Path) -> None:
        """Write fixtures for the tool catalog contract."""
        self.write_file(root, "README.md", "# Fixture\n")
        self.write_file(
            root,
            "tools/runtime/dispatch/agent-canon/src/catalog/tool_catalog.rs",
            "\n".join(
                [
                    "# @dependency-start",
                    "# responsibility Validates tool catalog.",
                    "# upstream design ../../../../../../tools/catalog.yaml catalog",
                    "# upstream design ../../../../../../tools/README.md tool docs",
                    "# upstream design ../../../../../../documents/tools/README.md root docs",
                    "# upstream design ../../../../../../documents/tools/tool-docs.toml docs map",
                    "# upstream design ../../../../../../documents/tools/repo-local-tool-imports.md imports",
                    "# downstream implementation ../../../../../../tools/validation/ci/runners/run_all_checks.sh ci",
                    "# downstream implementation ../../../../../../tests/agent_tools/test_tool_catalog.py tests",
                    "# @dependency-end",
                    "",
                ]
            ),
        )
        self.write_file(
            root,
            "tools/catalog.yaml",
            "\n".join(
                [
                    "# @dependency-start",
                    "# responsibility Defines fixture tool catalog.",
                    "# downstream implementation runtime/dispatch/agent-canon/src/catalog/tool_catalog.rs checker",
                    "# @dependency-end",
                    "",
                    "version: 1",
                    "entries:",
                    "  - id: tool-catalog",
                    "    path: tools/runtime/dispatch/agent-canon/src/catalog/tool_catalog.rs",
                    "    status: canonical",
                    "",
                ]
            ),
        )
        for relative in [
            "tools/README.md",
            "documents/tools/README.md",
            "documents/tools/tool-docs.toml",
            "documents/tools/repo-local-tool-imports.md",
            "tools/validation/ci/runners/run_all_checks.sh",
            "tests/agent_tools/test_tool_catalog.py",
        ]:
            self.write_file(
                root,
                relative,
                "\n".join(
                    [
                        "<!--",
                        "@dependency-start",
                        "responsibility Provides tool catalog fixture.",
                        "upstream design README.md fixture anchor",
                        "downstream implementation tools/runtime/dispatch/agent-canon/src/catalog/tool_catalog.rs checker",
                        "@dependency-end",
                        "-->",
                        "tools/catalog.yaml",
                        "tool_catalog.rs",
                        "tool-docs.toml",
                        "",
                    ]
                ),
            )


if __name__ == "__main__":
    unittest.main()
