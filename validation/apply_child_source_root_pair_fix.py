#!/usr/bin/env python3
"""Keep ephemeral OS temporary state outside the parent-owned filesystem boundary."""

from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    """Replace one exact source block."""
    source = path.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    path.write_text(source.replace(old, new), encoding="utf-8")


def main() -> None:
    """Patch the child environment and its focused regression."""
    boundary = Path("tools/agent_tools/parent_root_side_effects.py")
    replace_once(
        boundary,
        '''        """Create fixed parent-local paths and transport a single-use handoff."""
        env = dict(os.environ if base_env is None else base_env)
        root = attestation.parent_root
        default_tmp = root / ".agent-canon" / "tmp"
        default_cache = root / ".agent-canon" / "cache"
''',
        '''        """Bind persistent child state to the parent and preserve OS temporary state."""
        env = dict(os.environ if base_env is None else base_env)
        root = attestation.parent_root
        default_cache = root / ".agent-canon" / "cache"
''',
        "child environment purpose",
    )
    replace_once(
        boundary,
        '''        paths = {
            "TMPDIR": parent_local_value("TMPDIR", default_tmp),
            "TEMP": parent_local_value("TEMP", default_tmp),
            "TMP": parent_local_value("TMP", default_tmp),
            "XDG_CACHE_HOME": parent_local_value("XDG_CACHE_HOME", default_cache),
''',
        '''        paths = {
            "XDG_CACHE_HOME": parent_local_value("XDG_CACHE_HOME", default_cache),
''',
        "ephemeral temporary environment exclusion",
    )

    tests = Path("tests/agent_tools/test_parent_root_side_effects.py")
    replace_once(
        tests,
        '''    original_home = os.environ.get("HOME")
    env = child_environment(receipt, {"HOME": original_home or ""})
    assert env["HOME"] == (original_home or "")
''',
        '''    original_home = os.environ.get("HOME")
    os_temp = tmp_path.parent / "os-temp"
    env = child_environment(
        receipt,
        {
            "HOME": original_home or "",
            "TMPDIR": str(os_temp),
            "TEMP": str(os_temp),
            "TMP": str(os_temp),
        },
    )
    assert env["HOME"] == (original_home or "")
    assert env["TMPDIR"] == str(os_temp)
    assert env["TEMP"] == str(os_temp)
    assert env["TMP"] == str(os_temp)
    assert not os_temp.exists()
''',
        "ephemeral temporary environment regression",
    )
    replace_once(
        tests,
        '''    for name in (
        "TMPDIR", "TEMP", "TMP", "XDG_CACHE_HOME", "PYTHONPYCACHEPREFIX",
        "AGENT_CANON_TOOLS_HOME", "CARGO_HOME", "CARGO_TARGET_DIR",
        "AGENT_CANON_CLI_TARGET_DIR",
    ):
''',
        '''    for name in (
        "XDG_CACHE_HOME", "PYTHONPYCACHEPREFIX", "AGENT_CANON_TOOLS_HOME",
        "CARGO_HOME", "CARGO_TARGET_DIR", "AGENT_CANON_CLI_TARGET_DIR",
    ):
''',
        "parent-local persistent environment regression",
    )


if __name__ == "__main__":
    main()
