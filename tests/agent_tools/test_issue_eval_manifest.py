"""Tests for issue-derived eval manifest coverage."""

# @dependency-start
# contract test
# responsibility Tests issue-derived eval manifest coverage for AgentCanon closeout issues.
# upstream implementation ../../evidence/agent-evals/issue_eval_manifest.toml registers issue-derived eval rows.
# upstream design ../../agents/skills/comprehensive-development.md owns regression admission mappings.
# upstream design ../../agents/skills/change-review.md owns regression evidence review and completion adjudication.
# upstream design ../../documents/codex/prompt-skill-evaluation-checklist.md defines eval closeout expectations.
# downstream implementation ../../tools/agent_tools/eval_accumulation_check.py validates eval accumulation surfaces.
# @dependency-end

from __future__ import annotations

import copy
import unittest
from pathlib import Path
from typing import cast

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = PROJECT_ROOT / "evidence" / "agent-evals" / "issue_eval_manifest.toml"
REQUIRED_CLOSEOUT_ISSUES = {
    83,
    97,
    98,
    99,
    100,
    101,
    102,
    103,
    104,
    106,
    114,
    115,
    117,
    118,
    119,
    120,
    761,
}

ISSUE_761_EVAL_ID = "canonical-regression-contract-integration"
ISSUE_761_PROTECTS = (
    (
        "representative historical regressions are admitted through canonical "
        "invariant and boundary oracles"
    ),
    "generated skill shims remain projection-only consumers of canonical policy owners",
    "focused reproduction passes do not substitute for canonical acceptance",
)
ISSUE_761_EXPECTED_ROUTES = (
    (
        "cleanup / rollback / audit preservation => lifecycle / recovery / audit "
        "invariant => terminal / nonterminal, interruption, repeated attempt, "
        "partial-effect rollback"
    ),
    (
        "concurrency / reservation / idempotent retry => reservation protocol / "
        "state-transition / idempotency invariant => zero / one / many contenders, "
        "duplicate request, capacity boundary, interleaving"
    ),
    (
        "wait / backoff / timeout / cancel => temporal / liveness / cancellation "
        "invariant => pre-timeout / at-timeout / post-timeout, cancel before / after "
        "effect, retry exhaustion"
    ),
    (
        "payment / refund / discount / tax normalization / rounding => monetary "
        "normalization / ordering / precision invariant => zero / negative, ordering, "
        "precision limit, rounding tie"
    ),
    (
        "empty / malformed / legacy input shape => parser / compatibility invariant "
        "=> omitted, empty, scalar, malformed, legacy shape"
    ),
    (
        "multi-binding / submodule / generated-file ownership / projection drift => "
        "single-owner source identity / projection invariant => zero / one / many "
        "bindings, stale pin / source digest, generated drift"
    ),
    (
        "PASS / FAIL / NOT_RUN, missing artifacts, stale evidence => completion-state "
        "/ evidence identity invariant => status-artifact cross-product, missing "
        "artifact, stale evidence, clean-replay contradiction"
    ),
    (
        "extend the existing comprehensive-development and change-review owners "
        "instead of introducing a standalone regression taxonomy"
    ),
    (
        "run focused diagnosis first and require the owner-selected canonical "
        "boundary acceptance before completion"
    ),
)
ISSUE_761_FORBIDDEN_ROUTES = (
    "add a standalone regression taxonomy or a second checker for issue 761",
    "copy canonical regression policy into generated consumer shims",
    "promote a focused pass to canonical acceptance",
    (
        "accept contradictory PASS / FAIL / NOT_RUN state, missing eval artifact, "
        "or stale evidence as completed"
    ),
)
ISSUE_761_LINKED_RULES = (
    "agents/skills/comprehensive-development.md",
    "agents/skills/change-review.md",
    ".agents/skills/comprehensive-development/SKILL.md",
    ".agents/skills/change-review/SKILL.md",
    "evidence/agent-evals/issue_eval_manifest.toml",
    "tests/agent_tools/test_issue_eval_manifest.py",
)
ISSUE_761_TABLE_PHRASES = (
    (
        "| Historical failure family | Canonical invariant / owner class | "
        "Minimal boundary / counterexample set | Canonical oracle |"
    ),
    "cleanup / rollback / audit preservation",
    "terminal / nonterminal、interruption、repeated attempt、partial-effect rollback",
    "concurrency / reservation / idempotent retry",
    "zero / one / many contenders、duplicate request、capacity boundary、interleaving",
    "wait / backoff / timeout / cancel",
    "pre-timeout / at-timeout / post-timeout、cancel before / after effect",
    "payment / refund / discount / tax normalization / rounding",
    "discount-tax-refund ordering、precision limit、rounding tie",
    "empty / malformed / legacy input shape",
    "omitted、empty、scalar、malformed、legacy shape",
    "multi-binding / submodule / generated-file ownership / projection drift",
    "zero / one / many bindings、stale pin / source digest、generated drift",
    "PASS / FAIL / NOT_RUN、missing artifacts、stale evidence",
    "status-artifact cross-product、missing artifact、stale evidence",
)
ISSUE_761_SHIMS = (
    (
        PROJECT_ROOT / ".agents" / "skills" / "comprehensive-development" / "SKILL.md",
        "../../../agents/skills/comprehensive-development.md",
    ),
    (
        PROJECT_ROOT / ".agents" / "skills" / "change-review" / "SKILL.md",
        "../../../agents/skills/change-review.md",
    ),
)


