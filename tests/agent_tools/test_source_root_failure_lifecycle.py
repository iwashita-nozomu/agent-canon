"""Regression tests for SourceRootFailure exception semantics."""

# @dependency-start
# contract test
# responsibility Verifies SourceRootFailure follows the Python exception lifecycle.
# upstream implementation ../../tools/agent_tools/agent_canon_source_root.py SourceRootFailure definition
# @dependency-end

from __future__ import annotations

import sys
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = PROJECT_ROOT / "tools" / "agent_tools"
sys.path.insert(0, str(TOOLS_ROOT))

from agent_canon_source_root import SourceRootFailure  # noqa: E402


@contextmanager
def _generator_boundary() -> Iterator[None]:
    """Pass exceptions through contextlib's generator lifecycle."""
    yield


class _RecordingContext:
    """Record class-based context-manager cleanup inputs."""

    def __init__(self) -> None:
        self.exit_value: BaseException | None = None
        self.exit_traceback: TracebackType | None = None

    def __enter__(self) -> "_RecordingContext":
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        self.exit_value = exc_value
        self.exit_traceback = traceback
        return False


class SourceRootFailureLifecycleTests(unittest.TestCase):
    """Preserve typed payloads while Python manages exception state."""

    def test_direct_raise_preserves_payload_and_arguments(self) -> None:
        """Direct raise keeps the typed payload and BaseException arguments."""
        failure = SourceRootFailure("direct_code", "direct detail")
        caught: SourceRootFailure | None = None

        try:
            raise failure
        except SourceRootFailure as exc:
            caught = exc
            self.assertIsNotNone(exc.__traceback__)

        self.assertIs(caught, failure)
        self.assertEqual(failure.code, "direct_code")
        self.assertEqual(failure.detail, "direct detail")
        self.assertEqual(failure.args, ("direct_code", "direct detail"))

    def test_chained_raise_preserves_cause_context_and_payload(self) -> None:
        """Explicit chaining keeps runtime links and typed diagnostics."""
        cause = RuntimeError("root cause")
        failure = SourceRootFailure("chained_code", "chained detail")
        caught: SourceRootFailure | None = None

        try:
            try:
                raise cause
            except RuntimeError:
                raise failure from cause
        except SourceRootFailure as exc:
            caught = exc

        self.assertIs(caught, failure)
        self.assertIs(failure.__cause__, cause)
        self.assertIs(failure.__context__, cause)
        self.assertTrue(failure.__suppress_context__)
        self.assertEqual(failure.code, "chained_code")
        self.assertEqual(failure.detail, "chained detail")

    def test_generator_contextmanager_preserves_original_failure(self) -> None:
        """contextlib traceback restoration cannot replace the typed failure."""
        failure = SourceRootFailure("generator_code", "generator detail")
        caught: SourceRootFailure | None = None

        try:
            with _generator_boundary():
                raise failure
        except SourceRootFailure as exc:
            caught = exc

        self.assertIs(caught, failure)
        self.assertIsNotNone(failure.__traceback__)
        self.assertEqual(failure.code, "generator_code")
        self.assertEqual(failure.detail, "generator detail")

    def test_class_contextmanager_cleanup_observes_original_failure(self) -> None:
        """Ordinary with cleanup receives and propagates the typed failure."""
        cleanup = _RecordingContext()
        failure = SourceRootFailure("cleanup_code", "cleanup detail")
        caught: SourceRootFailure | None = None

        try:
            with cleanup:
                raise failure
        except SourceRootFailure as exc:
            caught = exc

        self.assertIs(caught, failure)
        self.assertIs(cleanup.exit_value, failure)
        self.assertIsNotNone(cleanup.exit_traceback)
        self.assertEqual(failure.code, "cleanup_code")
        self.assertEqual(failure.detail, "cleanup detail")


if __name__ == "__main__":
    unittest.main()
