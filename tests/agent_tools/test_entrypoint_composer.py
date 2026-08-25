# @dependency-start
# contract test
# responsibility Verifies deterministic consumer-root AGENTS.md composition and fail-closed collisions.
# upstream design ../../documents/design/entrypoint-owner-map.md consumer root composition contract
# upstream implementation ../../tools/agent_tools/entrypoint_composer.py composer under test
# upstream design ../../ROOT_AGENTS.md common consumer base
# @dependency-end
"""Focused tests for the consumer root instruction composer."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.agent_tools import entrypoint_composer as composer


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class EntrypointComposerTest(unittest.TestCase):
    """Exercise creation, deterministic refresh, and collision rejection."""

    def _inputs(self, root: Path) -> tuple[Path, Path, Path]:
        base = root / "ROOT_AGENTS.md"
        specific = root / "documents" / "agent-canon" / "consumer-root-instructions.md"
        output = root / "AGENTS.md"
        base.write_bytes(b"# AgentCanon Consumer Instructions\n\ncommon\n")
        specific.parent.mkdir(parents=True)
        specific.write_bytes(b"## Consumer Repository\n\nproject-owned\n")
        return base, specific, output

    def test_composes_regular_file_and_preserves_source_agents(self) -> None:
        """The source AGENTS.md remains untouched and output is self-contained."""
        source_agents = (REPOSITORY_ROOT / "AGENTS.md").read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            base, specific, output = self._inputs(Path(temporary))
            status, first = composer.compose(
                base_path=base,
                specific_path=specific,
                output_path=output,
                source_root=REPOSITORY_ROOT,
            )
            self.assertEqual(status, "created")
            self.assertTrue(output.is_file())
            self.assertFalse(output.is_symlink())
            self.assertFalse((output.parent / "AGENT.md").exists())
            self.assertEqual((REPOSITORY_ROOT / "AGENTS.md").read_bytes(), source_agents)
            parsed = composer._parse_marked(output.read_bytes())
            self.assertEqual(parsed.base, base.read_bytes())
            self.assertEqual(parsed.specific, specific.read_bytes())
            self.assertEqual(parsed.source_commit, first.source_commit)
            self.assertEqual(output.read_bytes(), first.render())

            second_status, second = composer.compose(
                base_path=base,
                specific_path=specific,
                output_path=output,
                source_root=REPOSITORY_ROOT,
            )
            self.assertEqual(second_status, "updated")
            self.assertEqual(first.render(), second.render())

    def test_marked_output_refreshes_from_current_exact_sources(self) -> None:
        """A valid managed file may be refreshed when either input becomes stale."""
        with tempfile.TemporaryDirectory() as temporary:
            base, specific, output = self._inputs(Path(temporary))
            composer.compose(
                base_path=base,
                specific_path=specific,
                output_path=output,
                source_root=REPOSITORY_ROOT,
            )
            base.write_bytes(base.read_bytes() + b"new common\n")
            specific.write_bytes(specific.read_bytes() + b"new consumer\n")
            status, refreshed = composer.compose(
                base_path=base,
                specific_path=specific,
                output_path=output,
                source_root=REPOSITORY_ROOT,
            )
            self.assertEqual(status, "updated")
            parsed = composer._parse_marked(output.read_bytes())
            self.assertEqual(parsed.base, refreshed.base)
            self.assertEqual(parsed.specific, refreshed.specific)

    def test_unmarked_output_is_a_preserved_collision(self) -> None:
        """A consumer-owned unmarked AGENTS.md is never overwritten."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, specific, output = self._inputs(root)
            output.write_bytes(b"# consumer-owned instructions\n")
            with self.assertRaises(composer.ComposeError) as raised:
                composer.compose(
                    base_path=base,
                    specific_path=specific,
                    output_path=output,
                    source_root=REPOSITORY_ROOT,
                )
            self.assertEqual(raised.exception.code, "collision")
            self.assertEqual(output.read_bytes(), b"# consumer-owned instructions\n")

    def test_partial_marked_output_and_symlinks_fail_typed(self) -> None:
        """Partial managed output and every input/output symlink fail closed."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, specific, output = self._inputs(root)
            output.write_bytes(composer.MANAGED_MARKER)
            with self.assertRaises(composer.ComposeError) as raised:
                composer.compose(
                    base_path=base,
                    specific_path=specific,
                    output_path=output,
                    source_root=REPOSITORY_ROOT,
                )
            self.assertEqual(raised.exception.code, "partial")

            output.unlink()
            symlink = root / "base-link.md"
            symlink.symlink_to(base)
            with self.assertRaises(composer.ComposeError) as raised:
                composer.compose(
                    base_path=symlink,
                    specific_path=specific,
                    output_path=output,
                    source_root=REPOSITORY_ROOT,
                )
            self.assertEqual(raised.exception.code, "symlink")

            symlink.unlink()
            symlink.symlink_to(specific)
            with self.assertRaises(composer.ComposeError) as raised:
                composer.compose(
                    base_path=base,
                    specific_path=symlink,
                    output_path=output,
                    source_root=REPOSITORY_ROOT,
                )
            self.assertEqual(raised.exception.code, "symlink")


if __name__ == "__main__":
    unittest.main()
