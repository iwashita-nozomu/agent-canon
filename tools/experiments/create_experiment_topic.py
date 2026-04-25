#!/usr/bin/env python3
# @dependency-start
# upstream design ../README.md shared automation index
# @dependency-end

"""Create one experiment topic from the template and register it."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from registry_lib import find_topic
from registry_lib import load_registry
from registry_lib import write_registry


def repo_root_from_script() -> Path:
    """Return the repository root from this script location."""
    return Path(__file__).absolute().parents[2]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Create experiments/<topic>/ from the template and append one registry entry."
    )
    parser.add_argument("topic", help="New experiment topic name.")
    parser.add_argument(
        "--repo-root",
        default=str(repo_root_from_script()),
        help="Repository root. Defaults to the path inferred from this script.",
    )
    parser.add_argument(
        "--registry",
        help="Optional registry path. Defaults to <repo-root>/experiments/registry.toml.",
    )
    parser.add_argument(
        "--template-topic",
        default="_template",
        help="Template topic directory name under experiments/.",
    )
    parser.add_argument(
        "--status",
        default="draft",
        help="Initial topic status for the registry entry.",
    )
    parser.add_argument(
        "--default-variant",
        default="formal",
        help="Default variant label for this topic.",
    )
    parser.add_argument(
        "--primary-note",
        help="Optional note path to record as primary_note in the registry.",
    )
    parser.add_argument(
        "--active-branch",
        help="Optional active_branch to write into the new registry entry.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing topic directory after deleting it first.",
    )
    return parser


def replace_topic_tokens(path: Path, topic_name: str) -> None:
    """Replace template topic tokens in one copied file."""
    text = path.read_text(encoding="utf-8")
    text = text.replace("<topic>", topic_name)
    if path.name == "README.md" and text.startswith("# Experiment Topic Template"):
        text = text.replace("# Experiment Topic Template", f"# {topic_name}", 1)
    path.write_text(text, encoding="utf-8")


def update_copied_files(topic_dir: Path, topic_name: str) -> None:
    """Patch copied template files with the new topic name."""
    for relative in ("README.md",):
        replace_topic_tokens(topic_dir / relative, topic_name)


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    registry_path = Path(args.registry).resolve() if args.registry else repo_root / "experiments" / "registry.toml"
    registry = load_registry(registry_path)

    if find_topic(registry, args.topic) is not None:
        raise SystemExit(f"topic {args.topic!r} already exists in {registry_path}")

    defaults = registry.get("defaults", {})
    if not isinstance(defaults, dict):
        raise SystemExit("registry defaults must be a table")
    template_dir_name = defaults.get("topic_template_dir", f"experiments/{args.template_topic}")
    if not isinstance(template_dir_name, str):
        raise SystemExit("defaults.topic_template_dir must be a string when present")

    template_dir = repo_root / template_dir_name
    topic_dir = repo_root / "experiments" / args.topic
    if topic_dir.exists():
        if not args.force:
            raise SystemExit(f"topic directory already exists: {topic_dir}")
        shutil.rmtree(topic_dir)

    shutil.copytree(template_dir, topic_dir)
    update_copied_files(topic_dir, args.topic)

    topics = registry.get("topics")
    if not isinstance(topics, list):
        raise SystemExit("registry must contain [[topics]]")
    new_entry: dict[str, object] = {
        "name": args.topic,
        "status": args.status,
        "topic_dir": f"experiments/{args.topic}",
        "topic_readme": f"experiments/{args.topic}/README.md",
        "canonical_entrypoint": f"experiments/{args.topic}/experimentcode.py",
        "result_root": f"experiments/{args.topic}/result",
        "report_root": "experiments/report",
        "default_variant": args.default_variant,
        "smoke_inner_command": (
            f"python3 experiments/{args.topic}/experimentcode.py --run-dir {{run_dir}} --limit 4"
        ),
        "formal_inner_command": (
            f"python3 experiments/{args.topic}/experimentcode.py --run-dir {{run_dir}} --limit 32"
        ),
    }
    if args.primary_note:
        new_entry["primary_note"] = args.primary_note
    if args.active_branch:
        new_entry["active_branch"] = args.active_branch
    topics.append(new_entry)
    write_registry(registry_path, registry)

    print(f"topic_dir={topic_dir}")
    print(f"registry_path={registry_path}")
    print(f"topic_name={args.topic}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
