# @dependency-start
# contract test
# responsibility Tests semantic provider HTML report rendering.
# upstream implementation ../../tools/analysis/search/reporting/semantic_provider_html_report.py renders semantic provider comparison HTML
# upstream design ../../agents/skills/html-output.md owns HTML artifact generation and validation
# upstream design ../../documents/tools/semantic_index.md defines semantic provider comparison authority boundaries
# @dependency-end
"""Tests for semantic provider HTML reports."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "analysis" / "search" / "reporting" / "semantic_provider_html_report.py"


def event_string(event: dict[str, object], name: str) -> str:
    value = event.get(name)
    if not isinstance(value, str):
        raise AssertionError(f"event field {name} is not text")
    return value


def event_argv(event: dict[str, object]) -> list[str]:
    value = event.get("argv")
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise AssertionError("event argv is not a string list")
    return cast(list[str], value)


def install_fake_renderers(root: Path) -> tuple[Path, Path]:
    """Create CLI fakes that record Quarto inputs and Lychee's selected path."""
    bin_dir = root / "bin"
    bin_dir.mkdir()
    events = root / "events.jsonl"
    events.touch()
    quarto = bin_dir / "quarto"
    quarto.write_text(
        """#!python-executable
import json
import os
import shutil
import sys
from pathlib import Path

args = sys.argv[1:]
events_path = Path(os.environ["FAKE_RENDER_EVENTS"])

def record(item):
    with events_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(item) + "\\n")

def project_for(source):
    for parent in (source.parent, *source.parents):
        if (parent / "_quarto.yml").is_file():
            return parent
    return None

if args == ["--version"]:
    print("1.10.19")
elif args == ["pandoc", "--version"]:
    print("pandoc 3.4.0.1")
elif args[0] == "inspect":
    source = Path(args[1])
    inspect_output = Path(args[2])
    figure = source.parent / "provider-delta.svg"
    project = project_for(source)
    inspect_output.write_text(
        json.dumps({"resources": ["provider-delta.svg"], "formats": {"html": {}}, "project": str(project) if project else None}),
        encoding="utf-8",
    )
    record({"kind": "inspect", "argv": args, "source_path": str(source), "project": str(project) if project else None, "source": source.read_text(encoding="utf-8"), "figure": figure.read_text(encoding="utf-8")})
elif args[0] == "render":
    render_status = int(os.environ.get("FAKE_RENDER_STATUS", "0"))
    if render_status:
        print("fake render failure", file=sys.stderr)
        raise SystemExit(render_status)
    source = Path(args[1])
    project = project_for(source)
    if project is not None and os.environ.get("FAKE_PROJECT_MARKER"):
        project_config = (project / "_quarto.yml").read_text(encoding="utf-8")
        if "pre-render:" in project_config:
            Path(os.environ["FAKE_PROJECT_MARKER"]).write_text("hook-ran", encoding="utf-8")
    output_name = args[args.index("--output") + 1]
    output_dir = Path(args[args.index("--output-dir") + 1])
    output_dir.mkdir(parents=True, exist_ok=True)
    asset_dir = output_dir / f"{Path(output_name).stem}_files"
    asset_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source.parent / "provider-delta.svg", asset_dir / "provider-delta.svg")
    output = output_dir / output_name
    output.write_text(
        f'<html><body><img src="{asset_dir.name}/provider-delta.svg"></body></html>\\n',
        encoding="utf-8",
    )
    record({"kind": "render", "argv": args, "source_path": str(source), "project": str(project) if project else None})
else:
    raise SystemExit(2)
""".replace("#!python-executable", f"#!{sys.executable}"),
        encoding="utf-8",
    )
    quarto.chmod(0o755)
    lychee = bin_dir / "lychee"
    lychee.write_text(
        """#!python-executable
import json
import os
import sys
from pathlib import Path

with Path(os.environ["FAKE_RENDER_EVENTS"]).open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({"kind": "lychee", "argv": sys.argv[1:]}) + "\\n")
raise SystemExit(int(os.environ.get("FAKE_LYCHEE_STATUS", "0")))
""".replace("#!python-executable", f"#!{sys.executable}"),
        encoding="utf-8",
    )
    lychee.chmod(0o755)
    return bin_dir, events


