# @dependency-start
# contract test
# responsibility Tests paper-writing's native local citeproc route and failure.
# upstream design ../../agents/skills/paper-writing.md paper citation command contract
# upstream design ../../documents/contracts/quarto-html-output.toml Quarto provider pin
# upstream implementation ../../tools/runtime/dispatch/tool_dispatch.py native CLI route
# @dependency-end

"""Exercise offline Pandoc citeproc through the shared Quarto CLI."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from tools.runtime.dispatch import tool_dispatch

PROJECT_ROOT = Path(__file__).resolve().parents[2]

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


def _configure_native_tool_route(tmp_path: Path, monkeypatch) -> Path:
    """Provide the authenticated image and registered-target context for dispatch."""
    image_root = tmp_path.parent / f"{tmp_path.name}-image"
    runtime_root = tmp_path.parent / f"{tmp_path.name}-runtime"
    dependencies_root = image_root / "image-dependencies"
    image_runtime = image_root / "runtime"
    dependencies_root.mkdir(parents=True)
    image_runtime.mkdir(parents=True)
    marker_paths = (
        image_root / tool_dispatch.CONTAINER_MARKER_NAME,
        image_runtime / tool_dispatch.RUNTIME_MARKER_NAME,
        dependencies_root / "plan.json",
    )
    marker_paths[0].write_bytes(tool_dispatch.CONTAINER_MARKER)
    marker_paths[1].write_bytes(tool_dispatch.RUNTIME_MARKER)
    marker_paths[2].write_text(
        '{"schema":"agent-canon-test-image/v1"}\n', encoding="utf-8"
    )
    for marker in marker_paths:
        marker.chmod(0o444)

    runtime_root.mkdir()
    output_root = runtime_root / "tool-output"
    home = runtime_root / "cache" / "home"
    home.mkdir(parents=True)
    (runtime_root / "state.json").write_text(
        json.dumps({"targets": {"fixture": {"root": str(tmp_path)}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_CANON_EXECUTION_PLANE", "tool-container")
    monkeypatch.setenv("AGENT_CANON_IMAGE_ROOT", str(image_root))
    monkeypatch.setenv("AGENT_CANON_IMAGE_DEPENDENCIES_ROOT", str(dependencies_root))
    monkeypatch.setenv("AGENT_CANON_RUNTIME_TOOLS_ROOT", str(PROJECT_ROOT))
    monkeypatch.setenv(
        "AGENT_CANON_IMAGE_MARKER_DIGEST",
        "sha256:" + hashlib.sha256(tool_dispatch.CONTAINER_MARKER).hexdigest(),
    )
    monkeypatch.setenv(
        "AGENT_CANON_RUNTIME_MARKER_DIGEST",
        "sha256:" + hashlib.sha256(tool_dispatch.RUNTIME_MARKER).hexdigest(),
    )
    monkeypatch.setenv("AGENT_CANON_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("AGENT_CANON_TARGET_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENT_CANON_OUTPUT_ROOT", str(output_root))
    # Quarto's cache belongs under this test's task-owned runtime cache rather
    # than the read-only ambient HOME of the shared contracts container.
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("AGENT_CANON_MOUNT_REGISTRY", raising=False)
    return output_root


def test_quarto_native_argv_matches_direct_probe_and_parity_record(
    tmp_path: Path,
    monkeypatch,
    capfd,
) -> None:
    """The catalog route preserves direct Quarto argv, cwd, streams, and status."""
    output_root = _configure_native_tool_route(tmp_path, monkeypatch)
    spec = tool_dispatch.load_specs(PROJECT_ROOT)[0]["quarto"]
    probe_args = ("pandoc", "--version")
    environment = tool_dispatch._environment(
        PROJECT_ROOT, spec, output_root.parent, output_root
    )
    direct = subprocess.run(
        [*spec.argv, *probe_args],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
    )
    routed_status = tool_dispatch._run_spec(
        PROJECT_ROOT,
        spec,
        probe_args,
        require_parity=False,
        container_exec=True,
    )
    routed_output = capfd.readouterr()
    direct_result = {
        "exit_code": direct.returncode,
        "stdout_sha256": hashlib.sha256(direct.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(direct.stderr).hexdigest(),
        "written_paths": [],
    }
    routed_stdout = routed_output.out.encode("utf-8")
    routed_stderr = routed_output.err.encode("utf-8")
    routed_result = {
        "exit_code": routed_status,
        "stdout_sha256": hashlib.sha256(routed_stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(routed_stderr).hexdigest(),
        "written_paths": [],
    }
    assert output_root.is_dir()
    assert routed_result == direct_result
    fixture_path = (
        PROJECT_ROOT / "tools/fixtures/tool_dispatch/public-command-parity.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    row = next(
        (entry for entry in fixture["entries"] if entry.get("id") == "quarto"),
        None,
    )
    if row is None:
        raise AssertionError(
            json.dumps(
                {
                    "id": "quarto",
                    "probe_args": list(probe_args),
                    "observed": {
                        "argv": list(spec.argv),
                        "cwd": spec.cwd_policy,
                        "stdin": spec.stdin_policy,
                        "stdout": spec.stdout_policy,
                        "stderr": spec.stderr_policy,
                        "exit": spec.exit_policy,
                        "signal": spec.signal_policy,
                        "written_paths": list(spec.written_paths),
                    },
                    "legacy_result": direct_result,
                    "container_result": routed_result,
                },
                sort_keys=True,
            )
        )
    tool_dispatch._check_parity_fixture(PROJECT_ROOT, spec)
    assert row["probe_args"] == list(probe_args)
    # The stored result hashes document their measured environment; HOME/TMPDIR
    # can change Pandoc's version output. Live parity is the same-run comparison
    # above, where both routes receive this test's identical environment.


def test_local_citations_render_and_unknown_key_fails_natively(
    tmp_path: Path,
    monkeypatch,
    capfd,
) -> None:
    """The registered native Quarto route formats local keys and propagates failure."""
    output_root = _configure_native_tool_route(tmp_path, monkeypatch)
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
        "A single citation [@alpha].\n\nA multiple citation [@alpha; @beta].\n",
        encoding="utf-8",
    )

    pandoc_options = [
        "--citeproc",
        "--bibliography",
        bibliography_path.name,
        "--csl",
        csl_path.name,
        "--to",
        "html",
        "--standalone",
        "--fail-if-warnings",
    ]
    rendered_path = output_root / "paper.html"
    spec = tool_dispatch.load_specs(PROJECT_ROOT)[0]["quarto"]
    render_status = tool_dispatch.run_container_tool(
        PROJECT_ROOT,
        spec,
        [
            "pandoc",
            manuscript_path.name,
            *pandoc_options,
            "--output",
            str(rendered_path),
        ],
    )

    render_output = capfd.readouterr()
    assert render_status == 0, render_output.out + render_output.err
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
    failed_status = tool_dispatch.run_container_tool(
        PROJECT_ROOT,
        spec,
        [
            "pandoc",
            unresolved_path.name,
            *pandoc_options,
            "--output",
            str(output_root / "unresolved.html"),
        ],
    )
    failure_output = capfd.readouterr()

    assert failed_status != 0, failure_output.out + failure_output.err
    assert "unknown-source" in failure_output.out + failure_output.err
