#!/usr/bin/env python3
# @dependency-start
# responsibility Validates Dockerfile, runtime pack, and devcontainer configuration.
# upstream design ../../documents/coding-conventions-project.md environment configuration policy
# upstream design ../../agents/skills/environment-maintenance.md environment change workflow
# upstream implementation ../docker_dependency_validator.sh validates Docker dependency contents
# upstream implementation ./container_runtime.py loads runtime pack contracts
# upstream implementation ./render_devcontainer_compose.py renders devcontainer compose
# upstream implementation ./run_container_pack.py builds and smokes runtime packs
# downstream implementation ./run_all_checks.sh runs container configuration validation
# downstream implementation ../../tests/tools/test_container_config.py tests validator
# @dependency-end
"""Validate Dockerfile, runtime pack, and devcontainer configuration."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]


REQUIRED_APT_PACKAGES = (
    "rsync",
    "openssh-client",
    "graphviz",
    "python3-venv",
)
REQUIRED_DOCKERFILE_SNIPPETS = (
    ("requirements.txt", "must-reference-requirements"),
    ("cli.github.com/packages", "must-use-github-cli-apt-repository"),
    ("gh --version", "must-smoke-check-gh"),
    ("docker/register_safe_directories.sh", "must-install-safe-directory-helper"),
)
REQUIRED_REQUIREMENTS = (
    "jupyterlab",
    "notebook",
    "ipykernel",
    "pydeps",
    "snakeviz",
    "pyyaml",
)
REQUIREMENT_RE = re.compile(
    r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?"
    r"(?:\s*(?:==|>=|<=|~=|!=|>|<).+)?$"
)


@dataclass(frozen=True)
class Finding:
    """One container configuration finding."""

    kind: str
    path: str
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding."""
        return f"CONTAINER_CONFIG_FINDING={self.kind}:{self.path}:{self.detail}"


@dataclass(frozen=True)
class PackConfig:
    """One runtime pack config loaded from TOML."""

    path: str
    name: str
    dockerfile: str
    context: str
    image_tag: str
    target: str | None
    workdir: str
    workspace_mount: str


@dataclass(frozen=True)
class ValidationReport:
    """Container configuration validation result."""

    status: str
    findings: tuple[Finding, ...]
    packs: tuple[PackConfig, ...]
    checked: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def as_mapping(value: object) -> Mapping[str, object] | None:
    """Return value as a string-keyed mapping when possible."""
    if not isinstance(value, Mapping):
        return None
    mapping = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in mapping):
        return None
    return cast(Mapping[str, object], mapping)


def as_sequence(value: object) -> Sequence[object] | None:
    """Return value as a sequence, excluding strings."""
    if isinstance(value, str):
        return None
    if isinstance(value, Sequence):
        return cast(Sequence[object], value)
    return None


def require_string(
    table: Mapping[str, object],
    key: str,
    source: str,
    section: str,
    findings: list[Finding],
) -> str:
    """Read one required non-empty string field."""
    value = table.get(key)
    if isinstance(value, str) and value:
        return value
    findings.append(Finding("invalid_manifest", source, f"{section}.{key}-must-be-string"))
    return ""


def require_string_list(
    table: Mapping[str, object],
    key: str,
    source: str,
    section: str,
    findings: list[Finding],
) -> tuple[str, ...]:
    """Read one optional list of strings."""
    value = table.get(key)
    if value is None:
        return ()
    sequence = as_sequence(value)
    if sequence is None or not all(isinstance(item, str) for item in sequence):
        findings.append(
            Finding("invalid_manifest", source, f"{section}.{key}-must-be-string-list")
        )
        return ()
    return tuple(cast(Sequence[str], sequence))


def is_safe_repo_relative(path_text: str) -> bool:
    """Return whether a configured path stays inside the repository."""
    path = Path(path_text)
    return not path.is_absolute() and ".." not in path.parts


def validate_repo_path(
    root: Path,
    source: str,
    field: str,
    value: str,
    findings: list[Finding],
) -> None:
    """Validate that one path is safe and exists under root."""
    if not value:
        return
    if not is_safe_repo_relative(value):
        findings.append(Finding("invalid_manifest", source, f"{field}-escapes-repo:{value}"))
        return
    if not (root / value).exists():
        findings.append(Finding("missing_file", source, f"{field}-missing:{value}"))


