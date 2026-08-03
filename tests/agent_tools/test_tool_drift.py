"""Tests for tool/convention drift checker."""

# @dependency-start
# contract test
# responsibility Tests tool/convention drift checker behavior.
# upstream implementation ../../tools/agent_tools/tool_drift.py checker
# upstream design ../../documents/design/dependency-manifest-design.md manifest trace map
# @dependency-end

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.agent_tools import tool_drift as drift_checker
from tools.agent_tools.graph_client import GraphDependencyFact, GraphResponse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "agent_tools" / "tool_drift.py"


class FakeToolGraphClient:
    """Provide graph-owned dependency facts for isolated checker fixtures."""

    last_query: dict[str, object] = {}

    def __init__(self, root: Path, _executable: Path | None = None) -> None:
        """Create a fixture graph client for the given root."""
        self._root = root.resolve()

    def query(
        self,
        *,
        path: str | None = None,
        relation: str = "dependency",
        direction: str = "both",
        depth: int = 0,
        all_nodes: bool = False,
    ) -> GraphResponse:
        """Project fixture manifests into the graph query response shape."""
        type(self).last_query = {
            "path": path,
            "relation": relation,
            "direction": direction,
            "depth": depth,
            "all_nodes": all_nodes,
        }
        nodes: dict[str, str] = {}
        facts: list[dict[str, object]] = []
        for manifest_path in sorted(self._root.rglob("*")):
            relative = manifest_path.relative_to(self._root)
            if not manifest_path.is_file() or any(
                part.startswith(".") for part in relative.parts
            ):
                continue
            source = relative.as_posix()
            in_manifest = False
            try:
                lines = manifest_path.read_text(encoding="utf-8").splitlines()[:80]
            except UnicodeDecodeError:
                continue
            for line_number, raw_line in enumerate(lines, start=1):
                line = raw_line.strip()
                for prefix in ("<!--", "#", "//", "*"):
                    if line.startswith(prefix):
                        line = line[len(prefix) :].strip()
                if line.endswith("-->"):
                    line = line[:-3].strip()
                if line == "@dependency-start":
                    in_manifest = True
                    continue
                if line == "@dependency-end":
                    in_manifest = False
                    continue
                if not in_manifest:
                    continue
                fields = line.split(maxsplit=3)
                if len(fields) < 4 or fields[0] not in {"upstream", "downstream"}:
                    continue
                dependency_direction, kind, target, reason = fields
                target_path = (manifest_path.parent / target).resolve()
                try:
                    target_name = target_path.relative_to(self._root).as_posix()
                except ValueError:
                    target_name = target_path.as_posix()
                source_id = f"node:{source}"
                target_id = f"node:{target_name}"
                nodes[source_id] = source
                nodes[target_id] = target_name
                fact_id = f"fact:{len(facts)}"
                facts.append(
                    {
                        "id": fact_id,
                        "kind": "dependency",
                        "inferred": False,
                        "from": source_id,
                        "to": target_id,
                        "producer": "test-fixture-projection",
                        "source_path": source,
                        "source_span": None,
                        "evidence_ref": f"{source}:{line_number}",
                        "authority": "test-fixture-projection",
                        "dependency_detail": {
                            "direction": dependency_direction,
                            "kind": kind,
                            "reason": reason,
                        },
                    }
                )
        return GraphResponse(
            schema="agent-canon.graph.query.v1",
            command="query",
            status="fresh",
            payload={
                "nodes": [
                    {"id": node_id, "path": path}
                    for node_id, path in sorted(nodes.items())
                ],
                "facts": facts,
            },
            exit_code=0,
        )


