# @dependency-start
# responsibility Tests vendored third-party skill adapter validation.
# upstream implementation ../../tools/agent_tools/vendor_skill_adapters.py validates and syncs adapters
# upstream design ../../vendor/skills/README.md third-party skill vendor contract
# @dependency-end

"""Tests for third-party skill vendor adapters."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "agent_tools" / "vendor_skill_adapters.py"


def skill_text(name: str) -> str:
    """Return one valid third-party SKILL.md body."""
    return "\n".join(
        [
            "---",
            f"name: {name}",
            f"description: {name} imported from a third-party source.",
            "---",
            "",
            f"# {name}",
            "",
        ]
    )


class VendorSkillAdaptersTest(unittest.TestCase):
    """Exercise vendor skill validation through the CLI."""

    def run_cli(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the adapter command against a temporary AgentCanon root."""
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--root", str(root), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_file(self, root: Path, relative_path: str, text: str) -> None:
        """Write one UTF-8 file below root."""
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def write_manifest(self, root: Path, body: str) -> None:
        """Write a manifest body with the required version."""
        self.write_file(root, "vendor/skills/manifest.toml", "version = 1\n\n" + body)

    def write_prompt_eval_manifest(self, root: Path, expected_count: int) -> None:
        """Write a minimal prompt eval manifest for runtime skill shims."""
        self.write_file(
            root,
            "agents/evals/skill_workflow_prompt_eval.toml",
            "\n".join(
                [
                    "version = 1",
                    "",
                    "[[evals]]",
                    'id = "runtime-skill-shims"',
                    'target_glob = ".agents/skills/*/SKILL.md"',
                    f"expected_count = {expected_count}",
                    'kind = "skill"',
                    'description = "runtime skill shims"',
                    "",
                    "[[evals.checklist]]",
                    'id = "S1"',
                    "critical = true",
                    'description = "has skill name"',
                    'required_regex = ["name:"]',
                    "",
                ]
            ),
        )

    def test_empty_manifest_passes(self) -> None:
        """An empty vendor manifest is valid before any third-party import."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_manifest(root, "")

            result = self.run_cli(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("VENDOR_SKILL_ADAPTERS=pass", result.stdout)

    def test_sync_creates_runtime_adapter_symlink(self) -> None:
        """The sync command should expose enabled skills through .agents/skills."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root,
                "vendor/skills/external/example-skill/SKILL.md",
                skill_text("example-skill"),
            )
            self.write_manifest(
                root,
                "\n".join(
                    [
                        "[[skills]]",
                        'id = "example-skill"',
                        'provider = "external"',
                        'source = "vendor/skills/external/example-skill"',
                        'adapter = ".agents/skills/example-skill"',
                        "enabled = true",
                        'license = "MIT"',
                        'upstream = "https://github.com/external/example-skill"',
                        'revision = "abc123"',
                        "",
                    ]
                ),
            )

            check_result = self.run_cli(root)
            self.assertEqual(check_result.returncode, 1)
            self.assertIn("missing-adapter", check_result.stdout)

            sync_result = self.run_cli(root, "--sync")
            self.assertEqual(sync_result.returncode, 0, sync_result.stdout + sync_result.stderr)
            self.assertIn("create-symlink:.agents/skills/example-skill", sync_result.stdout)

            adapter = root / ".agents" / "skills" / "example-skill"
            self.assertTrue(adapter.is_symlink())
            self.assertEqual(
                adapter.resolve(),
                (root / "vendor" / "skills" / "external" / "example-skill").resolve(),
            )

            final_result = self.run_cli(root)
            self.assertEqual(final_result.returncode, 0, final_result.stdout + final_result.stderr)

    def test_canonical_skill_id_conflict_fails(self) -> None:
        """Vendored skills must not shadow AgentCanon canonical skill ids."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root,
                "agents/skills/catalog.yaml",
                "\n".join(
                    [
                        "version: 1",
                        "skill_families:",
                        "  - id: existing-skill",
                        "    canonical_doc: agents/skills/existing-skill.md",
                        "    shim: .agents/skills/existing-skill/SKILL.md",
                        "",
                    ]
                ),
            )
            self.write_file(
                root,
                "vendor/skills/external/existing-skill/SKILL.md",
                skill_text("existing-skill"),
            )
            self.write_manifest(
                root,
                "\n".join(
                    [
                        "[[skills]]",
                        'id = "existing-skill"',
                        'provider = "external"',
                        'source = "vendor/skills/external/existing-skill"',
                        'adapter = ".agents/skills/existing-skill"',
                        "enabled = true",
                        'license = "MIT"',
                        'upstream = "https://github.com/external/existing-skill"',
                        'revision = "abc123"',
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "--sync")

            self.assertEqual(result.returncode, 1)
            self.assertIn("conflicts-with-canonical-skill", result.stdout)

    def test_enabled_adapter_requires_prompt_eval_count_coverage(self) -> None:
        """Vendored runtime adapters should not bypass prompt eval growth checks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root,
                "vendor/skills/external/example-skill/SKILL.md",
                skill_text("example-skill"),
            )
            self.write_manifest(
                root,
                "\n".join(
                    [
                        "[[skills]]",
                        'id = "example-skill"',
                        'provider = "external"',
                        'source = "vendor/skills/external/example-skill"',
                        'adapter = ".agents/skills/example-skill"',
                        "enabled = true",
                        'license = "MIT"',
                        'upstream = "https://github.com/external/example-skill"',
                        'revision = "abc123"',
                        "",
                    ]
                ),
            )
            self.write_prompt_eval_manifest(root, expected_count=0)

            sync_result = self.run_cli(root, "--sync")
            self.assertEqual(sync_result.returncode, 1)
            self.assertIn("prompt-eval-expected-count-mismatch", sync_result.stdout)
            self.assertIn("expected=0 actual=1", sync_result.stdout)

            self.write_prompt_eval_manifest(root, expected_count=1)
            final_result = self.run_cli(root)
            self.assertEqual(final_result.returncode, 0, final_result.stdout + final_result.stderr)

    def test_github_upstream_owner_must_match_provider(self) -> None:
        """Imported GitHub skills should attach under their upstream owner."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root,
                "vendor/skills/external/example-skill/SKILL.md",
                skill_text("example-skill"),
            )
            self.write_manifest(
                root,
                "\n".join(
                    [
                        "[[skills]]",
                        'id = "example-skill"',
                        'provider = "external"',
                        'source = "vendor/skills/external/example-skill"',
                        'adapter = ".agents/skills/example-skill"',
                        "enabled = true",
                        'license = "MIT"',
                        'upstream = "https://github.com/someone-else/example-skill"',
                        'revision = "abc123"',
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "--sync")

            self.assertEqual(result.returncode, 1)
            self.assertIn("github-owner-must-match-provider:someone-else!=external", result.stdout)

    def test_source_must_stay_under_provider_skill_path(self) -> None:
        """Manifest source should not point at another vendor owner or root path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root,
                "vendor/skills/other/example-skill/SKILL.md",
                skill_text("example-skill"),
            )
            self.write_manifest(
                root,
                "\n".join(
                    [
                        "[[skills]]",
                        'id = "example-skill"',
                        'provider = "external"',
                        'source = "vendor/skills/other/example-skill"',
                        'adapter = ".agents/skills/example-skill"',
                        "enabled = true",
                        'license = "MIT"',
                        'upstream = "https://github.com/external/example-skill"',
                        'revision = "abc123"',
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "--sync")

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "source-must-match-provider-skill:vendor/skills/external/example-skill",
                result.stdout,
            )

    def test_github_ssh_upstream_can_match_provider(self) -> None:
        """Imported GitHub SSH URLs are valid when the owner matches provider."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root,
                "vendor/skills/external/example-skill/SKILL.md",
                skill_text("example-skill"),
            )
            self.write_manifest(
                root,
                "\n".join(
                    [
                        "[[skills]]",
                        'id = "example-skill"',
                        'provider = "external"',
                        'source = "vendor/skills/external/example-skill"',
                        'adapter = ".agents/skills/example-skill"',
                        "enabled = true",
                        'license = "MIT"',
                        'upstream = "git@github.com:external/example-skill.git"',
                        'revision = "abc123"',
                        "",
                    ]
                ),
            )

            sync_result = self.run_cli(root, "--sync")

            self.assertEqual(sync_result.returncode, 0, sync_result.stdout + sync_result.stderr)


if __name__ == "__main__":
    unittest.main()
