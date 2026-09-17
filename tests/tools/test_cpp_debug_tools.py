"""Check native debug-tool provisioning without running product workloads."""

# @dependency-start
# contract test
# responsibility Verifies native debug packages and unchanged resident isolation.
# upstream design ../../documents/design/cpp-debugging.md diagnostic tool boundary
# upstream implementation ../../bootstrap/container/image/Dockerfile tool image
# @dependency-end

from __future__ import annotations

import shlex
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "bootstrap/container/image/Dockerfile"


class CppDebugToolsTests(unittest.TestCase):
    """Test the existing image transaction, not an alternative installer."""

    def test_native_tools_use_unpinned_apt_packages(self) -> None:
        """The image installs both utilities through its existing transaction."""
        text = DOCKERFILE.read_text(encoding="utf-8")
        install = text.split("apt-get install", 1)[1].split(";", 1)[0]
        arguments = shlex.split(install.replace("\\\n", " "))
        for package in ("gdb", "valgrind"):
            with self.subTest(package=package):
                self.assertIn(package, arguments)
        self.assertEqual(text.count("apt-get update"), 1)
        self.assertEqual(text.count("apt-get install"), 1)

    def test_debug_tools_do_not_relax_resident_isolation(self) -> None:
        """Installing a debugger grants no additional process privileges."""
        text = DOCKERFILE.read_text(encoding="utf-8")
        for label in (
            'io.agent-canon.run.cap-drop="ALL"',
            'io.agent-canon.run.no-new-privileges="true"',
            'io.agent-canon.run.read-only-rootfs="true"',
            'io.agent-canon.run.network="none"',
        ):
            with self.subTest(label=label):
                self.assertIn(label, text)
        for option in ("--privileged", "SYS_PTRACE", "seccomp=unconfined"):
            with self.subTest(option=option):
                self.assertNotIn(option, text)


if __name__ == "__main__":
    unittest.main()
