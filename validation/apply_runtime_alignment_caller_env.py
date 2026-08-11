#!/usr/bin/env python3
"""Bind runtime-alignment callers to their authenticated repository root."""

from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    """Replace one exact source block."""
    source = path.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    path.write_text(source.replace(old, new), encoding="utf-8")


def main() -> None:
    """Patch the canonical PR caller and its direct execution fixture."""
    pr_gate = Path("tools/ci/check_agent_canon_pr.sh")
    replace_once(
        pr_gate,
        'cd "${WORKSPACE_ROOT}"\nif [[ "${AGENT_CANON_CHILD_PURPOSE:-}" == "agent-canon-pr-script" ]]; then\n',
        'cd "${WORKSPACE_ROOT}"\n'
        'export AGENT_CANON_PARENT_ROOT="${WORKSPACE_ROOT}"\n'
        'export AGENT_CANON_ACTIVE_REPOSITORY_ROOT="${WORKSPACE_ROOT}"\n'
        'if [[ "${AGENT_CANON_CHILD_PURPOSE:-}" == "agent-canon-pr-script" ]]; then\n',
        "PR gate parent environment",
    )

    tests = Path("tests/agent_tools/test_check_agent_runtime_alignment.py")
    replace_once(
        tests,
        "import subprocess\nimport sys\n",
        "import os\nimport subprocess\nimport sys\n",
        "runtime alignment os import",
    )
    replace_once(
        tests,
        '''        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
''',
        '''        environment = os.environ.copy()
        environment["AGENT_CANON_PARENT_ROOT"] = str(PROJECT_ROOT)
        environment["AGENT_CANON_ACTIVE_REPOSITORY_ROOT"] = str(PROJECT_ROOT)
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
''',
        "runtime alignment subprocess environment",
    )


if __name__ == "__main__":
    main()
