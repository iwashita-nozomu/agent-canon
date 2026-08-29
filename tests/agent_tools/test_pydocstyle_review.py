"""Tests for the source-root-bound explicit Docstring review route."""

# @dependency-start
# contract test
# responsibility Verifies canonical pydocstyle configuration resolution for standalone and derived roots.
# upstream implementation ../../tools/validation/semantic/code/pydocstyle_review.py owns explicit Docstring review execution.
# upstream implementation ../../tools/runtime/source/agent_canon_source_root.py owns source-root resolution.
# upstream design ../../documents/conventions/DOCSTRING_GUIDE.md owns the D213 Docstring contract.
# @dependency-end

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from tools.runtime.source.agent_canon_source_root import RootResolution, SourceRootFailure
from tools.validation.semantic.code.pydocstyle_review import (
    build_parser,
    resolve_canonical_config,
    resolve_target,
    run,
)


def _resolution(current: Path, source: Path, layout: str) -> RootResolution:
    return RootResolution(
        current_repository_root=current,
        source_root=source,
        layout=layout,
        canon_root=source,
    )


def test_standalone_and_derived_roots_resolve_source_config(tmp_path: Path) -> None:
    """Both layouts resolve the config from the AgentCanon source root only."""
    standalone = tmp_path / "standalone"
    derived_parent = tmp_path / "derived-parent"
    derived = derived_parent / "vendor" / "agent-canon"
    for source in (standalone, derived):
        (source / "tools" / "ci").mkdir(parents=True)
        (source / "tools" / "validation" / "ci" / "config" / "pydocstyle.toml").write_text(
            '[tool.pydocstyle]\nadd-select = "D213"\n',
            encoding="utf-8",
        )

    standalone_config = resolve_canonical_config(
        standalone,
        resolver=lambda _: _resolution(standalone, standalone, "standalone"),
    )
    derived_config = resolve_canonical_config(
        derived_parent,
        resolver=lambda _: _resolution(derived_parent, derived, "vendored"),
    )

    assert standalone_config == (standalone / "tools/validation/ci/config/pydocstyle.toml").resolve()
    assert derived_config == (derived / "tools/validation/ci/config/pydocstyle.toml").resolve()
    assert not (derived_parent / "tools/validation/ci/config/pydocstyle.toml").exists()


def test_run_binds_absolute_source_config(tmp_path: Path) -> None:
    """The delegated pydocstyle command receives the resolved absolute config."""
    source = tmp_path / "source"
    config = source / "tools" / "validation" / "ci" / "config" / "pydocstyle.toml"
    config.parent.mkdir(parents=True)
    config.write_text("[tool.pydocstyle]\n", encoding="utf-8")
    target = tmp_path / "changed.py"
    target.write_text("# target\n", encoding="utf-8")
    parsed = build_parser().parse_args(["--target", "changed.py"])
    with patch("tools.validation.semantic.code.pydocstyle_review.subprocess.run") as process:
        process.return_value.returncode = 0
        assert (
            run(
                parsed,
                raw_root=tmp_path,
                resolver=lambda _: _resolution(tmp_path, source, "vendored"),
            )
            == 0
        )

    command = process.call_args.args[0]
    assert f"--config={config.resolve()}" in command
    assert command[command.index(f"--config={config.resolve()}") + 1] == "--"
    assert command[-1] == str(target.resolve())


def test_target_boundaries_reject_escape_injection_symlink_and_wrong_type(
    tmp_path: Path,
) -> None:
    """Target validation rejects every path outside the single regular .py contract."""
    root = tmp_path / "repo"
    source = root / "vendor" / "agent-canon"
    (source / "tools" / "ci").mkdir(parents=True)
    (source / "tools" / "validation" / "ci" / "config" / "pydocstyle.toml").write_text(
        "[tool.pydocstyle]\n", encoding="utf-8"
    )
    (root / "valid.py").write_text("# valid\n", encoding="utf-8")
    (root / "directory.py").mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("# outside\n", encoding="utf-8")
    (root / "escape.py").symlink_to(outside)

    def resolver(_: Path) -> RootResolution:
        return _resolution(root, source, "vendored")

    invalid_targets = (
        str((root / "valid.py").resolve()),
        "../outside.py",
        "--config=override.toml",
        "valid.txt",
        "directory.py",
        "missing.py",
        "escape.py",
    )
    for invalid in invalid_targets:
        with pytest.raises(SourceRootFailure):
            resolve_target(root, invalid, resolver=resolver)


def test_parser_rejects_config_override_and_multiple_targets() -> None:
    """The public parser owns one target and never accepts a config override."""
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--config=override.toml", "--target", "valid.py"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--target", "one.py", "--target", "two.py"])


def test_missing_tool_and_diagnostic_exit_codes_are_preserved(tmp_path: Path) -> None:
    """Explicit review failures remain nonzero without affecting the shared gate."""
    source = tmp_path / "source"
    config = source / "tools" / "validation" / "ci" / "config" / "pydocstyle.toml"
    config.parent.mkdir(parents=True)
    config.write_text("[tool.pydocstyle]\n", encoding="utf-8")
    (tmp_path / "target.py").write_text("# target\n", encoding="utf-8")
    parsed = build_parser().parse_args(["--target", "target.py"])

    def resolver(_: Path) -> RootResolution:
        return _resolution(tmp_path, source, "vendored")

    for returncode in (127, 1):
        with patch("tools.validation.semantic.code.pydocstyle_review.subprocess.run") as process:
            process.return_value.returncode = returncode
            assert run(parsed, raw_root=tmp_path, resolver=resolver) == returncode