def load_pack(root: Path, path: Path) -> tuple[PackConfig | None, list[Finding]]:
    """Load and validate one runtime pack TOML file."""
    source = path.relative_to(root).as_posix()
    findings: list[Finding] = []
    try:
        with path.open("rb") as handle:
            data = cast(Mapping[str, object], tomllib.load(handle))
    except tomllib.TOMLDecodeError as exc:
        return None, [Finding("invalid_manifest", source, f"toml-decode:{exc}")]

    pack = as_mapping(data.get("pack"))
    smoke = as_mapping(data.get("smoke"))
    runtime = as_mapping(data.get("runtime"))
    if pack is None or smoke is None or runtime is None:
        return None, [Finding("invalid_manifest", source, "pack-smoke-runtime-required")]

    name = require_string(pack, "name", source, "pack", findings)
    dockerfile = require_string(pack, "dockerfile", source, "pack", findings)
    context = require_string(pack, "context", source, "pack", findings)
    image_tag = require_string(pack, "image_tag", source, "pack", findings)
    target_value = pack.get("target")
    target = target_value if isinstance(target_value, str) else None
    if target_value is not None and target is None:
        findings.append(Finding("invalid_manifest", source, "pack.target-must-be-string"))

    require_string_list(smoke, "commands", source, "smoke", findings)
    require_string_list(runtime, "env", source, "runtime", findings)
    require_string_list(runtime, "mounts", source, "runtime", findings)
    workdir = runtime.get("workdir", "/workspace")
    workspace_mount = runtime.get("workspace_mount", "/workspace")
    if not isinstance(workdir, str):
        findings.append(Finding("invalid_manifest", source, "runtime.workdir-must-be-string"))
        workdir = ""
    if not isinstance(workspace_mount, str):
        findings.append(
            Finding("invalid_manifest", source, "runtime.workspace_mount-must-be-string")
        )
        workspace_mount = ""

    validate_repo_path(root, source, "dockerfile", dockerfile, findings)
    validate_repo_path(root, source, "context", context, findings)
    if findings:
        return None, findings
    return (
        PackConfig(
            path=source,
            name=name,
            dockerfile=dockerfile,
            context=context,
            image_tag=image_tag,
            target=target,
            workdir=workdir,
            workspace_mount=workspace_mount,
        ),
        [],
    )


def trim_requirement_line(line: str) -> str:
    """Strip comments and surrounding whitespace from one requirement line."""
    return line.split("#", 1)[0].strip()


def validate_requirements(root: Path) -> list[Finding]:
    """Validate docker/requirements.txt."""
    path = root / "docker" / "requirements.txt"
    relative = "docker/requirements.txt"
    if not path.is_file():
        return [Finding("missing_file", relative, "missing")]
    findings: list[Finding] = []
    requirements: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = trim_requirement_line(raw_line)
        if not line:
            continue
        if not REQUIREMENT_RE.fullmatch(line):
            findings.append(
                Finding("dependency_contract_violation", relative, f"invalid-line:{line_number}")
            )
            continue
        name = re.split(r"[\[<>=~!\s]", line, maxsplit=1)[0].lower()
        requirements.add(name)
    for requirement in REQUIRED_REQUIREMENTS:
        if requirement not in requirements:
            findings.append(
                Finding("dependency_contract_violation", relative, f"missing:{requirement}")
            )
    return findings


def validate_dockerfile(root: Path) -> list[Finding]:
    """Validate docker/Dockerfile content-level contracts."""
    path = root / "docker" / "Dockerfile"
    relative = "docker/Dockerfile"
    if not path.is_file():
        return [Finding("missing_file", relative, "missing")]
    text = path.read_text(encoding="utf-8")
    findings: list[Finding] = []
    for package in REQUIRED_APT_PACKAGES:
        if not re.search(rf"(^|[\s\\]){re.escape(package)}([\s\\]|$)", text):
            findings.append(
                Finding("dependency_contract_violation", relative, f"missing-apt:{package}")
            )
    if not re.search(r"pip\s+install\b.*-r\s+\S*requirements\.txt", text, re.DOTALL):
        findings.append(
            Finding("dependency_contract_violation", relative, "missing-pip-requirements-install")
        )
    for snippet, detail in REQUIRED_DOCKERFILE_SNIPPETS:
        if snippet not in text:
            findings.append(Finding("dependency_contract_violation", relative, detail))
    return findings


def load_devcontainer_json(path: Path) -> tuple[Mapping[str, object] | None, list[Finding]]:
    """Load .devcontainer/devcontainer.json."""
    relative = ".devcontainer/devcontainer.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [Finding("invalid_manifest", relative, f"json-decode:{exc}")]
    mapping = as_mapping(data)
    if mapping is None:
        return None, [Finding("invalid_manifest", relative, "must-be-object")]
    return mapping, []


