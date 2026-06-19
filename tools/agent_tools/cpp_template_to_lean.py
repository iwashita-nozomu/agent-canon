#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Fully expands C++ template source roots into Lean evidence definitions.
# upstream implementation cpp_source_canonical_ir.py extracts C++ source-canonical IR.
# upstream implementation operational_ir_to_lean.py renders Lean evidence.
# downstream design ../../documents/tools/cpp_template_to_lean.md documents it.
# downstream implementation ../../tests/agent_tools/test_cpp_template_to_lean.py tests it.
# @dependency-end
"""Expand one C++ template source root into complete Lean evidence."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from cpp_source_canonical_ir import build_cpp_source_canonical_ir, render_record
from operational_ir_to_lean import (
    enforce_complete_coverage,
    normalize_render_input,
    render_lean,
    validate_namespace,
)


def write_text(path: Path, content: str) -> None:
    """Write a deterministic text artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root used to resolve relative C++ source paths.",
    )
    parser.add_argument(
        "--cpp-symbol",
        required=True,
        help="Root C++ symbol in path.{cc,cpp,h,hpp}::qualname form.",
    )
    parser.add_argument("--namespace", required=True, help="Lean namespace for generated evidence.")
    parser.add_argument(
        "--module-name",
        help="Nested Lean namespace for this generated module. Defaults from root metadata.",
    )
    parser.add_argument("--out", help="Optional Lean output path. When omitted, print to stdout.")
    parser.add_argument(
        "--record-out",
        help="Optional path for the fully expanded C++ source-canonical JSON record.",
    )
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the C++ template to Lean evidence expansion."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        namespace = validate_namespace(str(args.namespace))
        record = build_cpp_source_canonical_ir(str(args.cpp_symbol), root=Path(args.root))
        if args.record_out:
            write_text(Path(args.record_out), render_record(record, "json"))
        render_input = normalize_render_input(record)
        module_name = validate_namespace(str(args.module_name or render_input.module_name))
        enforce_complete_coverage(render_input)
        rendered = render_lean(render_input, namespace=namespace, module_name=module_name)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if args.out:
        write_text(Path(args.out), rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