class IssueEvalManifestTest(unittest.TestCase):
    """Validate the issue eval manifest used for closeout evidence."""

    def load_manifest(self) -> dict[str, object]:
        """Load the manifest TOML."""
        return tomllib.loads(MANIFEST.read_text(encoding="utf-8"))

    def eval_rows(self) -> list[dict[str, object]]:
        """Return every well-formed eval row."""
        rows = self.load_manifest().get("eval")
        self.assertIsInstance(rows, list)
        return [
            cast(dict[str, object], row)
            for row in cast(list[object], rows)
            if isinstance(row, dict)
        ]

    def issue_row(self, source_issue: int) -> dict[str, object]:
        """Return the unique eval row for one issue."""
        matches = [
            row for row in self.eval_rows() if row.get("source_issue") == source_issue
        ]
        self.assertEqual(len(matches), 1, f"source_issue={source_issue}")
        return matches[0]

    def string_field(self, row: dict[str, object], field: str) -> set[str]:
        """Return one all-string list field as a set."""
        value = row.get(field)
        self.assertIsInstance(value, list, field)
        items = cast(list[object], value)
        self.assertTrue(all(isinstance(item, str) for item in items), field)
        return {cast(str, item) for item in items}

    def assert_issue_761_contract(self, row: dict[str, object]) -> None:
        """Assert the canonical #761 invariant/boundary integration contract."""
        self.assertEqual(row.get("id"), ISSUE_761_EVAL_ID)
        self.assertEqual(row.get("category"), "insufficient-evidence")
        self.assertEqual(row.get("oracle_type"), "machine")
        self.assertTrue(
            set(ISSUE_761_PROTECTS) <= self.string_field(row, "protects"),
            "protects",
        )
        self.assertTrue(
            set(ISSUE_761_EXPECTED_ROUTES)
            <= self.string_field(row, "expected_route"),
            "expected_route",
        )
        self.assertTrue(
            set(ISSUE_761_FORBIDDEN_ROUTES)
            <= self.string_field(row, "forbidden_route"),
            "forbidden_route",
        )
        self.assertTrue(
            set(ISSUE_761_LINKED_RULES) <= self.string_field(row, "linked_rules"),
            "linked_rules",
        )

    def assert_issue_761_canonical_table(self, text: str) -> None:
        """Assert that every representative family and boundary remains in the table."""
        for phrase in ISSUE_761_TABLE_PHRASES:
            self.assertIn(phrase, text)

    def test_closeout_issue_set_has_eval_coverage(self) -> None:
        """Every issue in the bulk closeout set has at least one eval row."""
        covered = {
            row.get("source_issue")
            for row in self.eval_rows()
            if isinstance(row.get("source_issue"), int)
        }

        self.assertFalse(REQUIRED_CLOSEOUT_ISSUES - covered)

    def test_eval_ids_are_unique(self) -> None:
        """Eval IDs should remain stable unique lookup keys."""
        ids = [row.get("id") for row in self.eval_rows()]

        self.assertEqual(len(ids), len(set(ids)))

    def test_issue_761_maps_representative_regressions_to_canonical_oracles(
        self,
    ) -> None:
        """The issue row and owner table cover representative boundary families."""
        self.assert_issue_761_contract(self.issue_row(761))
        canonical = (
            PROJECT_ROOT / "agents" / "skills" / "comprehensive-development.md"
        ).read_text(encoding="utf-8")
        self.assert_issue_761_canonical_table(canonical)

    def test_issue_761_checker_rejects_incomplete_or_contradictory_evidence(
        self,
    ) -> None:
        """The existing checker fails closed on each material evidence omission."""
        row = self.issue_row(761)
        mutations = (
            ("expected_route", ISSUE_761_EXPECTED_ROUTES[0]),
            (
                "linked_rules",
                "evidence/agent-evals/issue_eval_manifest.toml",
            ),
            (
                "forbidden_route",
                (
                    "accept contradictory PASS / FAIL / NOT_RUN state, missing eval "
                    "artifact, or stale evidence as completed"
                ),
            ),
        )

        for field, omitted in mutations:
            incomplete = copy.deepcopy(row)
            incomplete[field] = [
                item for item in self.string_field(incomplete, field) if item != omitted
            ]
            with self.subTest(field=field, omitted=omitted):
                with self.assertRaises(AssertionError):
                    self.assert_issue_761_contract(incomplete)

        canonical = (
            PROJECT_ROOT / "agents" / "skills" / "comprehensive-development.md"
        ).read_text(encoding="utf-8")
        missing_boundary = canonical.replace(
            ISSUE_761_TABLE_PHRASES[2],
            "",
            1,
        )
        with self.assertRaises(AssertionError):
            self.assert_issue_761_canonical_table(missing_boundary)

    def test_issue_761_generated_consumers_are_projection_only(self) -> None:
        """Generated runtime shims point to owners without copying their policy."""
        forbidden_policy_fragments = (
            "## Regression Evidence Admission",
            "## Regression Evidence Review",
            "Historical failure family",
            "focused reproduction passes do not substitute",
        )
        for shim, canonical_target in ISSUE_761_SHIMS:
            text = shim.read_text(encoding="utf-8")
            with self.subTest(shim=shim):
                self.assertIn("materialization-record:", text)
                self.assertIn(
                    f"upstream design {canonical_target} owner",
                    text,
                )
                self.assertIn(
                    f"]({canonical_target})",
                    text,
                )
                for fragment in forbidden_policy_fragments:
                    self.assertNotIn(fragment, text)

    def test_issue_761_separates_focused_diagnosis_from_acceptance(self) -> None:
        """Both canonical owners reject focused-only completion claims."""
        comprehensive = (
            PROJECT_ROOT / "agents" / "skills" / "comprehensive-development.md"
        ).read_text(encoding="utf-8")
        review = (
            PROJECT_ROOT / "agents" / "skills" / "change-review.md"
        ).read_text(encoding="utf-8")

        for phrase in (
            "focused test は counterexample",
            "canonical boundary / acceptance",
            "verified completion",
        ):
            self.assertIn(phrase, comprehensive)
        for phrase in (
            "focused test の pass は",
            "canonical validation route",
            "remaining verification",
        ):
            self.assertIn(phrase, review)


if __name__ == "__main__":
    unittest.main()
