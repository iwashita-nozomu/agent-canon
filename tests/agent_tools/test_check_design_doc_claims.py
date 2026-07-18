"""Tests for design-document claim evidence checker."""

# @dependency-start
# contract test
# responsibility Tests design-document claim evidence checker behavior.
# upstream design ../../documents/design/README.md design-document evidence policy
# upstream implementation ../../tools/agent_tools/check_design_doc_claims.py checks design claims
# upstream implementation ../../tools/agent_tools/graph_client.py validates persisted graph context
# upstream implementation ../../tools/agent_tools/check_dependency_graph.sh provides dependency graph semantics
# @dependency-end

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.agent_tools import check_design_doc_claims as graph_claim_checker
from tools.agent_tools.graph_client import GraphResponse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "check_design_doc_claims.py"


def run_checker(*args: str, root: Path) -> subprocess.CompletedProcess[str]:
    """Run the checker in one fixture repo."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def write(path: Path, text: str) -> None:
    """Write a dedented fixture file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")


class DesignDocClaimCheckerTest(unittest.TestCase):
    """Exercise deterministic design claim checks."""

    def test_pass_claim_supported_by_direct_implementation_evidence(self) -> None:
        """A design claim passes when dependency evidence contains the token."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "documents" / "design" / "feature.md",
                """
                # Feature Design
                <!--
                @dependency-start
                responsibility Documents Feature Design fixture.
                downstream implementation ../../tools/feature_runner.py runner implementation
                @dependency-end
                -->

                ## Evidence And Assumption Ledger

                - Evidence sources: `tools/feature_runner.py`.
                - Assumptions: current fixture uses direct implementation evidence.

                ## Claims

                - The design must route work through `run_feature`.
                """,
            )
            write(
                root / "tools" / "feature_runner.py",
                """
                # @dependency-start
                # responsibility Implements feature runner fixture.
                # upstream design ../documents/design/feature.md feature design
                # @dependency-end

                def run_feature() -> None:
                    pass
                """,
            )

            result = run_checker("documents/design/feature.md", root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DESIGN_DOC_CLAIMS=pass", result.stdout)
            self.assertIn("DESIGN_DOC_CLAIMS_CHECKED=1", result.stdout)

    def test_dependency_manifest_lines_are_not_claims(self) -> None:
        """Dependency header route lines are evidence metadata, not body claims."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "documents" / "design" / "feature.md",
                """
                # Feature Design
                <!--
                @dependency-start
                responsibility Documents Feature Design fixture.
                upstream implementation ../../tools/feature_runner.py runner implementation
                downstream design sibling.md sibling design
                @dependency-end
                -->

                ## Context

                Descriptive text.
                """,
            )
            write(
                root / "documents" / "design" / "sibling.md",
                """
                # Sibling
                """,
            )
            write(
                root / "tools" / "feature_runner.py",
                """
                def run_feature() -> None:
                    pass
                """,
            )

            result = run_checker("documents/design/feature.md", root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DESIGN_DOC_CLAIMS=pass", result.stdout)
            self.assertIn("DESIGN_DOC_CLAIMS_CHECKED=0", result.stdout)

    def test_reference_document_prose_without_tokens_is_not_design_claim(self) -> None:
        """Reference docs keep cue-only prose out of design-claim enforcement."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "documents" / "tools" / "guide.md",
                """
                # Tool Guide
                <!--
                @dependency-start
                contract reference
                responsibility Documents a reference guide fixture.
                upstream design ../README.md fixture index
                @dependency-end
                -->

                This guide must preserve reader flow.
                """,
            )
            write(
                root / "documents" / "README.md",
                """
                # Docs
                """,
            )

            result = run_checker("documents/tools/guide.md", root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DESIGN_DOC_CLAIMS=pass", result.stdout)
            self.assertIn("DESIGN_DOC_CLAIMS_CHECKED=0", result.stdout)

    def test_reference_document_placeholder_token_is_not_design_claim(self) -> None:
        """Ellipsis placeholders document command families without exact evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "documents" / "tools" / "guide.md",
                """
                # Tool Guide
                <!--
                @dependency-start
                contract reference
                responsibility Documents a reference guide fixture.
                upstream design ../README.md fixture index
                @dependency-end
                -->

                Use `agent-canon semantic-index ...` for the command family.
                """,
            )
            write(root / "documents" / "README.md", "# Docs\n")

            result = run_checker("documents/tools/guide.md", root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DESIGN_DOC_CLAIMS=pass", result.stdout)
            self.assertIn("DESIGN_DOC_CLAIMS_CHECKED=0", result.stdout)

    def test_relative_parent_path_token_resolves_to_repo_path(self) -> None:
        """Parent-relative Markdown path tokens resolve from the claim file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "tools" / "README.md",
                """
                # Tools
                <!--
                @dependency-start
                contract reference
                responsibility Documents tool guide fixture.
                upstream design ../documents/contract.md fixture contract
                @dependency-end
                -->

                ## Evidence And Assumption Ledger

                - Evidence sources: `../documents/contract.md`.
                - Assumptions: relative paths are operator-facing links.

                The reader guide points to `../documents/contract.md`.
                """,
            )
            write(root / "documents" / "contract.md", "# Contract\n")

            result = run_checker("tools/README.md", root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DESIGN_DOC_CLAIMS=pass", result.stdout)

    def test_fail_parent_relative_path_token_does_not_collapse_to_repo_root(self) -> None:
        """Parent-relative path claims do not fall back to unrelated root files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "documents" / "tools" / "guide.md",
                """
                # Tool Guide
                <!--
                @dependency-start
                contract design
                responsibility Documents nested tool guide fixture.
                upstream design ../README.md fixture docs index
                @dependency-end
                -->

                ## Evidence And Assumption Ledger

                - Evidence sources: `../README.md`.
                - Assumptions: parent-relative links are resolved from the guide.

                The guide must read `../README.md`.
                """,
            )
            write(root / "README.md", "# Root Docs\n")

            result = run_checker("documents/tools/guide.md", root=root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("claim-token-without-evidence", result.stdout)
            self.assertIn("token=../README.md", result.stdout)

    def test_wildcard_and_status_tokens_can_be_supported_by_evidence(self) -> None:
        """Wildcard and key-value status tokens match implementation evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "documents" / "design" / "feature.md",
                """
                # Feature Design
                <!--
                @dependency-start
                responsibility Documents Feature Design fixture.
                downstream implementation ../../tools/feature_runner.py runner implementation
                @dependency-end
                -->

                ## Evidence And Assumption Ledger

                - Evidence sources: `tools/feature_runner.py`.
                - Assumptions: wildcard and status tokens describe emitted output.

                ## Claims

                - The design records `TOKEN_FOOTPRINT_*`.
                - The loop can record `goal_status: blocked`.
                - The comparator emits `NEXT_ACTION=repair_skill_workflow_prompt`.
                """,
            )
            write(
                root / "tools" / "feature_runner.py",
                """
                TOKEN_FOOTPRINT_COMPARISON = "pass"
                goal_status = "blocked"
                print(f"NEXT_ACTION={repair_skill_workflow_prompt}")
                """,
            )

            result = run_checker("documents/design/feature.md", root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DESIGN_DOC_CLAIMS=pass", result.stdout)

    def test_request_contract_claim_is_typed_as_request_contract(self) -> None:
        """Request-contract claims are emitted as request_contract records."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "documents" / "design" / "feature.md",
                """
                # Feature Design
                <!--
                @dependency-start
                responsibility Documents Feature Design fixture.
                downstream implementation ../../tools/feature_runner.py runner implementation
                @dependency-end
                -->

                ## Evidence And Assumption Ledger

                - Evidence sources: `tools/feature_runner.py`.
                - Assumptions: request-contract claim is test-only.

                ## Claims

                - The design must satisfy request-contract `RC-10`.
                """,
            )
            write(
                root / "tools" / "feature_runner.py",
                """
                def run_feature() -> None:
                    pass
                """,
            )

            result = run_checker("--format", "json", "documents/design/feature.md", root=root)
            payload = json.loads(result.stdout)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(payload["status"], "pass")
            records = payload["documents"][0]["claim_evidence_records"]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["evidence_class"], "request_contract")
            self.assertEqual(records[0]["status"], "verified")

    def test_target_state_claim_reports_target_state_class(self) -> None:
        """Target-state claims are typed and accepted as approved_pending_implementation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "documents" / "design" / "feature.md",
                """
                # Feature Design
                <!--
                @dependency-start
                contract design
                responsibility Documents Feature Design fixture.
                upstream design ../README.md feature design
                @dependency-end
                -->

                ## Evidence And Assumption Ledger

                - Evidence sources: `documents/README.md`.
                - Assumptions: target-state projection is not yet implemented.

                ## Claims

                - The design route requires target state `e8ae83767a4c3a7edb10a59f611c9f949ac8ea0563dcf844329f2be95c9a2762`.
                """,
            )
            write(root / "documents" / "README.md", "# Docs\n")

            result = run_checker("--format", "json", "documents/design/feature.md", root=root)
            payload = json.loads(result.stdout)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(payload["status"], "pass")
            records = payload["documents"][0]["claim_evidence_records"]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["evidence_class"], "target_state")
            self.assertEqual(records[0]["status"], "approved_pending_implementation")

    def test_fail_key_value_token_requires_same_record_evidence(self) -> None:
        """A key and value in separate evidence records do not support a pair claim."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "documents" / "design" / "feature.md",
                """
                # Feature Design
                <!--
                @dependency-start
                responsibility Documents Feature Design fixture.
                downstream implementation ../../tools/feature_runner.py runner implementation
                @dependency-end
                -->

                ## Evidence And Assumption Ledger

                - Evidence sources: `tools/feature_runner.py`.
                - Assumptions: status tokens must describe emitted output records.

                ## Claims

                - The loop can record `goal_status: blocked`.
                """,
            )
            write(
                root / "tools" / "feature_runner.py",
                """
                goal_status = "ready"
                message = "worker blocked on unrelated condition"
                """,
            )

            result = run_checker("documents/design/feature.md", root=root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("claim-token-without-evidence", result.stdout)
            self.assertIn("token=goal_status: blocked", result.stdout)

    def test_fail_claim_without_evidence_after_recursive_expansion(self) -> None:
        """A missing token remains visible after recursive header expansion."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "documents" / "design" / "child.md",
                """
                # Child Design
                <!--
                @dependency-start
                responsibility Documents Child Design fixture.
                upstream design parent.md parent design
                @dependency-end
                -->

                ## Evidence And Assumption Ledger

                - Evidence sources: `parent.md`.
                - Assumptions: recursive parent design provides the context.

                ## Claims

                - The design must call `missing_symbol`.
                """,
            )
            write(
                root / "documents" / "design" / "parent.md",
                """
                # Parent Design
                <!--
                @dependency-start
                responsibility Documents Parent Design fixture.
                downstream design child.md child design
                @dependency-end
                -->

                Parent text mentions `other_symbol`.
                """,
            )

            result = run_checker("documents/design/child.md", root=root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("claim-token-without-evidence", result.stdout)
            self.assertIn("token=missing_symbol", result.stdout)

    def test_fail_natural_language_claim_without_checkable_token(self) -> None:
        """A modal claim line needs a checkable evidence token."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "documents" / "design" / "feature.md",
                """
                # Feature Design
                <!--
                @dependency-start
                responsibility Documents Feature Design fixture.
                upstream design parent.md parent design
                @dependency-end
                -->

                ## Evidence And Assumption Ledger

                - Evidence sources: parent design.
                - Assumptions: current fixture exercises prose-only claims.

                ## Claims

                - The design must preserve the behavior.
                """,
            )
            write(
                root / "documents" / "design" / "parent.md",
                """
                # Parent
                <!--
                @dependency-start
                responsibility Documents Parent fixture.
                downstream design feature.md feature design
                @dependency-end
                -->
                """,
            )

            result = run_checker("documents/design/feature.md", root=root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("claim-without-checkable-token", result.stdout)

    def test_fail_missing_explicit_design_path(self) -> None:
        """An explicit missing design path is reported as a finding."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)

            result = run_checker("documents/design/missing.md", root=root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("design-document-unresolved", result.stdout)

    def test_recursive_dependency_evidence_supports_claim(self) -> None:
        """A transitive implementation dependency can support a child claim."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "documents" / "design" / "child.md",
                """
                # Child Design
                <!--
                @dependency-start
                responsibility Documents Child Design fixture.
                upstream design parent.md parent design
                @dependency-end
                -->

                ## Evidence And Assumption Ledger

                - Evidence sources: `parent.md` and `tools/engine.py`.
                - Assumptions: recursive dependency expansion reaches implementation evidence.

                ## Claims

                - The design must call `engine_step`.
                """,
            )
            write(
                root / "documents" / "design" / "parent.md",
                """
                # Parent Design
                <!--
                @dependency-start
                responsibility Documents Parent Design fixture.
                downstream design child.md child design
                downstream implementation ../../tools/engine.py engine implementation
                @dependency-end
                -->
                """,
            )
            write(
                root / "tools" / "engine.py",
                """
                # @dependency-start
                # responsibility Implements engine fixture.
                # upstream design ../documents/design/parent.md parent design
                # @dependency-end

                def engine_step() -> None:
                    pass
                """,
            )

            result = run_checker("documents/design/child.md", root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DESIGN_DOC_CLAIMS=pass", result.stdout)

    def test_parent_design_contradiction_is_reported(self) -> None:
        """Opposite modal polarity over the same code token is a finding."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "documents" / "design" / "child.md",
                """
                # Child Design
                <!--
                @dependency-start
                responsibility Documents Child Design fixture.
                upstream design parent.md parent design
                @dependency-end
                -->

                ## Evidence And Assumption Ledger

                - Evidence sources: `parent.md`.
                - Assumptions: child keeps parent-doc alignment evidence.

                ## Claims

                - The design must use `legacy_route`.
                """,
            )
            write(
                root / "documents" / "design" / "parent.md",
                """
                # Parent Design
                <!--
                @dependency-start
                responsibility Documents Parent Design fixture.
                downstream design child.md child design
                @dependency-end
                -->

                - The parent design must not use `legacy_route`.
                """,
            )

            result = run_checker("documents/design/child.md", root=root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("parent-document-contradiction", result.stdout)
            self.assertIn("token=legacy_route", result.stdout)

    def test_implicit_assumption_term_requires_ledger_entry(self) -> None:
        """DSL and standard-form terms are tracked through the assumption ledger."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "documents" / "design" / "dsl.md",
                """
                # DSL Design
                <!--
                @dependency-start
                responsibility Documents DSL Design fixture.
                upstream design parent.md parent design
                @dependency-end
                -->

                ## Evidence And Assumption Ledger

                - Evidence sources: `parent.md`.
                - Assumptions: standard form is inherited from the parent design.

                ## Claims

                - The design maps the DSL into the problem standard form.
                """,
            )
            write(
                root / "documents" / "design" / "parent.md",
                """
                # Parent Design
                <!--
                @dependency-start
                responsibility Documents Parent Design fixture.
                downstream design dsl.md child design
                @dependency-end
                -->
                """,
            )

            result = run_checker("documents/design/dsl.md", root=root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("implicit-assumption-term-untracked", result.stdout)
            self.assertIn("term=DSL", result.stdout)

    def test_reports_path_is_not_used_as_manifest_evidence(self) -> None:
        """Generated report paths stay outside dependency evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "documents" / "design" / "feature.md",
                """
                # Feature Design
                <!--
                @dependency-start
                responsibility Documents Feature Design fixture.
                downstream implementation ../../reports/generated.py generated report
                @dependency-end
                -->

                ## Evidence And Assumption Ledger

                - Evidence sources: current implementation.
                - Assumptions: generated reports are review artifacts.

                ## Claims

                - The design must call `generated_only`.
                """,
            )
            write(
                root / "reports" / "generated.py",
                """
                def generated_only() -> None:
                    pass
                """,
            )

            result = run_checker("documents/design/feature.md", root=root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("claim-token-without-evidence", result.stdout)

    def test_json_output_is_stable(self) -> None:
        """JSON output exposes machine-readable result shape."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "documents" / "design" / "feature.md",
                """
                # Feature Design
                <!--
                @dependency-start
                responsibility Documents Feature Design fixture.
                @dependency-end
                -->
                """,
            )

            result = run_checker("--format", "json", "documents/design/feature.md", root=root)
            payload = json.loads(result.stdout)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["finding_count"], 0)


