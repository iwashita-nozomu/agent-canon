#!/usr/bin/env python3
"""Run a configured algorithm-proof theme regeneration pipeline.

@dependency-start
responsibility Provides a generic runner for lean/<topic>/main.py algorithm-proof expansion entrypoints.
upstream implementation algorithm_expansion_ir.py builds Algorithm Expansion IR.
upstream implementation algorithm_lemma_graph.py builds lemma dependency graphs.
upstream implementation ../../rust/agent-canon/src/algorithm_ir_to_lean.rs generates Lean implementation models.
upstream implementation kkt_equation_section.py emits solver-chain equation sections.
upstream implementation proof_path_analyzer.py validates proof-status overlays.
downstream design ../../documents/tools/algorithm_proof_theme_runner.md documents usage.
@dependency-end
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import cast


def _find_repo_root(start: Path) -> Path:
    for path in (start, *start.parents):
        if (path / "tools" / "agent_tools").is_dir() and (path / "agents").is_dir():
            return path
        if (path / "vendor" / "agent-canon" / "tools" / "agent_tools").is_dir():
            return path
    raise SystemExit(f"cannot find repo root from {start}")


def _resolve(theme_dir: Path, value: str | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return theme_dir / path


def _stringify(value: str | Path) -> str:
    return str(value)


def _dict_list(value: object) -> list[dict[str, object]]:
    """Return JSON object rows from a JSON list."""
    if not isinstance(value, list):
        return []
    return [cast(dict[str, object], item) for item in cast(list[object], value) if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    """Return string values from a JSON list."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in cast(list[object], value)]


def _pascal(value: str) -> str:
    return "".join(part.capitalize() for part in value.replace("-", "_").split("_") if part)