def validate_devcontainer(root: Path, default_pack: PackConfig | None) -> list[Finding]:
    """Validate devcontainer entrypoint and generated compose alignment."""
    devcontainer_dir = root / ".devcontainer"
    if not devcontainer_dir.exists():
        return []
    findings: list[Finding] = []
    json_path = devcontainer_dir / "devcontainer.json"
    if not json_path.is_file():
        return [Finding("missing_file", ".devcontainer/devcontainer.json", "missing")]
    config, json_findings = load_devcontainer_json(json_path)
    findings.extend(json_findings)
    if config is None:
        return findings

    expected_json = {
        "initializeCommand": "bash .devcontainer/generate-runtime-compose.sh",
        "dockerComposeFile": "docker-compose.generated.yml",
        "service": "workspace",
        "postCreateCommand": "bash docker/register_safe_directories.sh /workspace",
    }
    for key, expected in expected_json.items():
        if config.get(key) != expected:
            findings.append(
                Finding("inconsistency", ".devcontainer/devcontainer.json", f"{key}-expected:{expected}")
            )
    if default_pack is not None and config.get("workspaceFolder") != default_pack.workspace_mount:
        findings.append(
            Finding(
                "inconsistency",
                ".devcontainer/devcontainer.json",
                f"workspaceFolder-expected:{default_pack.workspace_mount}",
            )
        )

    script_path = devcontainer_dir / "generate-runtime-compose.sh"
    if not script_path.is_file():
        findings.append(Finding("missing_file", ".devcontainer/generate-runtime-compose.sh", "missing"))
        return findings
    script = script_path.read_text(encoding="utf-8")
    for snippet in (
        "tools/ci/render_devcontainer_compose.py",
        "--pack docker/packs/default.toml",
        "--output .devcontainer/docker-compose.generated.yml",
    ):
        if snippet not in script:
            findings.append(
                Finding("inconsistency", ".devcontainer/generate-runtime-compose.sh", f"missing:{snippet}")
            )

    compose_path = devcontainer_dir / "docker-compose.generated.yml"
    if compose_path.exists() and default_pack is not None:
        compose = compose_path.read_text(encoding="utf-8")
        expected_snippets = (
            "services:",
            "workspace:",
            "context: ..",
            f"dockerfile: {default_pack.dockerfile}",
            f"working_dir: {default_pack.workdir}",
            f"- ..:{default_pack.workspace_mount}:cached",
        )
        for snippet in expected_snippets:
            if snippet not in compose:
                findings.append(
                    Finding("inconsistency", ".devcontainer/docker-compose.generated.yml", f"missing:{snippet}")
                )
    return findings


def validate(root: Path) -> ValidationReport:
    """Run all container configuration checks."""
    root = root.resolve()
    docker_dir = root / "docker"
    devcontainer_dir = root / ".devcontainer"
    if not docker_dir.exists() and not devcontainer_dir.exists():
        return ValidationReport("skip", (), (), ())

    findings: list[Finding] = []
    checked: list[str] = []
    packs: list[PackConfig] = []
    if docker_dir.exists():
        checked.extend(("docker/Dockerfile", "docker/requirements.txt", "docker/packs"))
        findings.extend(validate_dockerfile(root))
        findings.extend(validate_requirements(root))
        packs_dir = docker_dir / "packs"
        if not packs_dir.is_dir():
            findings.append(Finding("missing_file", "docker/packs", "missing"))
        else:
            pack_paths = sorted(packs_dir.glob("*.toml"))
            if not pack_paths:
                findings.append(Finding("missing_file", "docker/packs", "no-pack-files"))
            for pack_path in pack_paths:
                pack, pack_findings = load_pack(root, pack_path)
                findings.extend(pack_findings)
                if pack is not None:
                    packs.append(pack)

    default_pack = next((pack for pack in packs if pack.path == "docker/packs/default.toml"), None)
    if devcontainer_dir.exists():
        checked.append(".devcontainer")
        findings.extend(validate_devcontainer(root, default_pack))

    sorted_findings = tuple(
        sorted(findings, key=lambda finding: (finding.kind, finding.path, finding.detail))
    )
    return ValidationReport(
        "fail" if sorted_findings else "pass",
        sorted_findings,
        tuple(packs),
        tuple(checked),
    )


def render_json(report: ValidationReport) -> str:
    """Render JSON output."""
    return json.dumps(
        {
            "status": report.status,
            "findings": [asdict(finding) for finding in report.findings],
            "packs": [asdict(pack) for pack in report.packs],
            "checked": list(report.checked),
        },
        indent=2,
        sort_keys=True,
    )


def render_text(report: ValidationReport) -> None:
    """Render text output."""
    for finding in report.findings:
        print(finding.render())
    for pack in report.packs:
        print(
            "CONTAINER_CONFIG_PACK="
            f"{pack.name}\tpath={pack.path}\tdockerfile={pack.dockerfile}\t"
            f"context={pack.context}\tworkdir={pack.workdir}\t"
            f"workspace_mount={pack.workspace_mount}"
        )
    print(f"CONTAINER_CONFIG_CHECKED={','.join(report.checked) if report.checked else 'none'}")
    print(f"CONTAINER_CONFIG_FINDINGS={len(report.findings)}")
    print(f"CONTAINER_CONFIG={report.status}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the validator."""
    args = build_parser().parse_args(argv)
    report = validate(Path(args.root))
    if args.format == "json":
        print(render_json(report))
    else:
        render_text(report)
    if report.status == "fail":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