def sample_compare_report() -> dict[str, object]:
    """Return a minimal compare-providers report."""
    return {
        "semantic_index_provider_compare": "ok",
        "db": "reports/semantic-index.sqlite",
        "top_k": 10,
        "min_score": 0.82,
        "left": {
            "provider": "deterministic-dense-v1",
            "model": "hash-token-char-v1",
            "dim": 128,
            "nodes": 20,
            "merge_candidates": 4,
        },
        "right": {
            "provider": "deterministic-sparse-v1",
            "model": "hash-token-char-v1",
            "dim": 128,
            "nodes": 20,
            "merge_candidates": 5,
        },
        "merge_candidates": {
            "left_count": 4,
            "right_count": 5,
            "shared_count": 2,
            "overlap_ratio": 0.4,
            "shared": ["documents/a.md:document:1-20|documents/b.md:document:1-20"],
            "left_only": ["documents/left.md:document:1-8|documents/<script>.md:document:1-8"],
            "right_only": ["documents/right.md:document:2-9|documents/peer.md:document:1-7"],
        },
        "search": {
            "query_chars": 42,
            "left_count": 3,
            "right_count": 3,
            "shared_count": 1,
            "overlap_ratio": 1 / 3,
            "left_top": [
                {
                    "rank": 1,
                    "score": 0.91,
                    "path": "documents/a.md",
                    "node_kind": "document",
                    "line_start": 1,
                    "line_end": 20,
                }
            ],
            "right_top": [
                {
                    "rank": 1,
                    "score": 0.93,
                    "path": "documents/c.md",
                    "node_kind": "document",
                    "line_start": 2,
                    "line_end": 18,
                }
            ],
            "left_only": ["documents/a.md:document:1-20"],
            "right_only": ["documents/c.md:document:2-18"],
        },
    }


