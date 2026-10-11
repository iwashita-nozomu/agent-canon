#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides create experiment topic experiment workflow tooling.
# upstream design ../../../README.md shared automation index
# upstream design ../../../documents/design/experiment-topic-template.md canonical topic template contract.
# downstream implementation ../../../templates/experiments/_template/run.py runnable topic scaffold and orchestration boundary.
# downstream implementation ../../../templates/experiments/_template/cases.py case models, registry, worker, and failure classification.
# downstream implementation ../../../templates/experiments/_template/visualization.py visualization status and renderer extension.
# downstream implementation ../../../templates/experiments/_cpp_template C++-first package and profile-selected CMake surface.
# downstream implementation ../../agent/templates/template_bundle.py exports both canonical experiment packages.
# upstream design ../../../documents/experiments/experiment-registry.md project experiment registry contract.
# @dependency-end

"""Create one experiment topic from the template and register it."""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

# A direct filesystem invocation places ``tools/experiments/lifecycle`` on
# ``sys.path``; add the repository root so the same public imports work as
# ``python -m``.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.experiments.lifecycle.experiment_identity import validate_segment
from tools.experiments.registry.registry_lib import find_topic, load_registry, write_registry

AGENT_CANON_TEMPLATE_DIR = "vendor/agent-canon/templates/experiments/_template"
CPP_TEMPLATE_DIR = "templates/experiments/_cpp_template"


