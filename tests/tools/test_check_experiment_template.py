# @dependency-start
# contract test
# responsibility Tests centralized experiment template generation and smoke validation.
# upstream implementation ../../tools/experiments/create_experiment_topic.py canonical topic materialization route
# upstream design ../../tools/ci/check_experiment_template.py temporary parent-shaped validation route
# downstream implementation ../../templates/experiments/_template/run.py experiment scaffold source
# @dependency-end

"""一時的な parent-shaped experiment template validation を検証します."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CREATE_TOPIC = PROJECT_ROOT / "tools" / "experiments" / "create_experiment_topic.py"
CHECKER = PROJECT_ROOT / "tools" / "ci" / "check_experiment_template.py"


def test_created_topic_readme_keeps_research_acceptance_topic_owned(
    tmp_path: Path,
) -> None:
    """creator が一律の研究受入条件を topic README へ再生成しないことを検証します."""
    parent_root = tmp_path / "parent"
    registry_path = parent_root / "experiments" / "registry.toml"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        "\n".join(
            (
                "schema_version = 1",
                "topics = []",
                "",
                "[defaults]",
                'topic_template_dir = "templates/experiments/_template"',
                "",
            )
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(CREATE_TOPIC),
            "--repo-root",
            str(parent_root),
            "--status",
            "template",
            "acceptance-boundary",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    readme = (
        parent_root / "experiments" / "acceptance-boundary" / "README.md"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "受入条件",
        "## 完了条件",
        "completion gate",
        "non-empty observation",
    ):
        assert forbidden not in readme
    for required in (
        "## 評価と lifecycle の境界",
        "topic / research owner",
        "run identity",
        "result/<run-id>/",
        "terminal / failure state",
        "failure evidence",
        "provenance / readback",
    ):
        assert required in readme


def test_centralized_experiment_template_smoke_copies_and_runs() -> None:
    """生成した topic を smoke checker が作成、実行、削除することを検証します."""
    temp_root = PROJECT_ROOT / ".agent-canon" / "tmp"
    before: set[Path] = set(temp_root.iterdir()) if temp_root.is_dir() else set()
    result = subprocess.run(
        [sys.executable, str(CHECKER)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "EXPERIMENT_TEMPLATE_SMOKE=pass" in result.stdout
    assert "EXPERIMENT_TEMPLATE_TOPIC=experiments/template-smoke" in result.stdout
    assert "EXPERIMENT_TEMPLATE_EXECUTION=pass" in result.stdout
    assert not (PROJECT_ROOT / "experiments" / "template-smoke").exists()
    after: set[Path] = set(temp_root.iterdir()) if temp_root.is_dir() else set()
    assert after == before
