# @dependency-start
# contract reference
# responsibility Validates that the split Codex CLI Markdown sections reconstruct the preserved full source body.
# upstream design ../source/codex_cli_guide_config_deepdive.full.md complete source body.
# downstream design ../MANIFEST.md records expected split ranges and hashes.
# @dependency-end

from __future__ import annotations

import hashlib
from pathlib import Path

MARKER = "<!-- split-content-start -->"
SECTION_FILES = [
    "01-overview-and-basic-usage.md",
    "02-project-operations-and-subagents.md",
    "03-experimental-features.md",
    "04-mcp-deep-dive.md",
    "05-operation-pattern-diagrams.md",
    "06-practice-cards-mcp-experiments.md",
    "07-configuration-writing-fundamentals-and-recipes-001-113.md",
    "08-additional-configuration-recipes-114-253.md",
    "09-final-templates-and-references.md",
]


def body_after_marker(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if MARKER not in text:
        raise SystemExit(f"missing marker in {path}")
    return text.rsplit(MARKER, 1)[1].lstrip("\n")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    source = body_after_marker(root / "source" / "codex_cli_guide_config_deepdive.full.md")
    reconstructed = "".join(body_after_marker(root / "sections" / name) for name in SECTION_FILES)

    source_sha = sha256(source)
    reconstructed_sha = sha256(reconstructed)
    source_lines = len(source.splitlines())
    reconstructed_lines = len(reconstructed.splitlines())

    print(f"source_sha256={source_sha}")
    print(f"reconstructed_sha256={reconstructed_sha}")
    print(f"source_lines={source_lines}")
    print(f"reconstructed_lines={reconstructed_lines}")
    print(f"sections={len(SECTION_FILES)}")

    if source != reconstructed:
        raise SystemExit("split validation failed: reconstructed body differs from full source")
    print("split validation passed")


if __name__ == "__main__":
    main()
