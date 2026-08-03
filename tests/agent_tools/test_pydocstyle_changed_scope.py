"""Tests for the trusted changed-production pydocstyle gate."""

# @dependency-start
# contract test
# responsibility Verifies changed-path selection and line-independent pydocstyle partitioning.
# upstream implementation ../../tools/agent_tools/pydocstyle_changed_scope.py canonical changed-scope owner
# upstream implementation ../../tools/ci/run_python_quality_checks.sh shared Python quality runner
# upstream design ../../documents/conventions/DOCSTRING_GUIDE.md Docstring gate contract
# @dependency-end

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCANNER = PROJECT_ROOT / "tools" / "agent_tools" / "pydocstyle_changed_scope.py"
CANONICAL_CONFIG = PROJECT_ROOT / "tools" / "ci" / "pydocstyle.toml"


class PydocstyleChangedScopeTest(unittest.TestCase):
    """Exercise the PR-owned production Python Docstring boundary."""

    def setUp(self) -> None:
        """Create an isolated Git fixture."""
        self.temp_root = Path(tempfile.mkdtemp(prefix="pydocstyle-scope-"))
        self.addCleanup(shutil.rmtree, self.temp_root)
        self.run_cmd("git", "init", "-b", "main")
        self.run_cmd("git", "config", "user.email", "fixture@example.invalid")
        self.run_cmd("git", "config", "user.name", "Pydocstyle Fixture")
        (self.temp_root / "tools" / "ci").mkdir(parents=True)
        shutil.copyfile(
            CANONICAL_CONFIG, self.temp_root / "tools" / "ci" / "pydocstyle.toml"
        )

    def run_cmd(
        self, *args: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        """Run one fixture command."""
        result = subprocess.run(
            list(args),
            cwd=self.temp_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)
        return result

    def write(self, relative: str, text: str) -> None:
        """Write one fixture source file."""
        path = self.temp_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, message: str) -> str:
        """Commit the current fixture tree and return its SHA."""
        self.run_cmd("git", "add", ".")
        self.run_cmd("git", "commit", "-m", message)
        return self.run_cmd("git", "rev-parse", "HEAD").stdout.strip()

    def packet(self, base_sha: str) -> tuple[Path, str]:
        """Materialize the exact selector packet for the current head."""
        head_sha = self.run_cmd("git", "rev-parse", "HEAD").stdout.strip()
        paths = self.run_cmd(
            "git", "diff", "--name-only", f"{base_sha}...{head_sha}"
        ).stdout.splitlines()
        payload = {
            "schema": "agent-canon.pr-changed-paths.v1",
            "root": str(self.temp_root.resolve()),
            "base_sha": base_sha,
            "base_source": "fixture",
            "base_tree": self.run_cmd(
                "git", "rev-parse", f"{base_sha}^{{tree}}"
            ).stdout.strip(),
            "head_sha": head_sha,
            "head_tree": self.run_cmd(
                "git", "rev-parse", f"{head_sha}^{{tree}}"
            ).stdout.strip(),
            "merge_base": self.run_cmd(
                "git", "merge-base", base_sha, head_sha
            ).stdout.strip(),
            "changed_paths": paths,
            "changed_paths_sha256": hashlib.sha256(
                "\0".join(paths).encode()
            ).hexdigest(),
        }
        packet = self.temp_root / "changed-paths.json"
        packet.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        return packet, head_sha

    def scan(
        self, packet: Path, base_sha: str, *, trusted_base: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run the production scanner against the fixture packet."""
        return subprocess.run(
            [
                sys.executable,
                str(SCANNER),
                "--root",
                str(self.temp_root),
                "--changed-path-packet",
                str(packet),
                "--trusted-base-sha",
                trusted_base or base_sha,
            ],
            cwd=self.temp_root,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_unchanged_existing_violation_is_baseline_evidence(self) -> None:
        """An unchanged repo-wide violation is not entered into the changed scan."""
        self.write(
            "unchanged.py",
            'def old():\n    """Summary.\n\n    Detail.\n    """\n    pass\n',
        )
        self.write(
            "changed.py",
            '"""Changed module."""\n\n\ndef changed():\n    """Stable summary."""\n    pass\n',
        )
        base = self.commit("base")
        self.write(
            "changed.py",
            '"""Changed module."""\n\n\n\n\ndef changed():\n    """Stable summary."""\n    pass\n',
        )
        self.commit("shift unchanged-clean function")
        packet, _ = self.packet(base)
        result = self.scan(packet, base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PYDOCSTYLE_CHANGED_SCOPE_SELECTED=1", result.stdout)
        self.assertIn("PYDOCSTYLE_CHANGED_SCOPE=pass", result.stdout)
        self.assertNotIn("unchanged.py", result.stdout)

    def test_changed_production_new_diagnostic_blocks(self) -> None:
        """A new D213 in a changed production symbol blocks."""
        self.write(
            "changed.py",
            '"""Changed module."""\n\n\ndef changed():\n    """\n    Summary.\n    """\n    pass\n',
        )
        base = self.commit("base")
        self.write(
            "changed.py",
            '"""Changed module."""\n\n\ndef changed():\n    """Summary.\n\n    Detail.\n    """\n    pass\n',
        )
        self.commit("introduce D213")
        packet, _ = self.packet(base)
        result = self.scan(packet, base)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("D213", result.stdout)
        self.assertIn("changed_production_diagnostic", result.stdout)

    def test_same_diagnostic_and_line_shift_are_baseline(self) -> None:
        """The same code and qualified symbol survives line movement."""
        source = '"""Changed module."""\n\n\ndef changed():\n    """Summary.\n\n    Detail.\n    """\n    pass\n'
        self.write("changed.py", source)
        base = self.commit("base")
        self.write("changed.py", "\n\n" + source)
        self.commit("shift D213")
        packet, _ = self.packet(base)
        result = self.scan(packet, base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PYDOCSTYLE_CHANGED_SCOPE_BASELINE=1", result.stdout)
        self.assertIn("PYDOCSTYLE_CHANGED_SCOPE_BLOCKING=0", result.stdout)

    def test_tests_fixtures_generated_and_deleted_paths_are_skipped(self) -> None:
        """Non-production and deleted Python files delegate to their owners."""
        self.write(
            "tests/test_bad.py",
            'def bad():\n    """Summary.\n\n    Detail.\n    """\n    pass\n',
        )
        self.write(
            "fixtures/bad.py",
            'def bad():\n    """Summary.\n\n    Detail.\n    """\n    pass\n',
        )
        self.write(
            "generated/bad.py",
            'def bad():\n    """Summary.\n\n    Detail.\n    """\n    pass\n',
        )
        self.write(
            "deleted.py",
            'def bad():\n    """Summary.\n\n    Detail.\n    """\n    pass\n',
        )
        base = self.commit("base")
        self.write(
            "tests/test_bad.py",
            'def bad():\n    """Summary.\n\n    Detail.\n    """\n    pass\n\n# changed\n',
        )
        self.write(
            "fixtures/bad.py",
            'def bad():\n    """Summary.\n\n    Detail.\n    """\n    pass\n\n# changed\n',
        )
        self.write(
            "generated/bad.py",
            'def bad():\n    """Summary.\n\n    Detail.\n    """\n    pass\n\n# changed\n',
        )
        (self.temp_root / "deleted.py").unlink()
        self.commit("change delegated paths")
        packet, _ = self.packet(base)
        result = self.scan(packet, base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PYDOCSTYLE_CHANGED_SCOPE_SELECTED=0", result.stdout)

    def test_wrong_trusted_base_fails_closed(self) -> None:
        """A caller-substituted trusted base cannot authorize the packet."""
        self.write("changed.py", '"""Changed module."""\n')
        base = self.commit("base")
        self.write("changed.py", '"""Changed module."""\n\n# changed\n')
        self.commit("change")
        packet, _ = self.packet(base)
        result = self.scan(packet, base, trusted_base="0" * 40)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("changed_path_packet_trusted_base_mismatch", result.stdout)

    def test_canonical_convention_selects_d213_without_d212(self) -> None:
        """The canonical config makes the conflicting pair mutually exclusive."""
        text = CANONICAL_CONFIG.read_text(encoding="utf-8")
        self.assertIn('add-select = "D213"', text)
        self.assertIn('add-ignore = "D212"', text)
        self.assertNotIn('add-select = "D212,D213"', text)


if __name__ == "__main__":
    unittest.main()
