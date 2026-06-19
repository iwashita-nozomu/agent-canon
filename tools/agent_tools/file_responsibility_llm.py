#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Runs advisory local LLM responsibility review for exactly one file.
# upstream design ../../documents/local-llm-responsibility-analysis.md local LLM single-file policy
# upstream design ../../documents/responsibility-scope-management.md responsibility scope policy
# upstream design ../../tools/README.md tool entrypoint index
# upstream design ../../documents/tools/README.md user-facing tool index
# downstream implementation ../../tests/agent_tools/test_file_responsibility_llm.py tests scope limits and prompt rendering
# @dependency-end
"""Run advisory local LLM responsibility review for one file."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "ggml-org/SmolLM3-3B-GGUF:Q4_K_M"
DEFAULT_MAX_BYTES = 24_000
DEFAULT_PREDICT_TOKENS = 768
PROMPT_DIGEST_LENGTH = 12
LOCAL_LLM_CPU_ENV = {
    "CUDA_VISIBLE_DEVICES": "",
    "NVIDIA_VISIBLE_DEVICES": "void",
    "HIP_VISIBLE_DEVICES": "",
    "ROCR_VISIBLE_DEVICES": "",
}


@dataclass(frozen=True)
class ReviewTarget:
    """One validated single-file review target."""

    root: Path
    path: Path
    relative_path: str
    text: str


@dataclass(frozen=True)
class LlamaCommand:
    """A rendered llama.cpp command."""

    executable: str
    model: str
    prompt: str
    predict_tokens: int

    def argv(self) -> list[str]:
        """Return command arguments."""
        return [
            self.executable,
            "-hf",
            self.model,
            "-p",
            self.prompt,
            "-n",
            str(self.predict_tokens),
            "--temp",
            "0.1",
        ]


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", help="Exactly one file to review.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--model", default=os.environ.get("AGENT_CANON_LOCAL_LLM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--llama-cli", default=os.environ.get("AGENT_CANON_LLAMA_CLI", ""))
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--predict-tokens", type=int, default=DEFAULT_PREDICT_TOKENS)
    parser.add_argument("--print-prompt", action="store_true")
    return parser


def relative(root: Path, path: Path) -> str:
    """Return a stable root-relative path."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def read_target(root: Path, raw_file: str, max_bytes: int) -> ReviewTarget:
    """Read and validate the single file target."""
    path = (root / raw_file).resolve() if not Path(raw_file).is_absolute() else Path(raw_file)
    if not path.is_file():
        raise ValueError(f"single-file target is required: {raw_file}")
    data = path.read_bytes()
    if len(data) > max_bytes:
        data = data[:max_bytes]
    text = data.decode("utf-8", errors="replace")
    return ReviewTarget(
        root=root.resolve(),
        path=path,
        relative_path=relative(root.resolve(), path),
        text=text,
    )


def prompt_for_target(target: ReviewTarget) -> str:
    """Return the local LLM prompt for one file."""
    return "\n".join(
        [
            "You are an advisory code/document responsibility reviewer.",
            "Scope: exactly one file. Do not infer repo-wide ownership.",
            "Primary authority remains dependency headers, tool catalog, and responsibility manifests.",
            "Return concise Markdown with these headings only:",
            "1. Responsibility Summary",
            "2. Possible Ownership Mismatch",
            "3. Missing Protecting Tool Or Issue Evidence",
            "4. Deterministic Follow-Up Checks",
            "",
            f"File: {target.relative_path}",
            "",
            "Content:",
            "```",
            target.text,
            "```",
        ]
    )


def prompt_digest(prompt: str) -> str:
    """Return a stable prompt hash."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:PROMPT_DIGEST_LENGTH]


def find_llama_cli(explicit: str) -> str:
    """Resolve the llama-cli executable."""
    tools_home = Path(os.environ.get("AGENT_CANON_TOOLS_HOME", str(Path.home() / ".tools")))
    candidates = [
        explicit,
        str(tools_home / "bin" / "llama-cli"),
        str(Path.home() / ".tools" / "bin" / "llama-cli"),
        shutil.which("llama-cli") or "",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return ""


def run_llama(command: LlamaCommand) -> subprocess.CompletedProcess[str]:
    """Run llama.cpp for one prompt."""
    return subprocess.run(
        command.argv(),
        check=False,
        capture_output=True,
        text=True,
        env=local_llm_cpu_env(),
    )


def local_llm_cpu_env() -> dict[str, str]:
    """Return process environment with accelerator devices hidden."""
    return {**os.environ, **LOCAL_LLM_CPU_ENV}


def print_status(target: ReviewTarget, model: str, digest: str, status: str) -> None:
    """Print common machine-readable status lines."""
    print("FILE_RESP_LLM_SCOPE=single_file")
    print(f"FILE_RESP_LLM_FILE={target.relative_path}")
    print(f"FILE_RESP_LLM_MODEL={model}")
    print(f"FILE_RESP_LLM_PROMPT_SHA={digest}")
    print(f"FILE_RESP_LLM={status}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local LLM single-file responsibility review."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    try:
        target = read_target(root, args.file, args.max_bytes)
    except ValueError as exc:
        print(f"FILE_RESP_LLM_ERROR={exc}", file=sys.stderr)
        return 2
    prompt = prompt_for_target(target)
    digest = prompt_digest(prompt)
    if args.print_prompt:
        print_status(target, args.model, digest, "prompt")
        print(prompt)
        return 0

    executable = find_llama_cli(args.llama_cli)
    if not executable:
        print_status(target, args.model, digest, "unavailable")
        print("FILE_RESP_LLM_ERROR=llama-cli-not-found", file=sys.stderr)
        return 2

    result = run_llama(
        LlamaCommand(
            executable=executable,
            model=args.model,
            prompt=prompt,
            predict_tokens=args.predict_tokens,
        )
    )
    print_status(target, args.model, digest, "pass" if result.returncode == 0 else "fail")
    if result.stdout.strip():
        print(result.stdout)
    if result.stderr.strip():
        print(result.stderr, file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
