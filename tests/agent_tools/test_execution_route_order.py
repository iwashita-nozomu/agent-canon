"""Run documented entrypoints with fakes; no live Docker or runtime is used."""

# @dependency-start
# contract test
# responsibility Checks that ordinary command examples execute before route diagnostics.
# upstream design ../../agents/skills/agent-canon-bootstrap.md ordinary tool command
# upstream design ../../agents/skills/devcontainer-exec.md selected container command
# @dependency-end

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ExecutionRouteOrderTest(unittest.TestCase):
    def assert_single_call(
        self, skill: str, replacements: dict[str, str], expected: list[str]
    ) -> None:
        text = (PROJECT_ROOT / "agents/skills" / skill).read_text(encoding="utf-8")
        command = text.split("```bash\n", 1)[1].split("```", 1)[0]
        for placeholder, value in replacements.items():
            command = command.replace(placeholder, value)
        for exit_code in (0, 23, 125):
            with self.subTest(skill=skill, exit_code=exit_code):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    recorder = root / "record.py"
                    recorder.write_text(
                        "import json, os, sys\n"
                        "with open(os.environ['ROUTE_TEST_CALLS'], 'a') as output:\n"
                        "    output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                        "print('command stdout')\n"
                        "print('command stderr', file=sys.stderr)\n"
                        "sys.exit(int(os.environ['ROUTE_TEST_EXIT']))\n",
                        encoding="utf-8",
                    )
                    for name in ("bootstrap.sh", "devcontainer", "id", "pwd"):
                        fake = root / name
                        fake.write_text(
                            f'#!/bin/sh\nexec {shlex.quote(sys.executable)} '
                            f'{shlex.quote(str(recorder))} {shlex.quote(name)} "$@"\n',
                            encoding="utf-8",
                        )
                        fake.chmod(0o755)
                    calls_path = root / "calls.jsonl"
                    result = subprocess.run(
                        ["bash", "-c", command],
                        cwd=root,
                        env={
                            **os.environ,
                            "PATH": f"{root}{os.pathsep}{os.defpath}",
                            "ROUTE_TEST_CALLS": str(calls_path),
                            "ROUTE_TEST_EXIT": str(exit_code),
                        },
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=False,
                    )
                    self.assertEqual(result.returncode, exit_code, result.stderr)
                    calls = [
                        json.loads(line) for line in calls_path.read_text().splitlines()
                    ]
                    self.assertEqual(calls, [expected])
                    self.assertEqual(result.stdout, "command stdout\n")
                    self.assertEqual(result.stderr, "command stderr\n")

    def test_bootstrap_dispatches_without_status_or_target_preflight(self) -> None:
        self.assert_single_call(
            "agent-canon-bootstrap.md",
            {
                "<authorized-parent-workspace>": "'/work/control space'",
                "<project-root>": "'/work/project space'",
                "<catalog-id>": "fixture-tool",
                "<args...>": "--value 'literal; echo not-a-command'",
            },
            [
                "bootstrap.sh", "--repository-root", ".", "--control-parent-root",
                "/work/control space", "tool", "run", "--root", "/work/project space",
                "fixture-tool", "--", "--value", "literal; echo not-a-command",
            ],
        )

    def test_devcontainer_preserves_the_existing_selector(self) -> None:
        for selector in ([], ["--config", "/work/config space.json"]):
            with self.subTest(selector=selector):
                self.assert_single_call(
                    "devcontainer-exec.md",
                    {
                        "<project-root>": "'/work/project space'",
                        "[--config <selector>]": shlex.join(selector),
                        "<exact-project-command>": 'printf "%s" "literal; not-a-command"',
                    },
                    [
                        "devcontainer", "exec", "--workspace-folder",
                        "/work/project space", *selector, "zsh", "-lc",
                        'printf "%s" "literal; not-a-command"',
                    ],
                )


if __name__ == "__main__":
    unittest.main()