class SemanticProviderHtmlReportTest(unittest.TestCase):
    """Verify semantic provider report rendering."""

    def run_report(
        self,
        root: Path,
        report: dict[str, object],
        output: Path,
        *,
        embed_resources: bool = False,
        source_text: str | None = None,
        missing_source: bool = False,
        quarto_available: bool = True,
        render_status: int = 0,
        lychee_status: int = 0,
        tmpdir: Path | None = None,
        project_marker: Path | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], list[dict[str, object]]]:
        compare_json = root / "compare.json"
        if not missing_source:
            compare_json.write_text(
                source_text if source_text is not None else json.dumps(report),
                encoding="utf-8",
            )
        bin_dir, event_path = install_fake_renderers(root)
        if not quarto_available:
            (bin_dir / "quarto").unlink()
        env = os.environ.copy()
        env["PATH"] = str(bin_dir)
        env["FAKE_RENDER_EVENTS"] = str(event_path)
        env["FAKE_RENDER_STATUS"] = str(render_status)
        env["FAKE_LYCHEE_STATUS"] = str(lychee_status)
        if tmpdir is not None:
            env["TMPDIR"] = str(tmpdir)
        if project_marker is not None:
            env["FAKE_PROJECT_MARKER"] = str(project_marker)
        argv = [
            sys.executable,
            str(SCRIPT),
            "--compare-json",
            str(compare_json),
            "--output",
            str(output),
        ]
        if embed_resources:
            argv.append("--embed-resources")
        result = subprocess.run(
            argv,
            cwd=PROJECT_ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        events: list[dict[str, object]] = []
        for line in event_path.read_text(encoding="utf-8").splitlines():
            parsed: object = json.loads(line)
            if not isinstance(parsed, dict):
                raise AssertionError("fake renderer event is not an object")
            events.append(cast(dict[str, object], parsed))
        return result, events

    def test_render_html_report(self) -> None:
        """The CLI delegates static HTML rendering and preserves report facts."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output = root / "report.html"
            result, events = self.run_report(root, sample_compare_report(), output)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("SEMANTIC_PROVIDER_HTML_REPORT=", result.stdout)
            result_line = next(
                line
                for line in result.stdout.splitlines()
                if line.startswith("SEMANTIC_PROVIDER_HTML_REPORT_RESULT=")
            )
            receipt = json.loads(result_line.split("=", 1)[1])
            self.assertEqual(receipt["status"], "rendered")
            self.assertEqual(
                receipt["configuration"]["project"], {"type": "default"}
            )
            self.assertEqual(receipt["validation"]["lychee"], "pass")
            self.assertEqual(receipt["quarto_version"], "1.10.19")
            self.assertEqual(receipt["pandoc_version"], "pandoc 3.4.0.1")
            self.assertEqual(
                receipt["output_sha256"],
                hashlib.sha256(output.read_bytes()).hexdigest(),
            )
            self.assertTrue(receipt["asset_sha256"])
            source = event_string(events[0], "source")
            self.assertIn("Provider Delta To Shared Candidate Logic", source)
            self.assertIn("deterministic-dense-v1", source)
            self.assertIn("deterministic-sparse-v1", source)
            self.assertIn(
                "candidate_logic_authority=shared_responsibility_bucket",
                source,
            )
            self.assertIn(
                "`documents/left.md:document:1-8|documents/<script>.md:document:1-8`",
                source,
            )
            render_argv = event_argv(events[1])
            self.assertIn("--no-execute", render_argv)
            self.assertIn("--to", render_argv)
            self.assertEqual(events[-1]["kind"], "lychee")
            self.assertIn("--config", event_argv(events[-1]))
            self.assertIn("report_files/provider-delta.svg", output.read_text(encoding="utf-8"))
            self.assertTrue((root / "report_files" / "provider-delta.svg").is_file())

    def test_missing_search_section_is_allowed(self) -> None:
        """A compare report without query search is still rendered by Quarto."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            report = sample_compare_report()
            report["search"] = None
            output = root / "report.html"
            result, events = self.run_report(root, report, output)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("search not recorded", event_string(events[0], "figure"))
            self.assertIn(
                "Search comparison was not recorded",
                event_string(events[0], "source"),
            )

    def test_embedded_resources_are_explicit_opt_in(self) -> None:
        """Resource embedding only appears in Quarto metadata when requested."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output = root / "embedded.html"
            result, events = self.run_report(
                root, sample_compare_report(), output, embed_resources=True
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                "embed-resources: true", event_string(events[0], "source")
            )
            result_line = next(
                line
                for line in result.stdout.splitlines()
                if line.startswith("SEMANTIC_PROVIDER_HTML_REPORT_RESULT=")
            )
            receipt = json.loads(result_line.split("=", 1)[1])
            self.assertTrue(receipt["configuration"]["embed-resources"])

    def test_staging_ignores_quarto_project_from_tmpdir(self) -> None:
        """A caller TMPDIR cannot expose parent Quarto render hooks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            project = root / "caller-project"
            project.mkdir()
            marker = project / "pre-render-ran.txt"
            project_config = (
                "project:\n"
                "  type: default\n"
                "  pre-render: touch pre-render-ran.txt\n"
            )
            (project / "_quarto.yml").write_text(project_config, encoding="utf-8")
            nested_tmp = project / "tmp"
            nested_tmp.mkdir()
            output = project / "report.html"
            result, events = self.run_report(
                project,
                sample_compare_report(),
                output,
                tmpdir=nested_tmp,
                project_marker=marker,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(output.is_file())
            self.assertFalse(marker.exists())
            inspect_event = next(event for event in events if event["kind"] == "inspect")
            render_event = next(event for event in events if event["kind"] == "render")
            generated_source = Path(event_string(inspect_event, "source_path"))
            generated_project = generated_source.parent
            self.assertEqual(inspect_event["project"], str(generated_project))
            self.assertEqual(render_event["project"], str(generated_project))
            self.assertIn(project.resolve(), generated_source.parents)
            self.assertEqual(
                (generated_project / "_quarto.yml").read_text(encoding="utf-8"),
                "project:\n  type: default\n",
            )

    def test_failure_states_distinguish_source_renderer_render_and_validation(self) -> None:
        """The CLI keeps owning failure states distinct at its native boundaries."""
        cases = (
            ("missing_asset", 1, True, None, True, 0, 0),
            ("invalid_source", 1, False, "not json", True, 0, 0),
            ("renderer_unavailable", 1, False, None, False, 0, 0),
            ("render_failed", 7, False, None, True, 7, 0),
            ("validation_failed", 1, False, None, True, 0, 1),
        )
        for (
            expected_status,
            expected_exit_code,
            missing,
            source_text,
            has_quarto,
            render_status,
            lychee_status,
        ) in cases:
            with self.subTest(status=expected_status), tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                result, _ = self.run_report(
                    root,
                    sample_compare_report(),
                    root / "report.html",
                    missing_source=missing,
                    source_text=source_text,
                    quarto_available=has_quarto,
                    render_status=render_status,
                    lychee_status=lychee_status,
                )
                self.assertEqual(result.returncode, expected_exit_code)
                result_line = next(
                    line
                    for line in result.stdout.splitlines()
                    if line.startswith("SEMANTIC_PROVIDER_HTML_REPORT_RESULT=")
                )
                receipt = json.loads(result_line.split("=", 1)[1])
                self.assertEqual(receipt["status"], expected_status)


if __name__ == "__main__":
    unittest.main()
