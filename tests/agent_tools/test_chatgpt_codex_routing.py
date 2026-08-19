"""Finite-relation tests for ChatGPT/Codex request-modality routing."""

# ruff: noqa: D101, D102, D103

# @dependency-start
# contract test
# responsibility Validates ChatGPT closure, Codex execution, conflict, input, and monotonicity invariants.
# upstream design ../../agents/internal-routines/chatgpt-codex-routing.md owns route semantics.
# upstream implementation ../../tools/agent_tools/chatgpt_codex_routing.py implements the decision relation.
# @dependency-end

from __future__ import annotations

import itertools
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "agent_tools"))

import chatgpt_codex_routing as routing  # noqa: E402


class ChatgptCodexRoutingTest(unittest.TestCase):
    def packet(
        self,
        facts: routing.RoutingFacts,
        *,
        codex_scope: str = "edit and validate the repository",
        validation_oracle: str = "selected repository checks pass",
    ) -> routing.RoutePacket:
        return routing.decide_route(
            facts=facts,
            requested_deliverable="complete the requested result",
            chatgpt_scope="interpret the request and present the result",
            codex_scope=codex_scope,
            validation_oracle=validation_oracle,
        )

    def test_conversation_only_cases_close_in_chatgpt(self) -> None:
        cases = {
            "explanation": routing.RoutingFacts(),
            "summary_of_supplied_text": routing.RoutingFacts(),
            "translation": routing.RoutingFacts(),
            "read_only_web_or_connector_research": routing.RoutingFacts(),
            "explicit_chat_only": routing.RoutingFacts(explicit_chat_only=True),
        }
        for name, facts in cases.items():
            with self.subTest(name=name):
                packet = self.packet(facts)
                self.assertEqual(packet.route, "chatgpt")
                self.assertEqual(packet.handoff, "none")
                self.assertEqual(packet.codex_scope, "none")
                self.assertEqual(packet.validation_oracle, "none")

    def test_each_execution_fact_routes_to_codex(self) -> None:
        for field in routing.EXECUTION_REASON_FIELDS:
            with self.subTest(field=field):
                packet = self.packet(routing.RoutingFacts(**{field: True}))
                self.assertEqual(packet.route, "codex")
                self.assertEqual(packet.reason_codes, (field,))
                self.assertEqual(packet.handoff, "agent-orchestration")
                self.assertEqual(packet.blocked_dependency, "none")

    def test_mixed_request_keeps_canonical_reason_order(self) -> None:
        facts = routing.RoutingFacts(
            workspace_or_repository_mutation=True,
            command_test_build_benchmark_runtime_observation_required=True,
            durable_repository_delivery_required=True,
        )
        packet = self.packet(facts)
        self.assertEqual(
            packet.reason_codes,
            (
                "workspace_or_repository_mutation",
                "command_test_build_benchmark_runtime_observation_required",
                "durable_repository_delivery_required",
            ),
        )
        self.assertEqual(packet.route, "codex")

    def test_explicit_chat_only_blocks_required_execution_without_mutation(self) -> None:
        packet = self.packet(
            routing.RoutingFacts(
                workspace_or_repository_mutation=True,
                explicit_chat_only=True,
            )
        )
        self.assertEqual(packet.route, "chatgpt")
        self.assertEqual(packet.handoff, "none")
        self.assertEqual(packet.reason_codes[0], "explicit_chat_only_conflict")
        self.assertIn("explicitly prohibited", packet.blocked_dependency)
        self.assertNotEqual(packet.codex_scope, "none")

    def test_codex_route_requires_execution_scope_and_oracle(self) -> None:
        facts = routing.RoutingFacts(workspace_or_repository_mutation=True)
        with self.assertRaises(routing.RoutingInputError) as context:
            self.packet(facts, codex_scope="none")
        self.assertEqual(context.exception.code, "missing_execution_scope")
        with self.assertRaises(routing.RoutingInputError) as context:
            self.packet(facts, validation_oracle="none")
        self.assertEqual(context.exception.code, "missing_validation_oracle")

    def test_mapping_rejects_unknown_or_non_boolean_facts(self) -> None:
        with self.assertRaises(routing.RoutingInputError) as context:
            routing.facts_from_mapping({"complexity_score": 9})
        self.assertEqual(context.exception.code, "unknown_field")
        with self.assertRaises(routing.RoutingInputError) as context:
            routing.facts_from_mapping({"workspace_or_repository_mutation": 1})
        self.assertEqual(context.exception.code, "invalid_boolean")

    def test_codex_predicate_is_monotone_over_all_execution_fact_sets(self) -> None:
        fields = routing.EXECUTION_REASON_FIELDS
        vectors = tuple(itertools.product((False, True), repeat=len(fields)))
        for lower in vectors:
            lower_packet = self.packet(
                routing.RoutingFacts(**dict(zip(fields, lower, strict=True)))
            )
            for upper in vectors:
                if not all((not left) or right for left, right in zip(lower, upper, strict=True)):
                    continue
                upper_packet = self.packet(
                    routing.RoutingFacts(**dict(zip(fields, upper, strict=True)))
                )
                if lower_packet.route == "codex":
                    self.assertEqual(upper_packet.route, "codex")

    def test_packet_from_mapping_is_exact_and_json_compatible(self) -> None:
        packet = routing.packet_from_mapping(
            {
                "requested_deliverable": "open a validated pull request",
                "facts": {"durable_repository_delivery_required": True},
                "chatgpt_scope": "resolve intent",
                "codex_scope": "create the branch, commit, and pull request",
                "validation_oracle": "pull request checks pass",
            }
        )
        self.assertEqual(packet.route, "codex")
        self.assertEqual(packet.as_dict()["reason_codes"], ["durable_repository_delivery_required"])
        with self.assertRaises(routing.RoutingInputError) as context:
            routing.packet_from_mapping(
                {
                    "requested_deliverable": "answer",
                    "facts": {},
                    "chatgpt_scope": "answer",
                    "score": 1,
                }
            )
        self.assertEqual(context.exception.code, "unknown_field")


if __name__ == "__main__":
    unittest.main()
