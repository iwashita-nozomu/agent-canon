"""Tests for coordinated search index generation."""

# @dependency-start
# contract test
# responsibility Tests repo-local search-card index generation and local LLM preflight behavior.
# upstream implementation ../../tools/agent_tools/search_index.py builds local LLM semantic cards
# upstream design ../../documents/search-coordination.md coordinated search provider contract
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEARCH_INDEX = PROJECT_ROOT / "tools" / "agent_tools" / "search_index.py"


def write_tool_registry(root: Path) -> None:
    """Write a minimal tool catalog."""
    (root / "tools").mkdir(parents=True, exist_ok=True)
    (root / "tools" / "catalog.yaml").write_text(
        "\n".join(
            [
                "version: 1",
                "entries:",
                "  - id: dependency-graph",
                "    summary: Validates dependency graph edit scope.",
                "    path: tools/dependency_graph.py",
                "    family: agent_tools",
                "    role: checker",
                "    docs:",
                "      - documents/dependency-graph.md",
                "    tests:",
                "      - tests/test_dependency_graph.py",
            ]
        ),
        encoding="utf-8",
    )


def write_tool(root: Path) -> None:
    """Write one indexed tool file."""
    (root / "tools" / "dependency_graph.py").write_text(
        "\n".join(
            [
                "# @dependency-start",
                "# responsibility Validates dependency graph edit scope.",
                "# upstream design ../documents/dependency-graph.md dependency graph policy",
                "# downstream implementation ../tests/test_dependency_graph.py regression tests",
                "# @dependency-end",
                "def check_dependency_graph():",
                "    return 'graph scope'",
            ]
        ),
        encoding="utf-8",
    )


def run_index(
    root: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run search_index.py against a temporary root."""
    return subprocess.run(
        [sys.executable, str(SEARCH_INDEX), *args, "--root", str(root)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


class SearchIndexTest(unittest.TestCase):
    """Verify search-card generation."""

    def test_build_writes_tool_card_and_state(self) -> None:
        """Build should persist ignored repo-local card and state files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_tool_registry(root)
            write_tool(root)

            result = run_index(root, "build", "--surface", "tools", "--format", "json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "pass")
            card_file = root / ".agent-canon" / "search-index" / "llm-cards.jsonl"
            state_file = root / ".agent-canon" / "search-index" / "index-state.json"
            self.assertTrue(card_file.is_file())
            self.assertTrue(state_file.is_file())
            cards = [json.loads(line) for line in card_file.read_text(encoding="utf-8").splitlines()]
            tool_cards = [card for card in cards if card["path"] == "tools/dependency_graph.py"]
            self.assertEqual(tool_cards[0]["kind"], "tool")
            self.assertEqual(tool_cards[0]["related_tools"], ["dependency-graph"])

    def test_build_prunes_legacy_token_tool_cards(self) -> None:
        """Search cards must not preserve retired legacy-like implementation paths."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_tool_registry(root)
            write_tool(root)
            (root / "tools" / "search_legacy.py").write_text(
                "def retired_search():\n    return 'legacyonlyneedle'\n",
                encoding="utf-8",
            )

            result = run_index(root, "build", "--surface", "tools", "--format", "json")

            self.assertEqual(result.returncode, 0, result.stderr)
            card_file = root / ".agent-canon" / "search-index" / "llm-cards.jsonl"
            cards = [json.loads(line) for line in card_file.read_text(encoding="utf-8").splitlines()]
            paths = {card["path"] for card in cards}
            self.assertIn("tools/dependency_graph.py", paths)
            self.assertNotIn("tools/search_legacy.py", paths)

    def test_required_llm_missing_fails_before_index_write(self) -> None:
        """A required unavailable local LLM must fail explicitly."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_tool_registry(root)
            write_tool(root)

            result = run_index(
                root,
                "build",
                "--surface",
                "tools",
                "--run-llm",
                "--require-llm",
                "--llama-cli",
                str(root / "missing-llama-cli"),
                env={
                    "AGENT_CANON_TOOLS_HOME": str(root / ".tools"),
                    "HOME": str(root),
                    "PATH": "",
                },
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("SEARCH_INDEX_ERROR=llama-cli-not-found", result.stderr)
            self.assertFalse((root / ".agent-canon" / "search-index" / "llm-cards.jsonl").exists())

    def test_run_llm_hides_accelerator_devices(self) -> None:
        """LLM-backed search cards should run llama-cli with CPU-only visibility."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            fake_llama = root / "llama-cli"
            env_log = root / "llama-env.log"
            write_tool_registry(root)
            write_tool(root)
            fake_llama.write_text(
                "#!/usr/bin/env bash\n"
                "{\n"
                "  printf 'CUDA_VISIBLE_DEVICES=%s\\n' \"${CUDA_VISIBLE_DEVICES-unset}\"\n"
                "  printf 'NVIDIA_VISIBLE_DEVICES=%s\\n' \"${NVIDIA_VISIBLE_DEVICES-unset}\"\n"
                "  printf 'HIP_VISIBLE_DEVICES=%s\\n' \"${HIP_VISIBLE_DEVICES-unset}\"\n"
                "  printf 'ROCR_VISIBLE_DEVICES=%s\\n' \"${ROCR_VISIBLE_DEVICES-unset}\"\n"
                "  printf 'AGENT_CANON_TEST_MARKER=%s\\n' \"${AGENT_CANON_TEST_MARKER-unset}\"\n"
                "} >\"$AGENT_CANON_TEST_ENV_LOG\"\n"
                "printf '%s\\n' '{\"summary\":\"refined\",\"concepts\":[\"cpu\"],\"aliases\":[],\"responsibility\":\"CPU-only local LLM\",\"ambiguity_notes\":[]}'\n",
                encoding="utf-8",
            )
            fake_llama.chmod(0o755)

            result = run_index(
                root,
                "build",
                "--surface",
                "tools",
                "--run-llm",
                "--require-llm",
                "--llama-cli",
                str(fake_llama),
                "--max-llm-files",
                "1",
                "--format",
                "json",
                env={
                    "CUDA_VISIBLE_DEVICES": "0",
                    "NVIDIA_VISIBLE_DEVICES": "0",
                    "HIP_VISIBLE_DEVICES": "0",
                    "ROCR_VISIBLE_DEVICES": "0",
                    "AGENT_CANON_TEST_MARKER": "kept",
                    "AGENT_CANON_TEST_ENV_LOG": str(env_log),
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["llm_used"], 1)
            env_text = env_log.read_text(encoding="utf-8")
            self.assertIn("CUDA_VISIBLE_DEVICES=\n", env_text)
            self.assertIn("NVIDIA_VISIBLE_DEVICES=void", env_text)
            self.assertIn("HIP_VISIBLE_DEVICES=\n", env_text)
            self.assertIn("ROCR_VISIBLE_DEVICES=\n", env_text)
            self.assertIn("AGENT_CANON_TEST_MARKER=kept", env_text)


if __name__ == "__main__":
    unittest.main()
