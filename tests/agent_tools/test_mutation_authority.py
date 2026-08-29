# @dependency-start
# contract test
# responsibility Tests runtime parent-mutation rejection and authenticated child-scope admission.
# upstream implementation ../../tools/runtime/authority/mutation_authority.py owns mutation authority.
# upstream implementation ../../.codex/hooks/hook_dispatcher.py applies the PreToolUse decision.
# @dependency-end
"""Focused tests for parent orchestration-only mutation control."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from tools.runtime.authority.mutation_authority import (  # noqa: E402
    IDENTITY_SCHEMA,
    evaluate_mutation_authority,
)


def write_identity(
    report_dir: Path,
    *,
    role_id: str,
    agent_id: str = "child-1",
    parent_agent_id: str = "parent-1",
    allowed_files: list[str] | None = None,
    allowed_directories: list[str] | None = None,
) -> None:
    value: dict[str, object] = {
        "schema": IDENTITY_SCHEMA,
        "run_id": "run-1",
        "agent_id": agent_id,
        "role_id": role_id,
        "parent_agent_id": parent_agent_id,
        "authority": "write_capable_child",
        "allowed_files": allowed_files or ["src/owned.py"],
        "allowed_directories": allowed_directories or [],
        "scope_digest": "",
        "status": "active",
        "receipt_sha256": "",
    }
    value["scope_digest"] = hashlib.sha256(
        json.dumps(
            {
                "allowed_files": value["allowed_files"],
                "allowed_directories": value["allowed_directories"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    unsigned = dict(value)
    unsigned.pop("receipt_sha256")
    value["receipt_sha256"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    target = report_dir / "runtime" / "agent_identity.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def write_writer_packet(root: Path) -> None:
    packet = {
        "schema": "agent-canon.writer-target-packet.v1",
        "checkout_root": str(root),
        "branch": "test",
        "remote": "local/repo",
        "allowed_paths": ["src/"],
        "checkout_identity": {
            "cwd": str(root),
            "git_root": str(root),
            "branch": "test",
            "head": "a" * 40,
            "remote": "local/repo",
        },
    }
    target = root / ".agent-canon" / "writer-target.json"
    target.parent.mkdir()
    target.write_text(json.dumps(packet, sort_keys=True), encoding="utf-8")


def write_spawn_event(root: Path) -> None:
    identity = json.loads((root / "runtime" / "agent_identity.json").read_text(encoding="utf-8"))
    target = root / "spawn.json"
    target.write_text(
        json.dumps(
            {
                "subagent_event_kind": "spawn",
                "subagent_target": identity["agent_id"],
                "subagent_agent_type": "worker",
                "mutation_scope_digest": identity["scope_digest"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


class MutationAuthorityTest(unittest.TestCase):
    def env(self, *, agent_id: str = "child-1", role_id: str = "implementer", parent_agent_id: str = "parent-1") -> dict[str, str]:
        return {
            "AGENT_CANON_RUNTIME_AGENT_ID": agent_id,
            "AGENT_CANON_RUNTIME_ROLE_ID": role_id,
            "AGENT_CANON_RUNTIME_PARENT_AGENT_ID": parent_agent_id,
        }

    def test_parent_mutation_is_rejected_even_with_matching_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity(root, role_id="parent")
            decision = evaluate_mutation_authority(
                {"tool_name": "Bash", "tool_input": {"command": "touch src/owned.py"}},
                report_dir=root,
                active_root=root,
                environment=self.env(role_id="parent"),
            )
            self.assertEqual(decision.status, "blocked")
            self.assertEqual(decision.reason, "parent_mutation_forbidden")

    def test_child_mutation_requires_scope_and_identity_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity(root, role_id="implementer")
            write_spawn_event(root)
            write_writer_packet(root)
            payload = {
                "tool_name": "apply_patch",
                "tool_input": {"patch": "*** Begin Patch\n*** Update File: src/owned.py\n*** End Patch\n"},
            }
            decision = evaluate_mutation_authority(
                payload,
                report_dir=root,
                active_root=root,
                environment=self.env(),
                hook_spool_root=root,
            )
            self.assertEqual(decision.status, "allowed")
            outside = evaluate_mutation_authority(
                {"tool_name": "apply_patch", "tool_input": {"patch": "*** Begin Patch\n*** Update File: README.md\n*** End Patch\n"}},
                report_dir=root,
                active_root=root,
                environment=self.env(),
                hook_spool_root=root,
            )
            self.assertEqual(outside.status, "blocked")
            self.assertEqual(outside.reason, "mutation_scope_outside_child_receipt")

    def test_missing_or_forged_identity_blocks_mutation_but_readback_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = {"tool_name": "apply_patch", "tool_input": {"patch": "*** Begin Patch\n*** Update File: src/owned.py\n*** End Patch\n"}}
            missing = evaluate_mutation_authority(
                payload, report_dir=root, active_root=root, environment=self.env()
            )
            self.assertEqual(missing.reason, "blocked_authority_required")
            write_identity(root, role_id="implementer")
            receipt = root / "runtime" / "agent_identity.json"
            receipt.write_text(receipt.read_text(encoding="utf-8").replace("child-1", "forged"), encoding="utf-8")
            forged = evaluate_mutation_authority(
                payload, report_dir=root, active_root=root, environment=self.env()
            )
            self.assertEqual(forged.reason, "blocked_authority_required")
            readback = evaluate_mutation_authority(
                {"tool_name": "Bash", "tool_input": {"command": "git status --short"}},
                report_dir=root,
                active_root=root,
                environment={},
            )
            self.assertEqual(readback.status, "not_applicable")

    def test_wrappers_and_interpreters_are_not_read_only(self) -> None:
        """Wrapper/interpreter routes require child authority just like direct writes."""
        commands = (
            "python3 script.py",
            "python -c 'open(\"x\", \"w\").write(\"x\")'",
            "bash -lc 'touch x'",
            "sh -c 'echo x > x'",
        )
        for command in commands:
            with self.subTest(command=command):
                decision = evaluate_mutation_authority(
                    {"tool_name": "Bash", "tool_input": {"command": command}},
                    report_dir=None,
                    active_root=Path("."),
                    environment={},
                )
                self.assertEqual(decision.status, "blocked")


if __name__ == "__main__":
    unittest.main()
