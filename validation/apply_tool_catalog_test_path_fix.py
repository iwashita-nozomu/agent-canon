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
    """Patch the extractor and add an integration regression."""
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
    anchor = "    def test_entry_summary_is_required(self) -> None:\n"
    regression = indent(
        dedent(
            '''
            def test_test_paths_are_not_default_tool_references(self) -> None:
                """Default wiring must not catalog the tools segment of test paths."""
                with tempfile.TemporaryDirectory() as tmp_dir:
                    root = Path(tmp_dir)
                    self.write_minimal_repo(root)
                    checks = root / "tools" / "ci" / "run_all_checks.sh"
                    checks.write_text(
                        checks.read_text(encoding="utf-8")
                        + "\\npython3 tests/tools/test_catalog_fixture.py\\n",
                        encoding="utf-8",
                    )
                    self.write_file(
                        root,
                        "tests/tools/test_catalog_fixture.py",
                        self.manifest("Fixture test, not a cataloged tool."),
                    )

                    result = self.run_checker(root)

                    self.assertEqual(
                        result.returncode,
                        0,
                        result.stdout + result.stderr,
                    )
                    self.assertNotIn(
                        "default_wiring:tools/test_catalog_fixture.py:",
                        result.stdout,
                    )

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
