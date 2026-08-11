#!/usr/bin/env python3
"""Pair AgentCanon source and canon overrides in parent-bound children."""

from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    """Replace one exact source block."""
    source = path.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    path.write_text(source.replace(old, new), encoding="utf-8")


def main() -> None:
    """Patch the canonical child environment and its focused regression."""
    boundary = Path("tools/agent_tools/parent_root_side_effects.py")
    replace_once(
        boundary,
        '''        env["AGENT_CANON_ACTIVE_REPOSITORY_ROOT"] = str(root)
        env["AGENT_CANON_PARENT_ROOT"] = str(root)
        env["AGENT_CANON_SOURCE_ROOT"] = str(attestation.source_root or root)
        env["AGENT_CANON_PARENT_ROOT_DEV"] = str(attestation.parent_dev)
''',
        '''        env["AGENT_CANON_ACTIVE_REPOSITORY_ROOT"] = str(root)
        env["AGENT_CANON_PARENT_ROOT"] = str(root)
        env["AGENT_CANON_SOURCE_ROOT"] = str(attestation.source_root or root)
        env["AGENT_CANON_ROOT"] = env["AGENT_CANON_SOURCE_ROOT"]
        env["AGENT_CANON_PARENT_ROOT_DEV"] = str(attestation.parent_dev)
''',
        "paired child source-root overrides",
    )

    tests = Path("tests/agent_tools/test_parent_root_side_effects.py")
    replace_once(
        tests,
        '''    assert env["AGENT_CANON_PARENT_ROOT"] == str(tmp_path.resolve())
    assert env["AGENT_CANON_SOURCE_ROOT"] == str(tmp_path.resolve())
    for name in (
''',
        '''    assert env["AGENT_CANON_PARENT_ROOT"] == str(tmp_path.resolve())
    assert env["AGENT_CANON_SOURCE_ROOT"] == str(tmp_path.resolve())
    assert env["AGENT_CANON_ROOT"] == env["AGENT_CANON_SOURCE_ROOT"]
    for name in (
''',
        "paired child source-root regression",
    )


if __name__ == "__main__":
    main()