def repo_root_from_script() -> Path:
    """Return the repository root from this script location."""
    return Path(__file__).absolute().parents[3]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Create experiments/<topic>/ from the template and append one registry entry."
    )
    parser.add_argument("topic", help="New experiment topic name.")
    parser.add_argument(
        "--repo-root",
        default=os.environ.get(
            "AGENT_CANON_OUTPUT_ROOT", str(repo_root_from_script())
        ),
        help="Parent repository root. Defaults to the active target or this script's repository.",
    )
    parser.add_argument(
        "--template-profile",
        choices=("python", "cpp"),
        default="python",
        help=(
            "Topic package to materialize. The existing Python scaffold remains "
            "the default."
        ),
    )
    parser.add_argument(
        "--cmake-profile",
        choices=("root-aggregate", "consumer-local"),
        help="Required for --template-profile cpp; supplied by the consumer's CMake owner.",
    )
    parser.add_argument(
        "--multi-case",
        action="store_true",
        help=(
            "Materialize the optional C++ case input adapter for a selected "
            "multi-case topic."
        ),
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
        help=(
            "Replace an unregistered existing topic directory after staging the "
            "new package and registry."
        ),
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


def update_cpp_topic(
    topic_dir: Path, topic_name: str, cmake_profile: str, multi_case: bool
) -> None:
    """Materialize only the selected CMake entry surface in the copied package."""
    for path in sorted(topic_dir.rglob("*")):
        if path.is_file():
            replace_topic_tokens(path, topic_name)
            text = path.read_text(encoding="utf-8")
            text = text.replace("<cmake-profile>", cmake_profile)
            text = text.replace("<case-mode>", "multi" if multi_case else "single")
            path.write_text(text, encoding="utf-8")

    source_path = topic_dir / "topic.cpp"
    source_path.rename(topic_dir / f"{topic_name}.cpp")

    cmake_dir = topic_dir / "cmake"
    profile_files = {
        "consumer-local": ("consumer-local.CMakeLists.txt", "CMakeLists.txt"),
        "root-aggregate": (
            "root-aggregate.registration.cmake",
            "cmake-registration.cmake",
        ),
    }
    source_name, output_name = profile_files[cmake_profile]
    (cmake_dir / source_name).rename(topic_dir / output_name)
    shutil.rmtree(cmake_dir)

    optional_dir = topic_dir / "optional"
    if multi_case:
        (optional_dir / "cases.py").rename(topic_dir / "cases.py")
    shutil.rmtree(optional_dir)


def publish_topic_and_registry(
    *,
    topic_dir: Path,
    template_dir: Path,
    topic_name: str,
    registry_path: Path,
    registry: dict[str, object],
    template_profile: str,
    cmake_profile: str | None,
    multi_case: bool,
    force: bool,
) -> None:
    """Stage the new package and registry before publishing either path."""
    topic_parent = topic_dir.parent
    registry_parent = registry_path.parent
    topic_stage_root = Path(
        tempfile.mkdtemp(prefix=f".{topic_name}.stage-", dir=topic_parent)
    )
    registry_stage_root: Path | None = None
    backup_root: Path | None = None
    backup_topic: Path | None = None
    topic_published = False
    transaction_committed = False
    published_identity: tuple[int, int] | None = None

    try:
        staged_topic = topic_stage_root / topic_name
        shutil.copytree(template_dir, staged_topic)
        if template_profile == "cpp":
            if cmake_profile is None:
                raise ValueError("C++ template materialization requires a CMake profile")
            update_cpp_topic(staged_topic, topic_name, cmake_profile, multi_case)
        else:
            update_copied_files(staged_topic, topic_name)

        registry_stage_root = Path(
            tempfile.mkdtemp(
                prefix=f".{registry_path.name}.stage-", dir=registry_parent
            )
        )
        staged_registry = registry_stage_root / registry_path.name
        write_registry(staged_registry, registry)
        if registry_path.exists():
            staged_registry.chmod(stat.S_IMODE(registry_path.stat().st_mode))

        if topic_dir.is_symlink():
            raise FileExistsError(f"topic directory is a symlink: {topic_dir}")
        if topic_dir.exists():
            if not force:
                raise FileExistsError(f"topic directory already exists: {topic_dir}")
            if not topic_dir.is_dir():
                raise FileExistsError(f"topic path is not a directory: {topic_dir}")
            backup_root = Path(
                tempfile.mkdtemp(prefix=f".{topic_name}.replaced-", dir=topic_parent)
            )
            backup_topic = backup_root / topic_name
            os.replace(topic_dir, backup_topic)

        os.rename(staged_topic, topic_dir)
        topic_published = True
        topic_stage_root.rmdir()
        topic_stat = topic_dir.stat()
        published_identity = (topic_stat.st_dev, topic_stat.st_ino)
        os.replace(staged_registry, registry_path)
        transaction_committed = True
    except Exception as error:
        rollback_error: OSError | None = None
        if topic_published and published_identity is not None and topic_dir.exists():
            topic_stat = topic_dir.stat()
            if (topic_stat.st_dev, topic_stat.st_ino) == published_identity:
                try:
                    shutil.rmtree(topic_dir)
                except OSError as cleanup_error:
                    rollback_error = cleanup_error
        if backup_topic is not None and backup_topic.exists():
            if topic_dir.exists() or topic_dir.is_symlink():
                rollback_error = rollback_error or FileExistsError(
                    f"cannot restore prior topic over existing path: {topic_dir}"
                )
            else:
                try:
                    os.replace(backup_topic, topic_dir)
                except OSError as restore_error:
                    rollback_error = rollback_error or restore_error
        if rollback_error is not None:
            backup_note = (
                f"; prior topic remains at {backup_topic}"
                if backup_topic is not None and backup_topic.exists()
                else ""
            )
            raise RuntimeError(
                f"publication failed and rollback was incomplete{backup_note}: "
                f"{rollback_error}"
            ) from error
        raise
    finally:
        if topic_stage_root.exists():
            try:
                shutil.rmtree(topic_stage_root)
            except OSError as cleanup_error:
                print(
                    f"warning: topic staging path remains at {topic_stage_root}: "
                    f"{cleanup_error}",
                    file=sys.stderr,
                )
        if registry_stage_root is not None and registry_stage_root.exists():
            try:
                shutil.rmtree(registry_stage_root)
            except OSError as cleanup_error:
                print(
                    f"warning: registry staging path remains at {registry_stage_root}: "
                    f"{cleanup_error}",
                    file=sys.stderr,
                )
        if backup_root is not None and backup_root.exists():
            if transaction_committed:
                try:
                    shutil.rmtree(backup_root)
                except OSError as cleanup_error:
                    print(
                        f"warning: replaced topic backup remains at {backup_root}: "
                        f"{cleanup_error}",
                        file=sys.stderr,
                    )
            elif not backup_root.joinpath(topic_name).exists():
                backup_root.rmdir()


def resolve_canon_path(repo_root: Path, logical_path: str) -> Path:
    """Resolve a canonical AgentCanon path in parent, standalone, or source checkouts."""
    source_root = Path(__file__).resolve().parents[3]
    vendor_root = repo_root / "vendor" / "agent-canon"
    candidates = (
        [
            vendor_root / logical_path,
            repo_root / logical_path,
            source_root / logical_path,
        ]
        if vendor_root.exists()
        else [repo_root / logical_path, source_root / logical_path]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def resolve_topic_template_dir(repo_root: Path, configured_path: str) -> Path:
    """Resolve a canonical topic scaffold without changing its owner."""
    configured = resolve_canon_path(
        repo_root, configured_path.removeprefix("vendor/agent-canon/")
    )
    if configured.is_dir():
        return configured
    fallback = resolve_canon_path(repo_root, "templates/experiments/_template")
    return fallback


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    try:
        topic_name = validate_segment(args.topic, "topic")
        default_variant = validate_segment(args.default_variant, "default_variant")
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    repo_root = Path(args.repo_root).resolve()
    active_target_text = os.environ.get("AGENT_CANON_OUTPUT_ROOT")
    if active_target_text:
        active_target = Path(active_target_text).resolve()
        if repo_root != active_target:
            raise SystemExit("--repo-root must match the active explicit target")
    registry_path = (
        Path(os.path.abspath(args.registry))
        if args.registry
        else repo_root / "experiments" / "registry.toml"
    )
    if active_target_text and registry_path != (
        active_target / "experiments" / "registry.toml"
    ):
        raise SystemExit(
            "--registry must name the active target's experiments/registry.toml"
        )
    experiments_root = repo_root / "experiments"
    if experiments_root.is_symlink():
        raise SystemExit(f"experiments directory is a symlink: {experiments_root}")
    if registry_path.is_symlink():
        raise SystemExit(f"registry path is a symlink: {registry_path}")
    if registry_path.exists():
        registry = load_registry(registry_path)
    elif args.dry_run:
        registry = {"defaults": {}, "topics": []}
    else:
        raise SystemExit(f"registry is required for topic creation: {registry_path}")

    if find_topic(registry, topic_name) is not None:
        raise SystemExit(f"topic {topic_name!r} already exists in {registry_path}")

    defaults = registry.get("defaults", {})
    if not isinstance(defaults, dict):
        raise SystemExit("registry defaults must be a table")
    if args.template_profile == "cpp":
        if args.cmake_profile is None:
            raise SystemExit("--cmake-profile is required with --template-profile cpp")
        if args.status != "draft":
            raise SystemExit("C++ starter topics must remain draft until native work is implemented")
        template_dir = resolve_topic_template_dir(repo_root, CPP_TEMPLATE_DIR)
    else:
        if args.cmake_profile is not None:
            raise SystemExit("--cmake-profile is only valid with --template-profile cpp")
        if args.multi_case:
            raise SystemExit("--multi-case is only valid with --template-profile cpp")
        template_dir_name = defaults.get(
            "topic_template_dir", AGENT_CANON_TEMPLATE_DIR
        )
        if not isinstance(template_dir_name, str):
            raise SystemExit("defaults.topic_template_dir must be a string when present")
        template_dir = resolve_topic_template_dir(repo_root, template_dir_name)
    topic_dir = experiments_root / topic_name
    required_templates = [
        template_dir,
        template_dir / "README.md",
        template_dir / "provenance.toml",
    ]
    if args.template_profile == "cpp":
        cmake_source = (
            "consumer-local.CMakeLists.txt"
            if args.cmake_profile == "consumer-local"
            else "root-aggregate.registration.cmake"
        )
        required_templates.extend(
            (
                template_dir / "config.yaml",
                template_dir / "topic.cpp",
                template_dir / "run.py",
                template_dir / "visualization.py",
                template_dir / "cmake" / cmake_source,
                template_dir / "report" / ".gitkeep",
                template_dir / "result" / ".gitkeep",
            )
        )
        if args.multi_case:
            required_templates.append(template_dir / "optional" / "cases.py")
    missing_templates = [str(path) for path in required_templates if not path.exists()]
    if missing_templates:
        raise SystemExit(
            f"canonical experiment templates are missing: {', '.join(missing_templates)}"
        )
    if topic_dir.exists() or topic_dir.is_symlink():
        if topic_dir.is_symlink():
            raise SystemExit(f"topic directory is a symlink: {topic_dir}")
        if not args.force:
            raise SystemExit(f"topic directory already exists: {topic_dir}")
        if not topic_dir.is_dir():
            raise SystemExit(f"topic path is not a directory: {topic_dir}")

    if args.dry_run:
        print("dry_run=true")
        print(f"template_dir={template_dir}")
        print(f"topic_dir={topic_dir}")
        print(f"registry_path={registry_path}")
        if topic_dir.exists():
            print(f"force_replaces_existing_topic={topic_dir}")
        if args.template_profile == "cpp":
            cmake_file = (
                "CMakeLists.txt"
                if args.cmake_profile == "consumer-local"
                else "cmake-registration.cmake"
            )
            files = (
                "README.md,provenance.toml,config.yaml,<topic>.cpp,run.py,"
                f"visualization.py,{cmake_file},report/.gitkeep,result/.gitkeep"
            )
            if args.multi_case:
                files = files.replace("run.py,", "run.py,cases.py,")
        else:
            files = (
                "README.md,provenance.toml,run.py,cases.py,visualization.py,"
                "config.yaml,report/.gitkeep,result/.gitkeep"
            )
        if args.template_profile == "cpp":
            print("template_profile=cpp")
            print(f"cmake_profile={args.cmake_profile}")
        print(f"planned_topic_files={files}")
        return 0

    topics = registry.get("topics")
    if not isinstance(topics, list):
        raise SystemExit("registry must contain [[topics]]")
    new_entry: dict[str, object] = {
        "name": topic_name,
        "status": args.status,
        "topic_dir": f"experiments/{topic_name}",
        "topic_readme": f"experiments/{topic_name}/README.md",
        "topic_provenance": f"experiments/{topic_name}/provenance.toml",
        "canonical_entrypoint": f"experiments/{topic_name}/run.py",
        "result_root": f"experiments/{topic_name}/result",
        "report_root": f"experiments/{topic_name}/report",
        "default_variant": default_variant,
        "default_inner_command": (
            f"/usr/bin/python /workspace/experiments/{topic_name}/run.py "
            "--config {config_path}"
            + (
                " --multi-case"
                if args.template_profile == "cpp" and args.multi_case
                else ""
            )
        ),
    }
    if args.primary_note:
        new_entry["primary_note"] = args.primary_note
    if args.active_branch:
        new_entry["active_branch"] = args.active_branch
    topics.append(new_entry)
    try:
        publish_topic_and_registry(
            topic_dir=topic_dir,
            template_dir=template_dir,
            topic_name=topic_name,
            registry_path=registry_path,
            registry=registry,
            template_profile=args.template_profile,
            cmake_profile=args.cmake_profile,
            multi_case=args.multi_case,
            force=args.force,
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    except (OSError, ValueError, shutil.Error) as exc:
        raise SystemExit(f"topic and registry were not published: {exc}") from exc

    print(f"topic_dir={topic_dir}")
    print(f"registry_path={registry_path}")
    print(f"topic_name={topic_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
