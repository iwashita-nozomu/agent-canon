"""Canonical source docs must not be confused with generated runtime directories."""

# @dependency-start
# contract test
# responsibility Verifies literal-directory exclusions in the native link checker.
# upstream implementation ../../tools/validation/documentation/config/lychee.toml configured source selection
# @dependency-end

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "tools/validation/documentation/config/lychee.toml"


def _native_cli() -> str:
    selected_cli = os.environ.get("AGENT_CANON_CLI")
    if not selected_cli:
        raise RuntimeError("AGENT_CANON_CLI must select the current native executable")
    return selected_cli


def _prepare_docs_root(tmp_path: Path) -> Path:
    root = tmp_path / "consumer repository with spaces"
    root.mkdir()
    return root


def _prepare_source_docs_root(tmp_path: Path) -> Path:
    root = _prepare_docs_root(tmp_path)
    shutil.copyfile(
        ROOT / ".markdownlint-cli2.jsonc", root / ".markdownlint-cli2.jsonc"
    )
    target_config = root / "tools/validation/documentation/config/lychee.toml"
    target_config.parent.mkdir(parents=True)
    shutil.copyfile(CONFIG, target_config)
    return root


def _run_docs_check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_native_cli(), "docs", "check", "--root", str(root), "README.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "relative,checked",
    [
        ("documents/runtime/source.md", True),
        ("documents/targeting.md", True),
        (".runtime/generated.md", False),
    ],
)
def test_native_link_filter_selects_directory_components(tmp_path, relative, checked):
    source = tmp_path / relative
    source.parent.mkdir(parents=True)
    source.write_text("# Fixture\n\n[Missing](missing.md)\n", encoding="utf-8")
    actual = subprocess.run(
        ["lychee", "--config", str(CONFIG), "--hidden", "--no-ignore", "./" + relative],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (actual.returncode != 0) is checked, actual.stdout + actual.stderr
    if checked:
        assert "missing.md" in actual.stdout + actual.stderr


def test_native_docs_check_uses_embedded_defaults_for_fresh_readme(
    tmp_path: Path,
) -> None:
    root = _prepare_docs_root(tmp_path)
    (root / "README.md").write_text(
        "# Fresh project\n\nA short project description.\n", encoding="utf-8"
    )

    result = _run_docs_check(root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert not (root / ".markdownlint-cli2.jsonc").exists()
    assert not (root / "tools/validation/documentation/config/lychee.toml").exists()


def test_native_docs_check_keeps_quarto_cache_outside_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _prepare_docs_root(tmp_path)
    (root / "README.md").write_text(
        "# Fresh project\n\nA short project description.\n", encoding="utf-8"
    )
    home = tmp_path / "unused-home"
    home.mkdir()
    temporary = tmp_path / "provider-temporary"
    temporary.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("TMPDIR", str(temporary))
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)

    result = _run_docs_check(root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert not (home / ".cache" / "quarto").exists()
    assert not list(temporary.glob("agent-canon-docs-pandoc-cache-*"))


def test_native_docs_check_detects_broken_readme_link_without_project_configs(
    tmp_path: Path,
) -> None:
    root = _prepare_docs_root(tmp_path)
    (root / "README.md").write_text(
        "# Fresh project\n\n[Missing](missing.md)\n", encoding="utf-8"
    )

    result = _run_docs_check(root)

    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "missing.md" in output
    assert not (root / ".markdownlint-cli2.jsonc").exists()
    assert not (root / "tools/validation/documentation/config/lychee.toml").exists()


@pytest.mark.parametrize(
    ("relative", "contents"),
    [
        (".markdownlint-cli2.jsonc", '{"config": ['),
        ("tools/validation/documentation/config/lychee.toml", "offline = ["),
    ],
)
def test_native_docs_check_preserves_existing_invalid_project_config(
    tmp_path: Path, relative: str, contents: str
) -> None:
    root = _prepare_docs_root(tmp_path)
    (root / "README.md").write_text(
        "# Config precedence\n\nA valid Markdown document.\n", encoding="utf-8"
    )
    config = root / relative
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(contents, encoding="utf-8")
    before = config.read_bytes()

    result = _run_docs_check(root)

    assert result.returncode != 0, result.stdout + result.stderr
    assert config.read_bytes() == before
    if relative != ".markdownlint-cli2.jsonc":
        assert not (root / ".markdownlint-cli2.jsonc").exists()
    if relative != "tools/validation/documentation/config/lychee.toml":
        assert not (root / "tools/validation/documentation/config/lychee.toml").exists()


@pytest.mark.parametrize("profile", ["_template", "_cpp_template"])
def test_native_docs_check_uses_consumer_relative_template_context(
    tmp_path: Path, profile: str
) -> None:
    root = _prepare_source_docs_root(tmp_path)
    (root / "documents").mkdir()
    (root / "documents" / "projectdoc.md").write_text(
        "# Project documentation\n", encoding="utf-8"
    )
    (root / "documents" / "ordinary-target.md").write_text(
        "# Ordinary target\n", encoding="utf-8"
    )
    (root / "documents" / "ordinary.md").write_text(
        "# Ordinary document\n\n[Target](ordinary-target.md)\n", encoding="utf-8"
    )
    template_dir = root / "templates" / "experiments" / profile
    template_dir.mkdir(parents=True)
    (template_dir / "run.py").write_text("pass\n", encoding="utf-8")
    (template_dir / "README.md").write_text(
        "# Template\n\n"
        "[Project documentation](../../documents/projectdoc.md)\n\n"
        "[Same package](./run.py)\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            _native_cli(),
            "docs",
            "check",
            "--root",
            str(root),
            f"templates/experiments/{profile}/README.md",
            "documents/ordinary.md",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_native_docs_check_still_fails_for_missing_template_link(
    tmp_path: Path,
) -> None:
    root = _prepare_source_docs_root(tmp_path)
    template_dir = root / "templates" / "experiments" / "_template"
    template_dir.mkdir(parents=True)
    (template_dir / "run.py").write_text("pass\n", encoding="utf-8")
    (template_dir / "README.md").write_text(
        "# Template\n\n[Missing](../../documents/missing-projectdoc.md)\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            _native_cli(),
            "docs",
            "check",
            "--root",
            str(root),
            "templates/experiments/_template/README.md",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "missing-projectdoc.md" in output