class FakeDesignGraphClient:
    """Provide graph-owned context without rerunning the graph producer."""

    def __init__(self, _root: Path, *, status: str = "fresh") -> None:
        self._status = status

    def status(self) -> SimpleNamespace:
        return SimpleNamespace(
            status=self._status,
            exit_code=0 if self._status == "fresh" else 2,
        )

    def context(self, path: str) -> GraphResponse:
        payload = {
            "schema": "agent-canon.graph.context.v1",
            "command": "context",
            "status": self._status,
            "resolved_path": path,
            "source_identity": {
                "snapshot_commit": "a" * 40,
                "source_path": path,
                "content_sha256": "b" * 64,
            },
            "evidence_paths": [path, "tools/feature_runner.py"],
            "parent_paths": [],
        }
        return GraphResponse(
            "agent-canon.graph.context.v1",
            "context",
            self._status,
            payload,
            0 if self._status == "fresh" else 2,
        )


class DesignDocGraphConsumerTest(unittest.TestCase):
    """Exercise consume-only graph context and freshness refusal."""

    def run_main(
        self,
        root: Path,
        graph: FakeDesignGraphClient,
        *paths: str,
    ) -> tuple[int, str]:
        output = io.StringIO()
        (root / ".git").mkdir(exist_ok=True)
        argv = ["check_design_doc_claims.py", "--root", str(root), *paths]
        with (
            patch.object(sys, "argv", argv),
            patch.object(graph_claim_checker, "GraphClient", lambda _root: graph),
            contextlib.redirect_stdout(output),
        ):
            result = graph_claim_checker.main()
        return result, output.getvalue()

    def test_check_one_consumes_graph_context_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "documents/design/feature.md",
                """
                # Feature Design

                ## Evidence And Assumption Ledger

                - Evidence: `tools/feature_runner.py`.

                ## Claims

                - The design must route work through `run_feature`.
                """,
            )
            write(
                root / "tools/feature_runner.py",
                """
                def run_feature() -> None:
                    pass
                """,
            )
            result, output = self.run_main(
                root,
                FakeDesignGraphClient(root),
                "documents/design/feature.md",
            )
            self.assertEqual(result, 0, output)
            self.assertIn("DESIGN_DOC_CLAIMS=pass", output)

    def test_stale_graph_context_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(root / "documents/design/feature.md", "# Feature Design\n")
            result, output = self.run_main(
                root,
                FakeDesignGraphClient(root, status="stale"),
                "documents/design/feature.md",
            )
            self.assertNotEqual(result, 0)
            self.assertIn("graph snapshot is not fresh", output)

    def test_graph_context_without_identity_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(root / "documents/design/feature.md", "# Feature Design\n")
            graph = FakeDesignGraphClient(root)
            missing_identity = GraphResponse(
                "agent-canon.graph.context.v1",
                "context",
                "fresh",
                {"resolved_path": "documents/design/feature.md"},
                0,
            )
            with patch.object(graph, "context", return_value=missing_identity):
                result, output = self.run_main(
                    root,
                    graph,
                    "documents/design/feature.md",
                )
            self.assertNotEqual(result, 0)
            self.assertIn("graph context did not resolve", output)


if __name__ == "__main__":
    unittest.main()