class ThemeRunner:
    def __init__(self, config_path: Path, *, dry_run: bool) -> None:
        self.config_path = config_path.resolve()
        self.theme_dir = self.config_path.parent
        self.repo_root = _find_repo_root(self.theme_dir)
        vendor_tools = self.repo_root / "vendor" / "agent-canon" / "tools" / "agent_tools"
        local_tools = self.repo_root / "tools" / "agent_tools"
        self.tools_dir = vendor_tools if vendor_tools.is_dir() else local_tools
        self.dry_run = dry_run
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("theme config must be a JSON object")
        self.config = cast(dict[str, object], payload)

    def run_command(self, cmd: list[str | Path], *, cwd: Path | None = None) -> None:
        rendered = [_stringify(part) for part in cmd]
        print("+ " + " ".join(rendered))
        if self.dry_run:
            return
        subprocess.run(rendered, cwd=cwd or self.repo_root, check=True)

    def python_tool(self, name: str, *args: str | Path) -> list[str | Path]:
        return [sys.executable, self.tools_dir / name, *args]

    def agent_canon_cli(self) -> Path:
        vendor_cli = self.repo_root / "vendor" / "agent-canon" / "tools" / "bin" / "agent-canon"
        if vendor_cli.exists():
            return vendor_cli
        return self.repo_root / "tools" / "bin" / "agent-canon"

    def root_stem(self, root: dict[str, object]) -> str:
        return str(root.get("artifact_stem") or root["name"]).replace("-", "_")

    def ir_json(self, root: dict[str, object]) -> Path:
        return self.theme_dir / f"{self.root_stem(root)}_ir.json"

    def ir_markdown(self, root: dict[str, object]) -> Path:
        return self.theme_dir / f"{self.root_stem(root)}_ir.md"

    def graph_path(self, root: dict[str, object], profile: str, suffix: str) -> Path:
        stem = self.root_stem(root)
        return self.theme_dir / f"{stem}_{profile}_lemma_graph{suffix}"

    def lean_namespace(self, root: dict[str, object]) -> str:
        return f"{self.config['lean_namespace']}.Generated{_pascal(self.root_stem(root))}"

    def lean_output(self, root: dict[str, object]) -> Path:
        name = f"Generated{_pascal(self.root_stem(root))}.lean"
        return self.theme_dir / str(self.config.get("lean_dir", "PDIPMConvergence")) / name

    def profiles(self, root: dict[str, object]) -> list[str]:
        return _string_list(root.get("profiles")) or ["solver_chain"]

    def selected_roots(self, names: list[str]) -> list[dict[str, object]]:
        roots = _dict_list(self.config.get("roots"))
        requested = set(names)
        known = {str(root["name"]) for root in roots}
        unknown = requested.difference(known)
        if unknown:
            raise SystemExit(
                f"unknown root(s): {', '.join(sorted(unknown))}; "
                f"known: {', '.join(sorted(known))}"
            )
        if not requested:
            return roots
        return [root for root in roots if str(root["name"]) in requested]

    def generate_ir(self, root: dict[str, object]) -> None:
        for fmt, out in (("json", self.ir_json(root)), ("markdown", self.ir_markdown(root))):
            self.run_command(
                self.python_tool(
                    "algorithm_expansion_ir.py",
                    "--root",
                    self.repo_root,
                    "--python-symbol",
                    str(root["python_symbol"]),
                    "--target-theorem",
                    str(root["target_theorem"]),
                    "--format",
                    fmt,
                    "--out",
                    out,
                )
            )

    def generate_graphs(self, root: dict[str, object]) -> None:
        ir_json = self.ir_json(root)
        for profile in self.profiles(root):
            for fmt, suffix in (("json", ".json"), ("markdown", ".md")):
                self.run_command(
                    self.python_tool(
                        "algorithm_lemma_graph.py",
                        "--ir-json",
                        ir_json,
                        "--target-profile",
                        profile,
                        "--format",
                        fmt,
                        "--out",
                        self.graph_path(root, profile, suffix),
                    )
                )

    def generate_lean(self, root: dict[str, object]) -> None:
        if root.get("extra_shapes"):
            raise SystemExit(
                f"root {root['name']} requests extra_shapes, but generic IR-to-Lean lowering "
                "does not support algorithm-specific generated shapes"
            )
        ir_json = self.ir_json(root)
        self.run_command(
            [
                self.agent_canon_cli(),
                "algorithm-ir-to-lean",
                "--algorithm-ir",
                ir_json,
                "--namespace",
                self.lean_namespace(root),
                "--module-name",
                self.root_stem(root),
                "--out",
                self.lean_output(root),
            ]
        )

    def generate_equation_sections(self) -> None:
        sections = _dict_list(self.config.get("equation_sections"))
        roots = _dict_list(self.config.get("roots"))
        for section in sections:
            for fmt, key in (("json", "json"), ("markdown", "markdown")):
                cmd = self.python_tool("kkt_equation_section.py")
                for root in roots:
                    cmd.extend(["--ir-json", self.ir_json(root)])
                out_path = _resolve(self.theme_dir, str(section[key]))
                if out_path is None:
                    raise ValueError("equation section output path is required")
                cmd.extend(
                    [
                        "--title",
                        str(section["title"]),
                        "--format",
                        fmt,
                        "--out",
                        out_path,
                    ]
                )
                self.run_command(cmd)

    def generate_proof_path_analyses(self) -> None:
        analyses = _dict_list(self.config.get("proof_path_analyses"))
        roots = _dict_list(self.config.get("roots"))
        for analysis in analyses:
            proof_status = _resolve(self.theme_dir, str(analysis["proof_status"]))
            if proof_status is None:
                raise ValueError("proof status path is required")
            base = self.python_tool(
                "proof_path_analyzer.py",
                "--proof-status",
                proof_status,
            )
            algorithm_root = analysis.get("algorithm_root")
            if algorithm_root:
                for root in roots:
                    if str(root["name"]) == str(algorithm_root):
                        base.extend(["--algorithm-ir", self.ir_json(root)])
                        break
            for root in roots:
                for profile in self.profiles(root):
                    base.extend(["--lemma-graph", self.graph_path(root, profile, ".json")])
            for frontier in _string_list(analysis.get("proof_frontier")):
                frontier_path = _resolve(self.theme_dir, frontier)
                if frontier_path is not None:
                    base.extend(["--proof-frontier", frontier_path])
            for adoption_text in _string_list(analysis.get("adoption_text")):
                adoption_path = _resolve(self.theme_dir, adoption_text)
                if adoption_path is not None:
                    base.extend(["--adoption-text", adoption_path])

            for fmt, key in (("json", "json"), ("markdown", "markdown")):
                out_path = _resolve(self.theme_dir, str(analysis[key]))
                if out_path is None:
                    raise ValueError("proof path analysis output path is required")
                self.run_command([*base, "--format", fmt, "--out", out_path])

    def lake_build(self) -> None:
        lake_dir = _resolve(self.theme_dir, str(self.config.get("lake_build_dir", ".")))
        assert lake_dir is not None
        self.run_command(["lake", "build"], cwd=lake_dir)

    def run(self, args: argparse.Namespace) -> int:
        roots = self.selected_roots(args.root_name)

        if not args.skip_ir:
            for root in roots:
                self.generate_ir(root)

        if not args.skip_graphs:
            for root in roots:
                self.generate_graphs(root)

        if not args.skip_lean:
            for root in roots:
                self.generate_lean(root)

        if not args.skip_equations:
            self.generate_equation_sections()

        if not args.skip_proof_analysis:
            self.generate_proof_path_analyses()

        if not args.skip_lake:
            self.lake_build()

        return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Regenerate a configured algorithm-proof theme from implementation roots."
    )
    parser.add_argument("--config", required=True, help="Path to lean/<topic>/algorithm_theme.json.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")
    parser.add_argument("--root-name", action="append", default=[], help="Limit root expansion by configured name.")
    parser.add_argument("--skip-ir", action="store_true", help="Do not regenerate Algorithm Expansion IR.")
    parser.add_argument("--skip-graphs", action="store_true", help="Do not regenerate lemma graphs.")
    parser.add_argument("--skip-lean", action="store_true", help="Do not regenerate Lean implementation files.")
    parser.add_argument("--skip-equations", action="store_true", help="Do not regenerate equation sections.")
    parser.add_argument("--skip-proof-analysis", action="store_true", help="Do not regenerate proof-path reports.")
    parser.add_argument("--skip-lake", action="store_true", help="Do not run lake build.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return ThemeRunner(Path(args.config), dry_run=args.dry_run).run(args)


if __name__ == "__main__":
    raise SystemExit(main())
