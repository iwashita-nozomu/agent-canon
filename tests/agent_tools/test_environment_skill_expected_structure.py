"""Protect the canonical Dockerfile-image-full-test skill structure."""

# @dependency-start
# contract test
# responsibility Protects canonical image build and docker-run full-test acceptance.
# upstream design ../../agents/skills/environment-maintenance.md expected structure owner
# upstream design ../../agents/skills/dependency-design.md dependency placement consumer
# upstream design ../../agents/skills/environment-cleanup.md cleanup consumer
# upstream design ../../agents/skills/devcontainer-exec.md targeted execution boundary
# @dependency-end

from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE = (
    "dockerfile -> canonical image -> "
    "docker run <canonical-full-test-command> -> pass"
)


class EnvironmentSkillExpectedStructureTests(unittest.TestCase):
    """Keep environment decisions and completion evidence on one image path."""

    def read(self, relative_path: str) -> str:
        """Read and normalize one canonical skill owner."""
        return " ".join(
            (PROJECT_ROOT / relative_path)
            .read_text(encoding="utf-8")
            .lower()
            .split()
        )

    def test_environment_maintenance_starts_from_the_expected_structure(self) -> None:
        """The owner presents the image/test structure before implementation mechanisms."""
        path = PROJECT_ROOT / "agents/skills/environment-maintenance.md"
        raw = path.read_text(encoding="utf-8").lower()
        text = " ".join(raw.split())

        self.assertLess(raw.index("## expected structure"), raw.index("## operating rules"))
        self.assertIn(PIPELINE, text)
        for marker in (
            "dockerfile の canonical target",
            "標準テスト一式を完了",
            "dev container、compose、runtime pack、github actionsは同じimage",
            "起動後にenvironmentを構築しない",
        ):
            self.assertIn(marker, text, marker)

    def test_dependency_design_places_standard_dependencies_in_the_image(self) -> None:
        """Dependency design cannot start from a mounted lifecycle installer."""
        text = self.read("agents/skills/dependency-design.md")

        self.assertIn(PIPELINE, text)
        for marker in (
            "標準実行・開発・検証commandが必要とするdependency",
            "canonical dockerfile target",
            "container初回起動のinstall ownerにはしません",
            "dockerfile build時に読む declarative input",
            "canonical full test command",
        ):
            self.assertIn(marker, text, marker)

    def test_cleanup_removes_alternate_environment_construction(self) -> None:
        """Cleanup closes every alternate installer back into the image path."""
        text = self.read("agents/skills/environment-cleanup.md")

        self.assertIn(PIPELINE, text)
        for marker in (
            "feature、initialize/post-create/post-attach",
            "alternate environment constructionを削除",
            "docker run",
            "標準テスト一式",
        ):
            self.assertIn(marker, text, marker)

    def test_running_devcontainer_is_not_environment_acceptance(self) -> None:
        """An existing mutable container cannot replace clean image acceptance."""
        text = self.read("agents/skills/devcontainer-exec.md")

        for marker in (
            "既存containerの実行結果はenvironment acceptanceではなく",
            "canonical imageのbuildと`docker run`による標準テスト一式",
            "このskillの成功はrequested commandの成功だけ",
            "image constructionやrepositoryの 標準テスト一式の成功を示すものではありません",
        ):
            self.assertIn(marker, text, marker)

    def test_completion_is_observable_from_docker_run(self) -> None:
        """Owner and cleanup completion use the externally observable full test."""
        for relative_path in (
            "agents/skills/environment-maintenance.md",
            "agents/skills/environment-cleanup.md",
        ):
            text = self.read(relative_path)
            self.assertIn("canonical docker imageをbuildできる", text, relative_path)
            self.assertIn(
                "buildしたimageを`docker run`し、repositoryの標準テスト一式",
                text,
                relative_path,
            )


if __name__ == "__main__":
    unittest.main()
