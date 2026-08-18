#!/usr/bin/env python3
"""Normalize the one-time Issue #766 patch against the asserted main snapshot."""

from __future__ import annotations

import ast
import base64
import gzip
from pathlib import Path

WRAPPER = Path(__file__).with_name("apply_issue_766.py")


def replace_once(source: str, old: str, new: str, label: str) -> str:
    """Replace exactly one asserted transport fragment."""
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{label} drifted: expected one match, found {count}")
    return source.replace(old, new, 1)


def main() -> None:
    """Rewrite the compressed patch source without weakening repository gates."""
    lines = WRAPPER.read_text(encoding="utf-8").splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith("_PATCH = "))
    payload = ast.literal_eval(lines[index].split("=", 1)[1].strip())
    source = gzip.decompress(base64.b64decode(payload)).decode("utf-8")

    source = replace_once(
        source,
        """replace_once(
    RUNNER,
    '''            \"result_dir\": str(context.paths.result_dir),\\n            \"log_dir\": str(context.paths.log_dir),\\n''',
    '''            \"result_dir\": str(context.paths.result_dir),\\n            \"raw_dir\": str(context.paths.raw_dir),\\n            \"log_dir\": str(context.paths.log_dir),\\n''',
)""",
        """runner_text = read(RUNNER)
runner_old = '''            \"result_dir\": str(context.paths.result_dir),\\n            \"log_dir\": str(context.paths.log_dir),\\n'''
runner_new = '''            \"result_dir\": str(context.paths.result_dir),\\n            \"raw_dir\": str(context.paths.raw_dir),\\n            \"log_dir\": str(context.paths.log_dir),\\n'''
runner_count = runner_text.count(runner_old)
if runner_count != 2:
    raise RuntimeError(
        f\"{RUNNER}: expected two canonical path payloads, found {runner_count}\"
    )
write(RUNNER, runner_text.replace(runner_old, runner_new))""",
        "runner raw-path payload assertion",
    )
    source = replace_once(
        source,
        """replace_all_in_paths(
    CONSUMERS,
    \"experiments/<topic>/result/<variant>/<run-id>.tar.gz\",
    \"experiments/<topic>/raw/<variant>/<run-id>.tar.gz\",
)
""",
        "",
        "absent legacy run-id archive spelling",
    )

    encoded = base64.b64encode(gzip.compress(source.encode("utf-8"), mtime=0)).decode()
    lines[index] = f"_PATCH = {encoded!r}"
    WRAPPER.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
