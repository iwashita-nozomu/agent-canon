#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides create experiment topic experiment workflow tooling.
# upstream design ../README.md shared automation index
# upstream design ../../templates/documents/experiment/README.template.md canonical topic README template.
# upstream design ../../templates/documents/experiment/experiment-provenance.template.toml canonical provenance template.
# downstream implementation ../../templates/experiments/_template/run.py runnable topic scaffold and orchestration boundary.
# downstream implementation ../../templates/experiments/_template/case_model.py reusable case/result models.
# downstream implementation ../../templates/experiments/_template/artifact_schema.py stable artifact schemas.
# downstream implementation ../../templates/experiments/_template/artifact_io.py atomic artifact publication.
# upstream design ../../documents/experiments/experiment-registry.md project experiment registry contract.
# @dependency-end

"""Create one experiment topic from the template and register it."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from registry_lib import find_topic, load_registry, write_registry

AGENT_CANON_TEMPLATE_DIR = "vendor/agent-canon/templates/experiments/_template"
CANONICAL_EXPERIMENT_TEMPLATE_DIR = "vendor/agent-canon/templates/documents/experiment"
CANONICAL_README_TEMPLATE = "README.template.md"
CANONICAL_PROVENANCE_TEMPLATE = "experiment-provenance.template.toml"


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
        "--status",
        default="draft",
        help="Initial topic status for the registry entry.",
    )
    parser.add_argument(
        "--default-variant",
        default="default",
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve inputs and show the planned files without writing a topic or registry.",
    )
    return parser


def replace_topic_tokens(path: Path, topic_name: str) -> None:
    """Replace template topic tokens in one copied file."""
    text = path.read_text(encoding="utf-8")
    text = text.replace("<topic>", topic_name).replace("<Experiment topic>", topic_name)
    if path.name == "README.md" and text.startswith("# Experiment Topic Template"):
        text = text.replace("# Experiment Topic Template", f"# {topic_name}", 1)
    path.write_text(text, encoding="utf-8")


def update_copied_files(topic_dir: Path, topic_name: str) -> None:
    """Patch copied template files with the new topic name."""
    for relative in ("README.md", "provenance.toml"):
        replace_topic_tokens(topic_dir / relative, topic_name)


def resolve_canon_path(repo_root: Path, logical_path: str) -> Path:
    """Resolve a canonical AgentCanon path in parent, standalone, or source checkouts."""
    source_root = Path(__file__).resolve().parents[2]
    vendor_root = repo_root / "vendor" / "agent-canon"
    candidates = (
        [vendor_root / logical_path, repo_root / logical_path, source_root / logical_path]
        if vendor_root.exists()
        else [repo_root / logical_path, source_root / logical_path]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def resolve_topic_template_dir(repo_root: Path, configured_path: str) -> Path:
    """Resolve the runnable scaffold without changing its owner."""
    configured = resolve_canon_path(repo_root, configured_path.removeprefix("vendor/agent-canon/"))
    if configured.is_dir():
        return configured
    fallback = resolve_canon_path(repo_root, "templates/experiments/_template")
    return fallback


def resolve_document_templates(repo_root: Path) -> tuple[Path, Path]:
    """Resolve the canonical topic README and provenance templates."""
    template_dir = resolve_canon_path(
        repo_root,
        CANONICAL_EXPERIMENT_TEMPLATE_DIR.removeprefix("vendor/agent-canon/"),
    )
    return (
        template_dir / CANONICAL_README_TEMPLATE,
        template_dir / CANONICAL_PROVENANCE_TEMPLATE,
    )


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    registry_path = Path(args.registry).resolve() if args.registry else repo_root / "experiments" / "registry.toml"
    if registry_path.exists():
        registry = load_registry(registry_path)
    elif args.dry_run:
        registry = {"defaults": {}, "topics": []}
    else:
        raise SystemExit(f"registry is required for topic creation: {registry_path}")

    if find_topic(registry, args.topic) is not None:
        raise SystemExit(f"topic {args.topic!r} already exists in {registry_path}")

    defaults = registry.get("defaults", {})
    if not isinstance(defaults, dict):
        raise SystemExit("registry defaults must be a table")
    template_dir_name = defaults.get("topic_template_dir", AGENT_CANON_TEMPLATE_DIR)
    if not isinstance(template_dir_name, str):
        raise SystemExit("defaults.topic_template_dir must be a string when present")

    template_dir = resolve_topic_template_dir(repo_root, template_dir_name)
    readme_template, provenance_template = resolve_document_templates(repo_root)
    topic_dir = repo_root / "experiments" / args.topic
    required_templates = (template_dir, readme_template, provenance_template)
    missing_templates = [str(path) for path in required_templates if not path.exists()]
    if missing_templates:
        raise SystemExit(f"canonical experiment templates are missing: {', '.join(missing_templates)}")
    if topic_dir.exists():
        if not args.force:
            raise SystemExit(f"topic directory already exists: {topic_dir}")

    if args.dry_run:
        print("dry_run=true")
        print(f"template_dir={template_dir}")
        print(f"canonical_readme_template={readme_template}")
        print(f"canonical_provenance_template={provenance_template}")
        print(f"topic_dir={topic_dir}")
        print(f"registry_path={registry_path}")
        print("planned_topic_files=README.md,provenance.toml,run.py,cases.py,case_model.py,case_execution.py,artifact_schema.py,artifact_io.py,visualization.py,config.yaml,visualize.ipynb,result/.gitkeep")
        return 0

    if topic_dir.exists():
        shutil.rmtree(topic_dir)

    shutil.copytree(template_dir, topic_dir, ignore=shutil.ignore_patterns("README.md"))
    shutil.copyfile(readme_template, topic_dir / "README.md")
    shutil.copyfile(provenance_template, topic_dir / "provenance.toml")
    update_copied_files(topic_dir, args.topic)

    topics = registry.get("topics")
    if not isinstance(topics, list):
        raise SystemExit("registry must contain [[topics]]")
    new_entry: dict[str, object] = {
        "name": args.topic,
        "status": args.status,
        "topic_dir": f"experiments/{args.topic}",
        "topic_readme": f"experiments/{args.topic}/README.md",
        "topic_provenance": f"experiments/{args.topic}/provenance.toml",
        "canonical_entrypoint": f"experiments/{args.topic}/run.py",
        "result_root": f"experiments/{args.topic}/result",
        "report_root": "experiments/report",
        "default_variant": args.default_variant,
        "default_inner_command": (
            f"/usr/bin/python /workspace/experiments/{args.topic}/run.py "
            "--config {config_path}"
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
