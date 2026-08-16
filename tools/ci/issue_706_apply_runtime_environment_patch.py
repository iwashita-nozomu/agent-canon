#!/usr/bin/env python3
"""Apply the one-time Issue #706 runtime environment projection correction."""

from __future__ import annotations

from pathlib import Path

PATH = Path("tools/agent_tools/check_agent_runtime_alignment.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    """Replace one exact source fragment or fail without partial output."""
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    """Add one exact, reversible process-environment projection boundary."""
    text = PATH.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from collections.abc import Collection\n",
        "from collections.abc import Collection, Iterator, Mapping\n",
        "collections imports",
    )
    helper = '''

@contextmanager
def _project_process_environment(
    environment: Mapping[str, str],
) -> Iterator[None]:
    """Replace the process environment for one fixture-owned operation.

    ``bootstrap_fixture_public_environment`` deliberately returns a value and
    restores its own caller environment before yielding.  Runtime alignment
    therefore projects that value only across the derived-bundle operation,
    then restores the complete prior mapping even when the operation fails.
    """
    previous = os.environ.copy()
    primary_error: BaseException | None = None
    try:
        os.environ.clear()
        os.environ.update(environment)
        yield
    except BaseException as error:
        primary_error = error
        raise
    finally:
        try:
            os.environ.clear()
            os.environ.update(previous)
        except BaseException as restoration_error:
            if primary_error is not None:
                primary_error.add_note(
                    "runtime-alignment environment restoration failed: "
                    f"{restoration_error}"
                )
            else:
                raise
'''
    anchor = "\n\n@contextmanager\ndef runtime_alignment_parent("
    text = replace_once(
        text,
        anchor,
        helper + anchor,
        "runtime alignment environment helper anchor",
    )
    text = replace_once(
        text,
        "with _temporary_environment(fixture.environment):",
        "with _project_process_environment(fixture.environment):",
        "runtime alignment environment projection call",
    )
    PATH.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
