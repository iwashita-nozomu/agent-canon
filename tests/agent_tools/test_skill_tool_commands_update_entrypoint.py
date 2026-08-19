"""Regression tests for optional AgentCanon update aliases in command packets."""

# @dependency-start
# contract test
# responsibility Tests fail-closed selection and runtime projection between parent-owned Make aliases and canonical AgentCanon owner commands.
# upstream implementation ../../tools/agent_tools/skill_tool_commands.py runtime packet and optional-alias owner
# upstream implementation ../../tools/agent_tools/agent_canon_source_root.py standalone/vendored root identity
# upstream design ../../agents/skills/agent-canon-update.md update entrypoint contract
# @dependency-end

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from agent_canon_source_root import RootResolution  # noqa: E402
from skill_tool_commands import (  # noqa: E402
    make_target_is_explicit,
    packet_for_skill,
    project_public_command,
    resolve_optional_agent_canon_make_alias,
    validate_command_plan_executables,
)


class AgentCanonUpdateAliasTest(unittest.TestCase):
    """Keep Make inspection read-only, literal, and fail-closed."""

    def test_absent_aliases_resolve_to_owner_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "Makefile").write_text("ci:\n\t@true\n", encoding="utf-8")

            expected = {
                "make agent-canon-update-plan": "plan",
                "make agent-canon-latest": "latest",
                "make agent-canon-ensure-latest": "latest",
            }
            for command, mode in expected.items():
                with self.subTest(command=command):
                    resolved = resolve_optional_agent_canon_make_alias(command, root)
                    self.assertEqual(
                        resolved,
                        "PYTHONPATH=vendor/agent-canon/tools:tools "
                        "python3 -m agent_tools.agent_canon_source_root exec "
                        f"tools/update_agent_canon.sh {mode}",
                    )
                    self.assertNotIn("make agent-canon-", resolved)

    def test_explicit_aliases_remain_parent_owned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "Makefile").write_text(
                ".PHONY: agent-canon-update-plan agent-canon-latest "
                "agent-canon-ensure-latest\n"
                "agent-canon-update-plan:\n\t@true\n"
                "agent-canon-latest agent-canon-ensure-latest: ; @true\n",
                encoding="utf-8",
            )

            for target in (
                "agent-canon-update-plan",
                "agent-canon-latest",
                "agent-canon-ensure-latest",
            ):
                command = f"make {target}"
                with self.subTest(target=target):
                    self.assertTrue(make_target_is_explicit(root, target))
                    self.assertEqual(
                        resolve_optional_agent_canon_make_alias(command, root),
                        command,
                    )

    def test_phony_or_assignment_text_does_not_admit_missing_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "Makefile").write_text(
                ".PHONY: agent-canon-ensure-latest\n"
                "agent-canon-ensure-latest := not-a-target\n",
                encoding="utf-8",
            )

            self.assertFalse(make_target_is_explicit(root, "agent-canon-ensure-latest"))
            self.assertIn(
                "tools/update_agent_canon.sh latest",
                resolve_optional_agent_canon_make_alias(
                    "make agent-canon-ensure-latest", root
                ),
            )

    def test_define_and_conditional_bodies_are_not_target_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "Makefile").write_text(
                "define DOCUMENTED_ALIAS\n"
                "agent-canon-ensure-latest:\n"
                "\t@true\n"
                "endef\n"
                "ifeq ($(ENABLE_AGENT_CANON_ALIAS),1)\n"
                "agent-canon-latest:\n"
                "\t@true\n"
                "endif\n"
                "agent-canon-update-plan:\n"
                "\t@true\n",
                encoding="utf-8",
            )

            self.assertTrue(
                make_target_is_explicit(root, "agent-canon-update-plan")
            )
            self.assertFalse(
                make_target_is_explicit(root, "agent-canon-latest")
            )
            self.assertFalse(
                make_target_is_explicit(root, "agent-canon-ensure-latest")
            )

    def test_assignment_value_with_colon_is_not_target_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "Makefile").write_text(
                "DOCUMENTED_ALIAS = agent-canon-ensure-latest:\n",
                encoding="utf-8",
            )

            self.assertFalse(
                make_target_is_explicit(root, "agent-canon-ensure-latest")
            )
            self.assertIn(
                "tools/update_agent_canon.sh latest",
                resolve_optional_agent_canon_make_alias(
                    "make agent-canon-ensure-latest", root
                ),
            )

    def test_resolution_never_evaluates_makefile_functions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            sentinel = root / "must-not-exist"
            (root / "Makefile").write_text(
                f"SIDE_EFFECT := $(shell touch {sentinel})\n"
                "ci:\n\t@true\n",
                encoding="utf-8",
            )

            resolve_optional_agent_canon_make_alias(
                "make agent-canon-update-plan", root
            )

            self.assertFalse(sentinel.exists())

    def test_mutation_authority_environment_is_forwarded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            command = (
                "AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:abc "
                "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval "
                "make agent-canon-ensure-latest"
            )

            resolved = resolve_optional_agent_canon_make_alias(command, root)

            self.assertIn("AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:abc", resolved)
            self.assertIn(
                "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval",
                resolved,
            )
            self.assertTrue(resolved.endswith("tools/update_agent_canon.sh latest"))

    def test_non_agentcanon_make_commands_are_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.assertEqual(
                resolve_optional_agent_canon_make_alias("make ci", root),
                "make ci",
            )


