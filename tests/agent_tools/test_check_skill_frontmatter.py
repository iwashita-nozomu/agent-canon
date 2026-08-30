# @dependency-start
# contract test
# responsibility Tests generated runtime Skill projection readback.
# upstream implementation ../../tools/validation/semantic/skills/check_skill_frontmatter.py dispatches projection checks
# upstream implementation ../../tools/agent/skills/skill_route_catalog.py owns catalog schema admission
# upstream implementation ../../tools/agent/skills/skill_shim_materializer.py owns generated fixed-point readback
# @dependency-end
"""Tests for the generated runtime Skill compatibility entrypoint."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "validation" / "semantic" / "skills" / "check_skill_frontmatter.py"


def run_cli(root: Path) -> subprocess.CompletedProcess[str]:
    """Run the projection compatibility command against one root."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_missing_catalog_does_not_parse_runtime_markdown() -> None:
    """A root without canonical sources has no frontmatter admission boundary."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        skill = root / ".codex" / "personal" / "skills" / "broken-skill" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nname: broken_skill\n---\n", encoding="utf-8")

        result = run_cli(root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "SKILL_FRONTMATTER_CHECKED=1" in result.stdout
    assert "SKILL_FRONTMATTER=pass" in result.stdout


def test_canonical_root_delegates_schema_and_fixed_point() -> None:
    """Canonical roots are accepted only through native schema and projection owners."""
    import tools.validation.semantic.skills.check_skill_frontmatter as checker

    with patch.object(checker, "validate_catalog_schemas", return_value=()) as schemas:
        with patch.object(
            checker,
            "check_materialization",
            return_value={"content_delta_paths": []},
        ) as materializer:
            with tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                catalog = root / "agents" / "skills" / "catalog.yaml"
                dependencies = root / "agents" / "skills" / "skill-dependencies.yaml"
                catalog.parent.mkdir(parents=True)
                catalog.write_text("placeholder\n", encoding="utf-8")
                dependencies.write_text("placeholder\n", encoding="utf-8")
                skill = root / ".codex" / "personal" / "skills" / "generated" / "SKILL.md"
                skill.parent.mkdir(parents=True)
                skill.write_text("generated\n", encoding="utf-8")

                findings, checked = checker.validate_root(root)

    assert findings == []
    assert checked == 1
    schemas.assert_called_once_with(root)
    materializer.assert_called_once_with(root, all_skills=True)


def test_projection_drift_is_reported_without_frontmatter_parsing() -> None:
    """Materializer drift is surfaced as a projection finding."""
    import tools.validation.semantic.skills.check_skill_frontmatter as checker

    with patch.object(checker, "validate_catalog_schemas", return_value=()):
        with patch.object(
            checker,
            "check_materialization",
            return_value={"content_delta_paths": [".codex/personal/skills/foo/SKILL.md"]},
        ):
            with tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                (root / "agents" / "skills").mkdir(parents=True)
                (root / "agents" / "skills" / "catalog.yaml").write_text("x\n", encoding="utf-8")
                (root / "agents" / "skills" / "skill-dependencies.yaml").write_text("x\n", encoding="utf-8")
                findings, _ = checker.validate_root(root)

    assert [(item.check, item.path, item.detail) for item in findings] == [
        ("projection", ".codex/personal/skills/foo/SKILL.md", "fixed-point-drift")
    ]
