"""Focused regression tests for the Codex live-projection boundary."""

# @dependency-start
# contract test
# responsibility Verifies that live projection exposes project-scoped Codex surfaces without projecting internal tools or tests.
# upstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md owns the reachability model
# upstream design ../../documents/runtime/shared-runtime-surfaces.toml owns exact live root views
# upstream implementation ../../tools/agent_tools/surface_manifest.py renders and validates projection metadata
# upstream design ../../ROOT_AGENTS.md consumes vendor-owned runtime entrypoints
# @dependency-end

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from surface_manifest import check_doc, load_manifest, render_specs  # noqa: E402


class CodexProjectionBoundaryTest(unittest.TestCase):
    """Verify direct Codex discovery paths and the bounded hook closure."""

    def manifest(self):
        return load_manifest(
            PROJECT_ROOT,
            ".",
            "documents/runtime/shared-runtime-surfaces.toml",
        )

    def test_checked_in_manifest_projects_only_required_runtime_views(self) -> None:
        manifest = self.manifest()
        by_path = {entry.path: entry for entry in manifest.entries}
        expected_sources = {
            "AGENTS.md": "ROOT_AGENTS.md",
            ".codex/config.toml": ".codex/config.toml",
            ".codex/agents": ".codex/agents",
            ".codex/hooks.json": ".codex/hooks.json",
            ".codex/hooks": ".codex/hooks",
        }

        active_symlinks = {
            entry.path for entry in manifest.entries if entry.mode == "symlink"
        }
        self.assertEqual(active_symlinks, set(expected_sources))
        for path, source in expected_sources.items():
            with self.subTest(path=path):
                self.assertEqual(by_path[path].source, source)
                self.assertFalse(by_path[path].local_override_allowed)

        removed = {
            entry.path for entry in manifest.entries if entry.mode == "removed_legacy"
        }
        self.assertIn("tools/agent-canon", removed)
        self.assertNotIn("tests", removed)
        self.assertNotIn(".codex/hooks.json", removed)
        self.assertNotIn(".codex/hooks", removed)

    def test_link_specs_match_codex_protocol_paths(self) -> None:
        specs = set(
            render_specs(
                self.manifest().entries,
                PROJECT_ROOT,
                "vendor/agent-canon",
            ).splitlines()
        )
        self.assertEqual(
            specs,
            {
                "AGENTS.md:vendor/agent-canon/ROOT_AGENTS.md",
                ".codex/config.toml:../vendor/agent-canon/.codex/config.toml",
                ".codex/agents:../vendor/agent-canon/.codex/agents",
                ".codex/hooks.json:../vendor/agent-canon/.codex/hooks.json",
                ".codex/hooks:../vendor/agent-canon/.codex/hooks",
            },
        )
        self.assertTrue(all("tools/agent-canon" not in spec for spec in specs))
        self.assertTrue(all("tests" not in spec for spec in specs))

    def test_runtime_document_and_root_entrypoint_are_aligned(self) -> None:
        manifest = self.manifest()
        self.assertEqual(check_doc(PROJECT_ROOT, ".", manifest), [])
        root_entrypoint = (PROJECT_ROOT / "ROOT_AGENTS.md").read_text(encoding="utf-8")
        self.assertNotIn("tools/agent-canon", root_entrypoint)
        self.assertIn("vendor/agent-canon/tools/agent_tools/route.py", root_entrypoint)


if __name__ == "__main__":
    unittest.main()
