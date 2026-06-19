# @dependency-start
# contract test
# responsibility Tests AgentCanon latest command TODO routing in small focused fixtures.
# upstream design ../../tools/README.md documents the high-level AgentCanon latest route.
# upstream implementation ../../tools/update_agent_canon.sh routes pending parent-repo TODOs.
# upstream implementation ../../tools/agent_tools/agent_canon_update_todos.py defines TODO tool output.
# upstream implementation ../../tests/tools/test_update_agent_canon.py provides submodule update fixtures.
# @dependency-end

"""Focused tests for AgentCanon latest TODO routing."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests.tools.test_update_agent_canon import (
    AGENT_CANON_IS_SUBMODULE,
    SubmoduleUpdateAgentCanonTest,
)


@pytest.mark.skipif(
    not AGENT_CANON_IS_SUBMODULE,
    reason="submodule wrapper tests only apply when vendor/agent-canon is a submodule",
)
def test_latest_reports_pending_update_todos_without_failing(tmp_path: Path) -> None:
    """Pending parent-repo update TODOs route work without failing latest."""
    fixture = SubmoduleUpdateAgentCanonTest(
        methodName="test_ensure_latest_reports_already_current_submodule"
    )
    bare_repo, _work_dir = fixture.make_agent_canon_remote(tmp_path)
    repo = fixture.make_superproject(tmp_path, bare_repo)
    todo_tool = repo / "tools" / "agent_tools" / "agent_canon_update_todos.py"
    todo_tool.parent.mkdir(parents=True)
    todo_tool.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import sys",
                "if sys.argv[1:] == ['plan', '--write']:",
                "    print('AGENT_CANON_UPDATE_TODO_PENDING_COUNT=1')",
                "    print('AGENT_CANON_UPDATE_TODO_PENDING=ACUT-test')",
                "    raise SystemExit(0)",
                "if sys.argv[1:] == ['acknowledge']:",
                "    print('unexpected acknowledge')",
                "    raise SystemExit(0)",
                "raise SystemExit(1)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    todo_tool.chmod(0o755)

    latest = subprocess.run(
        ["bash", "tools/update_agent_canon.sh", "latest"],
        cwd=repo,
        env=os.environ.copy(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert latest.returncode == 0, latest.stdout + latest.stderr
    assert "AGENT_CANON_UPDATE_TODO_PENDING_COUNT=1" in latest.stdout
    assert "AGENT_CANON_LATEST_TODOS=pending" in latest.stdout
    assert "AGENT_CANON_LATEST_TOOL_RESULT=updated_with_pending_todos" in latest.stdout
    assert "NEXT_ACTION=apply_agent_canon_update_todos_then_rerun_latest" in latest.stdout
    assert "unexpected acknowledge" not in latest.stdout