class CheckToolConventionDriftTest(unittest.TestCase):
    """Exercise the tool/convention drift checker."""

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the checker against a root."""
        stdout = io.StringIO()
        stderr = io.StringIO()
        argv = [str(CHECKER), "--root", str(root), *args]
        FakeToolGraphClient.last_query = {}
        with (
            patch.object(sys, "argv", argv),
            patch.object(drift_checker, "GraphClient", FakeToolGraphClient),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            return_code = drift_checker.main()
        return subprocess.CompletedProcess(
            args=argv,
            returncode=return_code,
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue(),
        )

    def test_current_repository_passes(self) -> None:
        """The canonical repository satisfies the drift gate."""
        result = self.run_checker(PROJECT_ROOT)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("TOOL_CONVENTION_DRIFT=pass", result.stdout)
        self.assertTrue(FakeToolGraphClient.last_query["all_nodes"])

    def test_projected_graph_paths_match_logical_contract_paths(self) -> None:
        """Graph facts from parent projections use standalone contract paths."""
        fact = GraphDependencyFact(
            id="fact:projection",
            direction="upstream",
            kind="design",
            source="tools/agent-canon/agent_tools/tool_drift.py",
            target="vendor/agent-canon/agents/canonical/CODEX_SUBAGENTS.md",
            reason="projection fixture",
            producer="test-fixture-projection",
            source_path="tools/agent-canon/agent_tools/tool_drift.py",
            source_span=None,
            evidence_ref="projection:1",
            authority="test-fixture-projection",
        )

        self.assertEqual(
            drift_checker.matching_direct_edges(
                (fact,),
                "tools/agent_tools/tool_drift.py",
                "agents/canonical/CODEX_SUBAGENTS.md",
            ),
            (fact,),
        )

    def test_missing_manifest_link_fails(self) -> None:
        """A required tool/document relationship must be in a manifest."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_convention_contract(root)
            tool = root / "tools" / "agent_tools" / "check_convention_compliance.py"
            tool.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# responsibility Checks convention compliance.",
                        "# upstream design ../../documents/conventions/README.md conventions",
                        "# upstream design ../../evidence/agent-evals/skill_workflow_prompt_eval.toml evals",
                        "# upstream design ../../templates/agents/closeout_gate.md closeout",
                        "# upstream implementation ../ci/run_all_checks.sh ci",
                        "# upstream implementation ./tool_drift.py drift gate",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "convention_compliance")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("TOOL_CONVENTION_DRIFT=fail", result.stdout)
            self.assertIn(
                "missing-manifest-link:convention_compliance:"
                "tools/agent_tools/check_convention_compliance.py:"
                "agents/canonical/CODEX_WORKFLOW.md",
                result.stdout,
            )
            self.assertNotIn(
                ".agents/skills/agent-orchestration/SKILL.md", result.stdout
            )

    def test_tool_rejection_preflight_checks_canonical_owner_skills(self) -> None:
        """Tool rejection preflight checks canonical skill owners, not generated shims."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_tool_rejection_preflight_contract(root)
            workflow = root / "agents" / "skills" / "codex-task-workflow.md"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    "responsibility_scope",
                    "missing-scope-policy",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "tool_rejection_preflight")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-required-text:tool_rejection_preflight:"
                "agents/skills/codex-task-workflow.md:"
                "missing-runtime-workflow-responsibility-preflight",
                result.stdout,
            )
            self.assertNotIn(
                ".agents/skills/codex-task-workflow/SKILL.md", result.stdout
            )
            self.assertNotIn(
                ".agents/skills/owner-bounded-routing/SKILL.md", result.stdout
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
                        "downstream environment ../../tools/agent_tools/check_convention_compliance.py checker",
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
                "tools/agent_tools/tool_catalog.py:tools/catalog.yaml",
                result.stdout,
            )

    def test_pr_check_must_select_dependency_graph_requirement(self) -> None:
        """The AgentCanon PR check must select strict graph completeness explicitly."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_agent_canon_pr_contract(root)
            script = root / "tools" / "ci" / "check_agent_canon_pr.sh"
            text = script.read_text(encoding="utf-8").replace(
                "if agentcanon_pr_dependency_graph_required; then\n", "if true; then\n"
            )
            script.write_text(text, encoding="utf-8")

            result = self.run_checker(root, "--contract", "agent_canon_pr_check")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-required-text:agent_canon_pr_check:"
                "tools/ci/check_agent_canon_pr.sh:"
                "missing-conditional-dependency-graph-gate",
                result.stdout,
            )

    def test_pr_check_requires_optional_dependency_graph_receipt_status(self) -> None:
        """The PR check must carry an explicit prepared-or-skipped graph receipt."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_agent_canon_pr_contract(root)
            script = root / "tools" / "ci" / "check_agent_canon_pr.sh"
            text = script.read_text(encoding="utf-8").replace(
                "PR_GATE_DEPENDENCY_GRAPH_STATUS=skipped\n", ""
            )
            script.write_text(text, encoding="utf-8")

            result = self.run_checker(root, "--contract", "agent_canon_pr_check")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-required-text:agent_canon_pr_check:"
                "tools/ci/check_agent_canon_pr.sh:"
                "missing-optional-dependency-graph-receipt-status",
                result.stdout,
            )

    def test_pr_check_requires_selector_reason_and_evidence_receipt(self) -> None:
        """Skipped graph receipts retain the selector's reason and evidence."""
        for marker, detail in (
            ("selector_reason=%s", "missing-dependency-graph-selector-reason-receipt"),
            (
                "selector_evidence=%s",
                "missing-dependency-graph-selector-evidence-receipt",
            ),
        ):
            with self.subTest(marker=marker):
                with tempfile.TemporaryDirectory() as tmp_dir:
                    root = Path(tmp_dir)
                    self.write_agent_canon_pr_contract(root)
                    script = root / "tools" / "ci" / "check_agent_canon_pr.sh"
                    script.write_text(
                        script.read_text(encoding="utf-8").replace(
                            marker, "removed", 1
                        ),
                        encoding="utf-8",
                    )

                    result = self.run_checker(
                        root, "--contract", "agent_canon_pr_check"
                    )

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(
                    "missing-required-text:agent_canon_pr_check:"
                    f"tools/ci/check_agent_canon_pr.sh:{detail}",
                    result.stdout,
                )

    def test_pr_check_strict_dependency_review_command_does_not_count_comment(
        self,
    ) -> None:
        """Dependency-review command only in comments is rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_agent_canon_pr_contract(root)
            script = root / "tools" / "ci" / "check_agent_canon_pr.sh"
            command = (
                'bash "${CANON_TOOLS_ROOT}/agent_tools/run_repo_dependency_review.sh" '
                "--fail-missing --cycle-report-only --changed-path-packet "
                '"${PR_GATE_DEPENDENCY_CHANGED_PATH_PACKET}" --trusted-base-sha '
                '"${PR_GATE_DEPENDENCY_GRAPH_BASE_SHA}" --report-dir '
                '"${PR_DEPENDENCY_REVIEW_DIR}"'
            )
            script.write_text(
                script.read_text(encoding="utf-8").replace(command, f"# {command}"),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "agent_canon_pr_check")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-required-command:agent_canon_pr_check:"
                "tools/ci/check_agent_canon_pr.sh:"
                "missing-strict-dependency-review",
                result.stdout,
            )

    def test_pr_check_strict_dependency_review_command_does_not_count_echo_printf_or_suppression(
        self,
    ) -> None:
        """Dependency-review command via echo/printf/suppression is rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_agent_canon_pr_contract(root)
            script = root / "tools" / "ci" / "check_agent_canon_pr.sh"
            command = (
                'bash "${CANON_TOOLS_ROOT}/agent_tools/run_repo_dependency_review.sh" '
                "--fail-missing --cycle-report-only --changed-path-packet "
                '"${PR_GATE_DEPENDENCY_CHANGED_PATH_PACKET}" --trusted-base-sha '
                '"${PR_GATE_DEPENDENCY_GRAPH_BASE_SHA}" --report-dir '
                '"${PR_DEPENDENCY_REVIEW_DIR}"'
            )
            script.write_text(
                script.read_text(encoding="utf-8").replace(
                    command, f'echo "{command}"\nprintf "{command}"\n{command} || true'
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "agent_canon_pr_check")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-required-command:agent_canon_pr_check:"
                "tools/ci/check_agent_canon_pr.sh:"
                "missing-strict-dependency-review",
                result.stdout,
            )

    def test_pr_check_strict_dependency_review_command_is_recognized_once(self) -> None:
        """Duplicate dependency-review invocation in PR check is rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_agent_canon_pr_contract(root)
            script = root / "tools" / "ci" / "check_agent_canon_pr.sh"
            command = (
                'bash "${CANON_TOOLS_ROOT}/agent_tools/run_repo_dependency_review.sh" '
                "--fail-missing --cycle-report-only --changed-path-packet "
                '"${PR_GATE_DEPENDENCY_CHANGED_PATH_PACKET}" --trusted-base-sha '
                '"${PR_GATE_DEPENDENCY_GRAPH_BASE_SHA}" --report-dir '
                '"${PR_DEPENDENCY_REVIEW_DIR}"'
            )
            script.write_text(
                script.read_text(encoding="utf-8") + f"\n{command}\n",
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "agent_canon_pr_check")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "duplicate-required-command:agent_canon_pr_check:"
                "tools/ci/check_agent_canon_pr.sh:"
                "missing-strict-dependency-review:actual=2:expected=1",
                result.stdout,
            )

    def test_pr_check_command_backslash_space_tab_is_not_a_continuation(self) -> None:
        """Malformed backslash continuation after command lines is rejected for all gate checks."""
        continuation_suffixes = (" \\ \n", " \\\t\n")
        gates = [
            (
                "agent_canon_pr_check",
                'bash "${CANON_TOOLS_ROOT}/agent_tools/run_repo_dependency_review.sh" --fail-missing --cycle-report-only --changed-path-packet "${PR_GATE_DEPENDENCY_CHANGED_PATH_PACKET}" --trusted-base-sha "${PR_GATE_DEPENDENCY_GRAPH_BASE_SHA}" --report-dir "${PR_DEPENDENCY_REVIEW_DIR}"',
                "missing-strict-dependency-review",
                'bash "${CANON_TOOLS_ROOT}/agent_tools/run_repo_dependency_review.sh" --fail-missing',
                '--cycle-report-only --changed-path-packet "${PR_GATE_DEPENDENCY_CHANGED_PATH_PACKET}" --trusted-base-sha "${PR_GATE_DEPENDENCY_GRAPH_BASE_SHA}" --report-dir "${PR_DEPENDENCY_REVIEW_DIR}"',
            ),
            (
                "agent_canon_pr_check",
                'python3 "${CANON_TOOLS_ROOT}/agent_tools/run_accumulated_agent_evals.py" --run-id agent-canon-pr-gate --log-dir "${PR_AGENT_EVAL_LOG_DIR}"',
                "missing-accumulated-agent-eval-producer",
                'python3 "${CANON_TOOLS_ROOT}/agent_tools/run_accumulated_agent_evals.py" --run-id agent-canon-pr-gate',
                '--log-dir "${PR_AGENT_EVAL_LOG_DIR}"',
            ),
            (
                "generated_artifact_guard",
                'python3 "${CANON_TOOLS_ROOT}/agent_tools/generated_artifact_guard.py" --root "${WORKSPACE_ROOT}"',
                "missing-generated-artifact-pr-guard",
                'python3 "${CANON_TOOLS_ROOT}/agent_tools/generated_artifact_guard.py"',
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
                        script = root / "tools" / "ci" / "check_agent_canon_pr.sh"
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
                            "tools/ci/check_agent_canon_pr.sh:"
                            f"{detail}",
                            result.stdout,
                        )

    def test_pr_check_strict_dependency_review_command_passes(self) -> None:
        """Canonical dependency-review command passes command extraction."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_agent_canon_pr_contract(root)

            result = self.run_checker(root, "--contract", "agent_canon_pr_check")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn(
                "missing-required-command:agent_canon_pr_check:"
                "tools/ci/check_agent_canon_pr.sh:",
                result.stdout,
            )

    def test_pr_check_strict_dependency_review_requires_changed_path_packet(
        self,
    ) -> None:
        """A strict review without the trusted path packet is rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_agent_canon_pr_contract(root)
            script = root / "tools" / "ci" / "check_agent_canon_pr.sh"
            script.write_text(
                script.read_text(encoding="utf-8").replace(
                    ' --changed-path-packet "${PR_GATE_DEPENDENCY_CHANGED_PATH_PACKET}"',
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "agent_canon_pr_check")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-required-command:agent_canon_pr_check:"
                "tools/ci/check_agent_canon_pr.sh:missing-strict-dependency-review",
                result.stdout,
            )

    def test_pr_check_strict_dependency_review_rejects_extra_arguments(
        self,
    ) -> None:
        """An extra argument cannot satisfy the exact strict-review contract."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_agent_canon_pr_contract(root)
            script = root / "tools" / "ci" / "check_agent_canon_pr.sh"
            command = (
                'bash "${CANON_TOOLS_ROOT}/agent_tools/run_repo_dependency_review.sh" '
                "--fail-missing --cycle-report-only --changed-path-packet "
                '"${PR_GATE_DEPENDENCY_CHANGED_PATH_PACKET}" --trusted-base-sha '
                '"${PR_GATE_DEPENDENCY_GRAPH_BASE_SHA}" --report-dir '
                '"${PR_DEPENDENCY_REVIEW_DIR}"'
            )
            script.write_text(
                script.read_text(encoding="utf-8").replace(
                    command, f"{command} --unexpected-bypass-argument"
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "agent_canon_pr_check")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-required-command:agent_canon_pr_check:"
                "tools/ci/check_agent_canon_pr.sh:missing-strict-dependency-review",
                result.stdout,
            )

    def test_pr_check_must_run_accumulated_agent_evals(self) -> None:
        """The AgentCanon PR check must mechanically accumulate eval reports."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_agent_canon_pr_contract(root)
            script = root / "tools" / "ci" / "check_agent_canon_pr.sh"
            text = script.read_text(encoding="utf-8").replace(
                'python3 "${CANON_TOOLS_ROOT}/agent_tools/run_accumulated_agent_evals.py" --run-id agent-canon-pr-gate --log-dir "${PR_AGENT_EVAL_LOG_DIR}"\n',
                "",
            )
            script.write_text(text, encoding="utf-8")

            result = self.run_checker(root, "--contract", "agent_canon_pr_check")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-required-command:agent_canon_pr_check:"
                "tools/ci/check_agent_canon_pr.sh:"
                "missing-accumulated-agent-eval-producer",
                result.stdout,
            )

    def test_pr_check_must_scope_agent_eval_archive_env(self) -> None:
        """The AgentCanon PR check must pass a writable archive env to eval producers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_agent_canon_pr_contract(root)
            script = root / "tools" / "ci" / "check_agent_canon_pr.sh"
            text = script.read_text(encoding="utf-8").replace(
                'AGENT_CANON_HOOK_ARCHIVE_DIR="${PR_HOOK_ARCHIVE_DIR}" \\\n',
                "",
            )
            script.write_text(text, encoding="utf-8")

            result = self.run_checker(root, "--contract", "agent_canon_pr_check")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-required-text:agent_canon_pr_check:"
                "tools/ci/check_agent_canon_pr.sh:"
                "missing-agent-canon-pr-hook-archive-env",
                result.stdout,
            )

    def test_pr_check_must_run_generated_artifact_guard(self) -> None:
        """The AgentCanon PR check must reject regenerated report leftovers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_agent_canon_pr_contract(root)
            script = root / "tools" / "ci" / "check_agent_canon_pr.sh"
            text = script.read_text(encoding="utf-8").replace(
                'python3 "${CANON_TOOLS_ROOT}/agent_tools/generated_artifact_guard.py" --root "${WORKSPACE_ROOT}"\n',
                "",
            )
            script.write_text(text, encoding="utf-8")

            result = self.run_checker(root, "--contract", "generated_artifact_guard")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-required-command:generated_artifact_guard:"
                "tools/ci/check_agent_canon_pr.sh:"
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
                    "tools/agent_tools/tool_catalog.py",
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

    def test_subagent_wave_routing_requires_policy_marker(self) -> None:
        """Subagent wave routing drift is caught as a tool contract."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_subagent_wave_routing_contract(root)
            workflow = root / "agents" / "canonical" / "CODEX_SUBAGENTS.md"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    "vertical dynamic wave",
                    "flat wave",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "subagent_wave_routing")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-required-text:subagent_wave_routing:"
                "agents/canonical/CODEX_SUBAGENTS.md:"
                "missing-canonical-vertical-wave-policy",
                result.stdout,
            )

    def test_subagent_wave_routing_requires_write_capable_handoff(self) -> None:
        """Subagent wave routing requires write-capable handoff marker as contract text."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_subagent_wave_routing_contract(root)
            orchestrated = root / "agents" / "canonical" / "CODEX_SUBAGENTS.md"
            orchestrated.write_text(
                orchestrated.read_text(encoding="utf-8").replace(
                    "write-capable handoff",
                    "",
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "subagent_wave_routing")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-required-text:subagent_wave_routing:"
                "agents/canonical/CODEX_SUBAGENTS.md:"
                "missing-canonical-write-capable-handoff-policy",
                result.stdout,
            )
            self.assertNotIn(
                ".agents/skills/agent-orchestration/SKILL.md", result.stdout
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
            "tools/agent_tools/check_convention_compliance.py",
            "\n".join(
                [
                    "# @dependency-start",
                    "# responsibility Checks convention compliance.",
                    "# upstream design ../../documents/conventions/README.md conventions",
                    "# upstream design ../../agents/canonical/CODEX_WORKFLOW.md workflow",
                    "# upstream design ../../agents/canonical/CODEX_SUBAGENTS.md subagents",
                    "# upstream design ../../agents/TASK_WORKFLOWS.md workflows",
                    "# upstream design ../../agents/skills/agent-orchestration.md orchestration",
                    "# upstream design ../../evidence/agent-evals/skill_workflow_prompt_eval.toml evals",
                    "# upstream design ../../templates/agents/closeout_gate.md closeout",
                    "# upstream implementation ../ci/run_all_checks.sh ci",
                    "# upstream implementation ./tool_drift.py drift gate",
                    "# @dependency-end",
                    "",
                ]
            ),
        )
        for relative in [
            "documents/conventions/README.md",
            "agents/canonical/CODEX_WORKFLOW.md",
            "agents/canonical/CODEX_SUBAGENTS.md",
            "agents/TASK_WORKFLOWS.md",
            "agents/skills/agent-orchestration.md",
            "evidence/agent-evals/skill_workflow_prompt_eval.toml",
            "templates/agents/closeout_gate.md",
            "tools/ci/run_all_checks.sh",
            "tools/agent_tools/tool_drift.py",
        ]:
            self.write_plain_manifest(root, relative)

    def write_subagent_wave_routing_contract(self, root: Path) -> None:
        """Write fixtures for the subagent wave routing contract."""
        self.write_file(root, "README.md", "# Fixture\n")
        self.write_file(
            root,
            "tools/agent_tools/tool_drift.py",
            "\n".join(
                [
                    "# @dependency-start",
                    "# responsibility Detects fixture tool drift.",
                    "# upstream design ../../agents/canonical/CODEX_SUBAGENTS.md subagents",
                    "# upstream design ../../agents/TASK_WORKFLOWS.md workflows",
                    "# upstream design ../../agents/skills/agent-orchestration.md orchestration",
                    "# upstream design ../../evidence/agent-evals/skill_workflow_prompt_eval.toml evals",
                    "# upstream implementation ./check_convention_compliance.py convention gate",
                    "# downstream implementation ../../tests/agent_tools/test_tool_drift.py tests",
                    "# @dependency-end",
                    "",
                ]
            ),
        )
        for relative in [
            "agents/canonical/CODEX_SUBAGENTS.md",
            "agents/TASK_WORKFLOWS.md",
            "agents/skills/agent-orchestration.md",
            "tools/agent_tools/check_convention_compliance.py",
        ]:
            self.write_file(
                root,
                relative,
                "\n".join(
                    [
                        "<!--",
                        "@dependency-start",
                        "responsibility Provides subagent wave routing fixture.",
                        "upstream design README.md fixture anchor",
                        "@dependency-end",
                        "-->",
                        "Intake Responsibility Wave",
                        "write-capable handoff",
                        "dynamic expansion wave",
                        "run.delegated_spawn_policy",
                        "stage owner vertical dynamic wave",
                        "",
                    ]
                ),
            )
        self.write_file(
            root,
            "evidence/agent-evals/skill_workflow_prompt_eval.toml",
            "VERTICAL-WAVE-POLICY ORCH-SHIM-POINTER-1 ORCH-SHIM-TOOLCALL-1\n",
        )
        self.write_file(
            root,
            "tests/agent_tools/test_tool_drift.py",
            "# fixture test vertical dynamic wave\n",
        )

    def write_tool_rejection_preflight_contract(self, root: Path) -> None:
        """Write fixtures for the tool rejection preflight contract."""
        self.write_file(
            root,
            "tools/agent_tools/tool_rejection_preflight.py",
            "\n".join(
                [
                    "# @dependency-start",
                    "# responsibility Prechecks edit-time risk class.",
                    "# upstream design ../../agents/COMMUNICATION_PROTOCOL.md protocol",
                    "# upstream design ../../agents/skills/codex-task-workflow.md workflow",
                    "# upstream design ../../agents/skills/owner-bounded-routing.md owner-bounded",
                    "# upstream design ../../tools/agent_tools/responsibility_scope.py scope",
                    "# upstream implementation ../../tests/agent_tools/test_tool_rejection_preflight.py scope preflight",
                    "# @dependency-end",
                    "",
                ]
            ),
        )
        for relative in [
            "agents/COMMUNICATION_PROTOCOL.md",
            "agents/skills/codex-task-workflow.md",
            "agents/skills/owner-bounded-routing.md",
            "tools/agent_tools/responsibility_scope.py",
            "tools/README.md",
            "documents/tools/README.md",
            "tests/agent_tools/test_tool_rejection_preflight.py",
        ]:
            if relative in {
                "agents/skills/codex-task-workflow.md",
                "agents/skills/owner-bounded-routing.md",
                "agents/COMMUNICATION_PROTOCOL.md",
            }:
                snippet = (
                    "`responsibility_scope` gate records"
                    if relative == "agents/COMMUNICATION_PROTOCOL.md"
                    else "responsibility_scope"
                )
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
            else:
                self.write_plain_manifest(root, relative)

    def write_agent_canon_pr_contract(self, root: Path) -> None:
        """Write fixtures for the AgentCanon PR check contract."""
        self.write_file(root, "README.md", "# Fixture\n")
        self.write_file(
            root,
            "tools/ci/check_agent_canon_pr.sh",
            "\n".join(
                [
                    "# @dependency-start",
                    "# responsibility Checks AgentCanon PR readiness.",
                    "# upstream design ../../agents/workflows/agent-canon-pr-workflow.md workflow",
                    "# upstream design ../../.github/PULL_REQUEST_TEMPLATE.md standalone template",
                    "# upstream design ../../.github/PULL_REQUEST_TEMPLATE/agent_canon.md template checklist",
                    "# upstream design ../../templates/documents/github/pull-request/agent_canon.md template checklist",
                    "# upstream implementation ../agent_tools/run_repo_dependency_review.sh dependency review",
                    "# upstream implementation ../agent_tools/run_accumulated_agent_evals.py accumulated evals",
                    "# upstream implementation ../agent_tools/generated_artifact_guard.py generated artifact guard",
                    "# upstream implementation ../agent_tools/evaluate_skill_workflow_prompts.py prompt eval",
                    "# upstream implementation ../agent_tools/check_agent_runtime_alignment.py runtime alignment",
                    "# upstream implementation ../agent_tools/check_convention_compliance.py convention gate",
                    "# upstream implementation ./agent_canon_pr_graph_selector.py graph selector",
                    "# upstream implementation ./check_github_workflows.py github checks",
                    "# @dependency-end",
                    "agentcanon_pr_dependency_graph_required() { return 0; }",
                    'python3 "${CANON_TOOLS_ROOT}/ci/agent_canon_pr_graph_selector.py"',
                    "PR_GATE_DEPENDENCY_GRAPH_STATUS=skipped",
                    "if agentcanon_pr_dependency_graph_required; then",
                    '  bash "${CANON_TOOLS_ROOT}/agent_tools/run_repo_dependency_review.sh" --fail-missing --cycle-report-only --changed-path-packet "${PR_GATE_DEPENDENCY_CHANGED_PATH_PACKET}" --trusted-base-sha "${PR_GATE_DEPENDENCY_GRAPH_BASE_SHA}" --report-dir "${PR_DEPENDENCY_REVIEW_DIR}"',
                    "  PR_GATE_DEPENDENCY_GRAPH_STATUS=prepared",
                    "fi",
                    "printf 'selector_reason=%s\\n' \"${PR_GATE_DEPENDENCY_GRAPH_REASON}\"",
                    "printf 'selector_evidence=%s\\n' \"${PR_GATE_DEPENDENCY_GRAPH_EVIDENCE}\"",
                    'write_pr_gate_receipt "${PR_GATE_DEPENDENCY_GRAPH_STATUS}" "${PR_GATE_DEPENDENCY_GRAPH_REASON}" "${PR_GATE_DEPENDENCY_GRAPH_EVIDENCE}"',
                    'AGENT_CANON_HOOK_ARCHIVE_DIR="${PR_HOOK_ARCHIVE_DIR}" \\',
                    'python3 "${CANON_TOOLS_ROOT}/agent_tools/run_accumulated_agent_evals.py" --run-id agent-canon-pr-gate --log-dir "${PR_AGENT_EVAL_LOG_DIR}"',
                    'python3 "${CANON_TOOLS_ROOT}/agent_tools/generated_artifact_guard.py" --root "${WORKSPACE_ROOT}"',
                    'python3 "${CANON_TOOLS_ROOT}/agent_tools/check_agent_runtime_alignment.py"',
                    "python3 tools/agent_tools/evaluate_skill_workflow_prompts.py --manifest evidence/agent-evals/skill_workflow_prompt_eval.toml",
                    "SHARED_SURFACE_STATUS=not_applicable_standalone_source",
                    "",
                ]
            ),
        )
        self.write_file(
            root,
            "tools/ci/agent_canon_pr_graph_selector.py",
            "\n".join(
                [
                    "# @dependency-start",
                    "# responsibility Selects parent graph gating.",
                    "# downstream implementation ./check_agent_canon_pr.sh PR gate",
                    "# @dependency-end",
                    "",
                ]
            ),
        )
        for relative in [
            "agents/workflows/agent-canon-pr-workflow.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",
            "templates/documents/github/pull-request/agent_canon.md",
            "tools/agent_tools/run_repo_dependency_review.sh",
            "tools/agent_tools/run_accumulated_agent_evals.py",
            "tools/agent_tools/generated_artifact_guard.py",
            "tools/agent_tools/evaluate_skill_workflow_prompts.py",
            "tools/agent_tools/check_agent_runtime_alignment.py",
            "tools/agent_tools/check_convention_compliance.py",
            "tools/ci/check_github_workflows.py",
        ]:
            self.write_plain_manifest(root, relative)

    def write_tool_catalog_contract(self, root: Path) -> None:
        """Write fixtures for the tool catalog contract."""
        self.write_file(root, "README.md", "# Fixture\n")
        self.write_file(
            root,
            "tools/agent_tools/tool_catalog.py",
            "\n".join(
                [
                    "# @dependency-start",
                    "# responsibility Validates tool catalog.",
                    "# upstream design ../../tools/catalog.yaml catalog",
                    "# upstream design ../../tools/README.md tool docs",
                    "# upstream design ../../documents/tools/README.md root docs",
                    "# upstream design ../../documents/tools/tool-docs.toml docs map",
                    "# upstream design ../../documents/tools/repo-local-tool-imports.md imports",
                    "# downstream implementation ../../tools/ci/run_all_checks.sh ci",
                    "# downstream implementation ../../tests/agent_tools/test_tool_catalog.py tests",
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
                    "# downstream implementation agent_tools/tool_catalog.py checker",
                    "# @dependency-end",
                    "",
                    "version: 1",
                    "entries:",
                    "  - id: tool-catalog",
                    "    path: tools/agent_tools/tool_catalog.py",
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
            "tools/ci/run_all_checks.sh",
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
                        "downstream implementation tools/agent_tools/tool_catalog.py checker",
                        "@dependency-end",
                        "-->",
                        "tools/catalog.yaml",
                        "tool_catalog.py",
                        "documents/tools/tool-docs.toml",
                        "",
                    ]
                ),
            )


if __name__ == "__main__":
    unittest.main()
