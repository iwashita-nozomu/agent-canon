"""Tests for the source-root-bound explicit Docstring review route."""

# @dependency-start
# contract test
# responsibility Verifies canonical pydocstyle configuration resolution for standalone and derived roots.
# upstream implementation ../../tools/agent_tools/pydocstyle_review.py owns explicit Docstring review execution.
# upstream implementation ../../tools/agent_tools/agent_canon_source_root.py owns source-root resolution.
# upstream design ../../documents/conventions/DOCSTRING_GUIDE.md owns the D213 Docstring contract.
# @dependency-end

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from tools.agent_tools.agent_canon_source_root import RootResolution
from tools.agent_tools.pydocstyle_review import (
    build_parser,
    resolve_canonical_config,
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
        (source / "tools" / "ci" / "pydocstyle.toml").write_text(
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

    assert standalone_config == (standalone / "tools/ci/pydocstyle.toml").resolve()
    assert derived_config == (derived / "tools/ci/pydocstyle.toml").resolve()
    assert not (derived_parent / "tools/ci/pydocstyle.toml").exists()


def test_run_binds_absolute_source_config(tmp_path: Path) -> None:
    """The delegated pydocstyle command receives the resolved absolute config."""
    source = tmp_path / "source"
    config = source / "tools" / "ci" / "pydocstyle.toml"
    config.parent.mkdir(parents=True)
    config.write_text("[tool.pydocstyle]\n", encoding="utf-8")
    parsed = build_parser().parse_args(["changed.py"])
    with patch("tools.agent_tools.pydocstyle_review.subprocess.run") as process:
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
    assert command[-1] == "changed.py"