class SkillToolCommandsUpdateEntrypointTest(unittest.TestCase):
    """Verify live-parent fallback and explicit-alias compatibility."""

    @staticmethod
    def _fixture(tmp_dir: str, makefile: str | None) -> tuple[Path, Path, RootResolution]:
        parent = Path(tmp_dir)
        source = parent / "vendor" / "agent-canon"
        (source / "agents" / "skills").mkdir(parents=True)
        (source / "agents" / "skills" / "catalog.yaml").write_text(
            "version: 1\nskill_families: []\n",
            encoding="utf-8",
        )
        (source / "tools").mkdir(parents=True)
        (source / "tools" / "update_agent_canon.sh").write_text(
            "#!/usr/bin/env bash\nexit 0\n",
            encoding="utf-8",
        )
        public = parent / "vendor" / "agent-canon" / "tools"
        public.mkdir(parents=True, exist_ok=True)
        (public / "update_agent_canon.sh").write_text(
            "#!/usr/bin/env bash\nexit 0\n",
            encoding="utf-8",
        )
        if makefile is not None:
            (parent / "Makefile").write_text(makefile, encoding="utf-8")
        resolution = RootResolution(
            current_repository_root=parent,
            source_root=source,
            layout="vendored",
            canon_root=source,
            public_tool_root=public,
        )
        return parent, source, resolution

    @staticmethod
    def _spec() -> SimpleNamespace:
        return SimpleNamespace(
            structured=True,
            required=(),
            conditional=(
                "make agent-canon-update-plan",
                "make agent-canon-latest",
                "make agent-canon-ensure-latest",
            ),
            maintenance=(),
        )

    def test_missing_parent_targets_publish_only_owner_tool_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            _parent, source, resolution = self._fixture(tmp_dir, "ci:\n\t@true\n")
            with (
                patch(
                    "skill_tool_commands.load_skill_tool_commands",
                    return_value={"agent-canon-update": self._spec()},
                ),
                patch("skill_tool_commands.load_skill_related_map", return_value={}),
            ):
                packet = packet_for_skill(resolution, "agent-canon-update")

            self.assertEqual(len(packet.conditional_commands), 3)
            self.assertNotIn("make agent-canon-", "\n".join(packet.conditional_commands))
            self.assertTrue(packet.conditional_commands[0].endswith("update_agent_canon.sh plan"))
            self.assertTrue(packet.conditional_commands[1].endswith("update_agent_canon.sh latest"))
            self.assertTrue(packet.conditional_commands[2].endswith("update_agent_canon.sh latest"))
            for row in packet.resolved_conditional_commands:
                self.assertIn(str((source / "tools" / "update_agent_canon.sh").resolve()), row[4])
            validate_command_plan_executables(resolution, packet)

            projection = project_public_command(
                packet.conditional_commands[0],
                resolution,
            )
            self.assertEqual(
                projection.public_env,
                (("PYTHONPATH", "vendor/agent-canon/tools"),),
            )
            self.assertIn(
                "vendor/agent-canon/tools/update_agent_canon.sh",
                projection.public_argv,
            )

    def test_explicit_parent_targets_remain_packet_aliases(self) -> None:
        makefile = (
            "agent-canon-update-plan:\n\t@true\n"
            "agent-canon-latest:\n\t@true\n"
            "agent-canon-ensure-latest:\n\t@true\n"
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            _parent, _source, resolution = self._fixture(tmp_dir, makefile)
            with (
                patch(
                    "skill_tool_commands.load_skill_tool_commands",
                    return_value={"agent-canon-update": self._spec()},
                ),
                patch("skill_tool_commands.load_skill_related_map", return_value={}),
            ):
                packet = packet_for_skill(resolution, "agent-canon-update")

            self.assertEqual(packet.conditional_commands, self._spec().conditional)


if __name__ == "__main__":
    unittest.main()
