# @dependency-start
# contract test
# responsibility Verifies rebuilt AgentCanon executables and links are published by the parent boundary.
# upstream implementation ../../tools/rebuild_agent_tools.sh owns local AgentCanon CLI publication.
# @dependency-end

"""Focused source checks for parent-bounded AgentCanon tool rebuilding."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "rebuild_agent_tools.sh"


def test_rebuild_routes_executable_and_link_publication_through_boundary() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'python3 "$BOUNDARY_SCRIPT" copy' in source
    assert "--preserve-mode" in source
    assert 'python3 "$BOUNDARY_SCRIPT" replace-symlink' in source
    assert 'install -m 755 "$build_binary" "$install_binary"' not in source
    assert 'ln -sf "$install_binary"' not in source
