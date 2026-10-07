"""Tests for design-document claim evidence checker."""

# @dependency-start
# contract test
# responsibility Tests design-document claim evidence checker behavior.
# upstream design ../../documents/design/README.md design-document evidence policy
# upstream implementation ../../tools/validation/semantic/documents/check_design_doc_claims.py checks design claims
# upstream implementation ../../tools/analysis/dependencies/check_dependency_graph.sh provides dependency graph semantics
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tools.validation.semantic.documents import (
    check_design_doc_claims as graph_claim_checker,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    PROJECT_ROOT
    / "tools"
    / "validation"
    / "semantic"
    / "documents"
    / "check_design_doc_claims.py"
)


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


def git(root: Path, *args: str) -> None:
    """Run one Git operation in a fixture repository."""
    subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    )


def init_git(root: Path) -> None:
    """Create a deterministic Git baseline for changed-scope fixtures."""
    git(root, "init", "-q")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "user.name", "Fixture")


class DesignDocClaimCheckerTest(unittest.TestCase):
    """Exercise deterministic design claim checks."""

    def test_github_issue_reference_is_not_an_implementation_token(self) -> None:
        """Issue/PR references are routing evidence, not source symbols."""
        self.assertEqual(
            graph_claim_checker.checkable_tokens(
                "Track implementation in `iwashita-nozomu/agent-canon#821`."
            ),
            (),
        )

    def test_changed_scope_keeps_active_claims_and_ignores_retired_history_and_tables(
        self,
    ) -> None:
        """Changed mode gates only new active implementation claims."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "documents/design/active.md",
                """
                # Active Design
                <!--
                @dependency-start
                contract design
                responsibility Documents active fixture.
                downstream implementation ../../tools/runner.py runner evidence
                @dependency-end
                -->

                ## Evidence And Assumption Ledger

                - Evidence sources: `tools/runner.py`.
                - Assumptions: the active implementation owns the route.

                ## Claims

                - The design must route through `old_missing_symbol`.
                """,
            )
            write(
                root / "documents/design/retired.md",
                """
                # Retired: old design
                <!--
                @dependency-start
                contract design
                responsibility Retired fixture redirect.
                downstream implementation ../../tools/runner.py old evidence
                @dependency-end
                -->

                ## Evidence And Assumption Ledger

                - Evidence sources: `tools/runner.py`.
                - Assumptions: this route is historical only.

                The former design must use `retired_old_symbol`.
                """,
            )
            write(
                root / "documents/design/historical.md",
                """
                # Historical: old design
                <!--
                @dependency-start
                contract design
                responsibility Documents historical fixture.
                downstream implementation ../../tools/runner.py old evidence
                @dependency-end
                -->

                ## Evidence And Assumption Ledger

                - Evidence sources: `tools/runner.py`.
                - Assumptions: this route is historical only.

                The historical design must use `historical_old_symbol`.
                """,
            )
            write(
                root / "documents/design/evidence-table.md",
                """
                # Evidence Table Design
                <!--
                @dependency-start
                contract design
                responsibility Documents evidence-table fixture.
                downstream implementation ../../tools/runner.py table evidence
                @dependency-end
                -->

                ## Evidence And Assumption Ledger

                - Evidence sources: `tools/runner.py`.
                - Assumptions: table rows are fixed evidence records.

                | Kind | Evidence |
                | --- | --- |
                | existing | `run_feature` |
                """,
            )
            write(root / "tools/runner.py", "def run_feature() -> None:\n    pass\n")
            init_git(root)
            git(root, "add", ".")
            git(root, "commit", "-qm", "fixture baseline")

            with (root / "documents/design/active.md").open(
                "a", encoding="utf-8"
            ) as stream:
                stream.write(
                    "\n- The design must route through [runner](../../tools/runner.py).\n"
                )
            with (root / "documents/design/retired.md").open(
                "a", encoding="utf-8"
            ) as stream:
                stream.write("\n- The retired route must use `retired_new_symbol`.\n")
            with (root / "documents/design/historical.md").open(
                "a", encoding="utf-8"
            ) as stream:
                stream.write(
                    "\n- The historical route must use `historical_new_symbol`.\n"
                )
            with (root / "documents/design/evidence-table.md").open(
                "a", encoding="utf-8"
            ) as stream:
                stream.write("\n| new | `unknown_generated_label` |\n")

            selected = graph_claim_checker.changed_design_paths(root)
            self.assertEqual(selected, ("documents/design/active.md",))
            result = run_checker("--changed", root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DESIGN_DOC_CLAIMS_DOCUMENTS=1", result.stdout)
            self.assertIn("DESIGN_DOC_CLAIMS_CHECKED=1", result.stdout)
            self.assertIn("DESIGN_DOC_CLAIMS_FINDINGS=0", result.stdout)

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

                - The design must route work through [runner](../../tools/feature_runner.py).
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

    def test_explicit_path_does_not_require_graph_snapshot(self) -> None:
        """Source evidence remains usable without graph status or identity receipts."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".git").mkdir()
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

                - Evidence sources: [runner](../../tools/feature_runner.py).
                - Assumptions: direct implementation evidence.

                The design must route work through [runner](../../tools/feature_runner.py).
                """,
            )
            write(
                root / "tools" / "feature_runner.py",
                "def run_feature() -> None:\n    pass\n",
            )

            result = run_checker("documents/design/feature.md", root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DESIGN_DOC_CLAIMS=pass", result.stdout)

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

    def test_relative_current_path_link_resolves_from_claim_file(self) -> None:
        """A ./ Markdown link keeps ordinary document-relative semantics."""
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
                @dependency-end
                -->

                ## Evidence And Assumption Ledger

                - Evidence sources: [source](./source.py).
                - Assumptions: current-directory links are document-relative.

                The guide must read [the source](./source.py).
                """,
            )
            write(root / "documents" / "tools" / "source.py", "VALUE = 1\n")

            result = run_checker("documents/tools/guide.md", root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DESIGN_DOC_CLAIMS=pass", result.stdout)

    def test_fail_parent_relative_path_token_does_not_collapse_to_repo_root(
        self,
    ) -> None:
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

                The guide must read [the README](../README.md).
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

    def test_key_value_code_span_is_ordinary_prose(self) -> None:
        """A key/value example is not promoted to a private claim language."""
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

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DESIGN_DOC_CLAIMS_CHECKED=0", result.stdout)

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

                - The design must call [the missing symbol](../../tools/missing_symbol.py).
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
            write(
                root / "tools" / "legacy_route.py",
                "def legacy_route() -> None:\n    pass\n",
            )

            result = run_checker("documents/design/child.md", root=root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("claim-token-without-evidence", result.stdout)
            self.assertIn("token=../../tools/missing_symbol.py", result.stdout)

    def test_natural_language_claim_without_link_is_ordinary_prose(self) -> None:
        """A modal prose line is not a private claim grammar entry."""
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

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DESIGN_DOC_CLAIMS_CHECKED=0", result.stdout)

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

                - The design must call [the engine](../../tools/engine.py).
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

            result = run_checker(
                "--recursive-depth",
                "2",
                "documents/design/child.md",
                root=root,
            )

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

                - The design must use [the legacy route](../../tools/legacy_route.py).
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

                - The parent design must not use [the legacy route](../../tools/legacy_route.py).
                """,
            )
            write(
                root / "tools" / "legacy_route.py",
                "def legacy_route() -> None:\n    pass\n",
            )

            result = run_checker("documents/design/child.md", root=root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("parent-document-contradiction", result.stdout)
            self.assertIn("token=../../tools/legacy_route.py", result.stdout)

    def test_dsl_terms_are_not_implicit_ledger_requirements(self) -> None:
        """DSL and standard-form prose does not activate a private ledger grammar."""
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

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DESIGN_DOC_CLAIMS_CHECKED=0", result.stdout)

    def test_generated_report_example_is_ordinary_prose(self) -> None:
        """A generated-report code span is not an implicit evidence reference."""
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

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DESIGN_DOC_CLAIMS_CHECKED=0", result.stdout)

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

            result = run_checker(
                "--format", "json", "documents/design/feature.md", root=root
            )
            payload = json.loads(result.stdout)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["finding_count"], 0)


if __name__ == "__main__":
    unittest.main()
