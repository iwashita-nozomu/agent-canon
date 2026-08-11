#!/usr/bin/env python3
"""Apply the focused tool-catalog false-positive fix for PR #660."""

from pathlib import Path
from textwrap import dedent, indent


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    """Replace one exact source block or stop without partial publication."""
    source = path.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    path.write_text(source.replace(old, new), encoding="utf-8")


def main() -> None:
    """Patch root-tool extraction and add a direct regex regression."""
    checker = Path("tools/agent_tools/tool_catalog.py")
    replace_once(
        checker,
        'TOOL_REFERENCE_RE = re.compile(r"\\btools/[A-Za-z0-9_./-]+\\.(?:py|sh)\\b")\n',
        'TOOL_REFERENCE_RE = re.compile(\n'
        '    r"(?<!tests/)\\btools/[A-Za-z0-9_./-]+\\.(?:py|sh)\\b"\n'
        ')\n',
        "root tool reference extraction",
    )

    tests = Path("tests/agent_tools/test_tool_catalog.py")
    replace_once(
        tests,
        "import subprocess\nimport sys\n",
        "import runpy\nimport subprocess\nimport sys\n",
        "tool catalog runpy import",
    )
    anchor = "    def test_entry_summary_is_required(self) -> None:\n"
    regression = indent(
        dedent(
            '''
            def test_test_paths_are_not_default_tool_references(self) -> None:
                """Test paths are not mistaken for root tool references."""
                sys.path.insert(0, str(CHECKER.parent))
                try:
                    namespace = runpy.run_path(str(CHECKER))
                finally:
                    sys.path.pop(0)
                pattern = namespace["TOOL_REFERENCE_RE"]
                matches = set(
                    pattern.findall(
                        "python3 tests/tools/test_catalog_fixture.py\\n"
                        "python3 tools/agent_tools/uncataloged.py\\n"
                    )
                )

                self.assertNotIn("tools/test_catalog_fixture.py", matches)
                self.assertIn("tools/agent_tools/uncataloged.py", matches)

            '''
        ).lstrip("\n"),
        "    ",
    )
    source = tests.read_text(encoding="utf-8")
    if source.count(anchor) != 1:
        raise SystemExit("tool catalog regression anchor changed")
    tests.write_text(source.replace(anchor, regression + anchor), encoding="utf-8")


if __name__ == "__main__":
    main()
