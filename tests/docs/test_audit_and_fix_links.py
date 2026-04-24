"""Tests for markdown link audit parsing."""

# Dependency Files:
# - vendor/agent-canon/documents/dependency-headers.md
# - vendor/agent-canon/tools/docs/audit_and_fix_links.py

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "docs" / "audit_and_fix_links.py"


def load_audit_module() -> ModuleType:
    """Load the link-audit script as a test module."""
    spec = importlib.util.spec_from_file_location("audit_and_fix_links", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MarkdownLinkParserTest(unittest.TestCase):
    """Exercise markdown link extraction edge cases."""

    def test_skips_code_fences_and_display_math(self) -> None:
        """Code/math examples are not documentation links."""
        module = load_audit_module()
        links = module.find_markdown_links(
            "\n".join(
                [
                    "[real](README.md)",
                    "```python",
                    "[code](missing.py)",
                    "```",
                    "$$",
                    "C[link](not-a-link)",
                    "$$",
                    "[also real](documents/README.md)",
                    "",
                ]
            )
        )

        self.assertEqual(
            links,
            [("real", "README.md"), ("also real", "documents/README.md")],
        )


if __name__ == "__main__":
    unittest.main()
