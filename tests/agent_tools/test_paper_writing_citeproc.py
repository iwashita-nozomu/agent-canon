# @dependency-start
# contract test
# responsibility Tests paper-writing's native local citeproc route and failure.
# upstream design ../../agents/skills/paper-writing.md paper citation command contract
# upstream design ../../documents/contracts/quarto-html-output.toml Quarto provider pin
# @dependency-end

"""Exercise offline Pandoc citeproc through the shared Quarto CLI."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


CSL_AUTHOR_DATE = """<?xml version="1.0" encoding="utf-8"?>
<style
  xmlns="http://purl.org/net/xbiblio/csl"
  version="1.0"
  class="in-text"
  default-locale="en-US">
  <info>
    <title>AgentCanon local author-date fixture</title>
    <id>https://example.invalid/styles/agent-canon-local-author-date</id>
    <link
      href="https://example.invalid/styles/agent-canon-local-author-date"
      rel="self"/>
    <updated>2026-10-11T00:00:00+00:00</updated>
  </info>
  <citation>
    <layout prefix="(" suffix=")" delimiter="; ">
      <group delimiter=" ">
        <names variable="author"><name form="short"/></names>
        <date variable="issued"><date-part name="year"/></date>
      </group>
    </layout>
  </citation>
  <bibliography>
    <layout>
      <group delimiter=". ">
        <names variable="author">
          <name name-as-sort-order="all" sort-separator=", "/>
        </names>
        <date variable="issued"><date-part name="year"/></date>
        <text variable="title" prefix="LOCAL STYLE: "/>
      </group>
    </layout>
  </bibliography>
</style>
"""


def test_local_citations_render_and_unknown_key_fails_natively(
    tmp_path: Path,
) -> None:
    """The native CLI formats local keys and fails when a key has no record."""
    bibliography_path = tmp_path / "references.json"
    bibliography_path.write_text(
        json.dumps(
            [
                {
                    "id": "alpha",
                    "type": "article-journal",
                    "author": [{"family": "Alpha", "given": "Ada"}],
                    "title": "First local source",
                    "container-title": "Fixture Journal",
                    "issued": {"date-parts": [[2020]]},
                },
                {
                    "id": "beta",
                    "type": "article-journal",
                    "author": [{"family": "Beta", "given": "Bea"}],
                    "title": "Second local source",
                    "container-title": "Fixture Journal",
                    "issued": {"date-parts": [[2021]]},
                },
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    csl_path = tmp_path / "local-author-date.csl"
    csl_path.write_text(CSL_AUTHOR_DATE, encoding="utf-8")
    manuscript_path = tmp_path / "paper.md"
    manuscript_path.write_text(
        "A single citation [@alpha].\n\n"
        "A multiple citation [@alpha; @beta].\n",
        encoding="utf-8",
    )

    pandoc_options = [
        "--citeproc",
        "--bibliography",
        str(bibliography_path),
        "--csl",
        str(csl_path),
        "--to",
        "html",
        "--standalone",
        "--fail-if-warnings",
    ]
    rendered_path = tmp_path / "paper.html"
    render = subprocess.run(
        [
            "quarto",
            "pandoc",
            str(manuscript_path),
            *pandoc_options,
            "--output",
            str(rendered_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert render.returncode == 0, render.stdout + render.stderr
    assert rendered_path.is_file()
    rendered = rendered_path.read_text(encoding="utf-8")
    assert "Alpha 2020" in rendered
    assert "Alpha 2020; Beta 2021" in rendered
    assert "LOCAL STYLE: First local source" in rendered
    assert "@alpha" not in rendered
    assert "@beta" not in rendered

    unresolved_path = tmp_path / "unresolved.md"
    unresolved_path.write_text(
        "An unresolved citation [@unknown-source].\n",
        encoding="utf-8",
    )
    failed = subprocess.run(
        [
            "quarto",
            "pandoc",
            str(unresolved_path),
            *pandoc_options,
            "--output",
            str(tmp_path / "unresolved.html"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert failed.returncode != 0, failed.stdout + failed.stderr
    assert "unknown-source" in failed.stdout + failed.stderr
