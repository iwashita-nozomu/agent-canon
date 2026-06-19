#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates Dockerfile, runtime pack, devcontainer, and VS Code workspace configuration.
# upstream design ../../documents/coding-conventions-project.md environment configuration policy
# upstream design ../../documents/shared-runtime-surfaces.toml machine-readable shared runtime surface ownership
# upstream design ../../documents/github-first-module-and-devcontainer-policy.md Dockerfile/devcontainer ownership boundary
# upstream design ../../documents/rust-agent-tool-migration.md Rust toolchain devcontainer boundary
# upstream design ../../documents/local-llm-responsibility-analysis.md local LLM devcontainer boundary
# upstream design ../../agents/skills/academic-writing.md Academic Writing TeX tooling boundary
# upstream design ../../documents/tools/lean_proof_env.md Lean proof environment toolchain boundary
# upstream design ../../agents/skills/environment-maintenance.md environment change workflow
# upstream implementation ../agent_tools/surface_manifest.py parses shared runtime surface manifests
# upstream implementation ../docker_dependency_validator.sh validates Docker dependency contents
# upstream implementation ./container_runtime.py loads runtime pack contracts
# upstream implementation ./run_container_pack.py builds and smokes runtime packs
# downstream implementation ./run_all_checks.sh runs container configuration validation
# downstream implementation ../../tests/tools/test_container_config.py tests validator
# @dependency-end
"""Validate Dockerfile, runtime pack, devcontainer, and VS Code workspace configuration."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

AGENT_TOOLS_DIR = Path(__file__).resolve().parents[1] / "agent_tools"
if str(AGENT_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_TOOLS_DIR))

from surface_manifest import SurfaceEntry, SurfaceManifest, load_manifest, target_for_entry  # noqa: E402,I001

REQUIRED_APT_PACKAGES = (
    "rsync",
    "openssh-client",
    "graphviz",
    "python3.11",
    "python3.11-dev",
    "python3.11-venv",
)
REQUIRED_DOCKERFILE_SNIPPETS = (
    ("docker/register_safe_directories.sh", "must-install-safe-directory-helper"),
)
FORBIDDEN_DOCKERFILE_PATTERNS = (
    (re.compile(r"cli\.github\.com/packages"), "dockerfile-must-not-configure-github-cli"),
    (re.compile(r"(^|[\s\\])gh([\s\\]|$)"), "dockerfile-must-not-install-gh"),
    (re.compile(r"gh\s+--version"), "dockerfile-must-not-smoke-check-gh"),
    (re.compile(r"@openai/codex"), "dockerfile-must-not-install-codex-cli"),
    (re.compile(r"codex\s+--version"), "dockerfile-must-not-smoke-check-codex"),
    (re.compile(r"\brustup\b"), "dockerfile-must-not-install-rustup"),
    (re.compile(r"\bcargo\s+(build|install|test|clippy|fmt)\b"), "dockerfile-must-not-run-cargo"),
    (re.compile(r"\brustc\s+--version\b"), "dockerfile-must-not-smoke-check-rustc"),
    (re.compile(r"elan-init\.sh"), "dockerfile-must-not-install-lean-via-elan"),
    (
        re.compile(r"leanprover/elan/releases/download"),
        "dockerfile-must-not-install-elan-release",
    ),
    (re.compile(r"\belan\s+(toolchain|default|self|update)\b"), "dockerfile-must-not-run-elan"),
    (re.compile(r"\blean\s+--version\b"), "dockerfile-must-not-smoke-check-lean"),
    (re.compile(r"\blake\s+(build|update|env)\b"), "dockerfile-must-not-run-lake"),
    (
        re.compile(r"npm\s+install\s+-g\s+@openai/codex"),
        "dockerfile-must-not-install-codex-via-npm",
    ),
)
REQUIRED_POST_CREATE_SNIPPETS = (
    "run_as_root",
    "docker/register_safe_directories.sh",
    "docker/install_python_dependencies.sh",
    'git config --global --add safe.directory "$workspace"',
    "repo-local Python dependency installer absent",
    "cli.github.com/packages",
    "apt_install gh",
    "codex --version >/dev/null",
    "npm install -g @openai/codex",
    "rustup toolchain install",
    "rustfmt",
    "clippy",
    "rust-analyzer",
    "cargo build --release",
    "AGENT_CANON_TOOLS_HOME",
    "${tools_home}/agent-canon/bin/agent-canon",
    "/usr/local/bin/agent-canon",
    "install_llama_cpp",
    "tools/install_llama_cpp.sh",
    "ggml-org/SmolLM3-3B-GGUF:Q4_K_M",
    "${tools_home}/bin/llama-cli",
    "install_secret_scanners",
    "gitleaks",
    "trufflehog",
    "detect-secrets",
    "apt_install jq",
    "jq --version",
    "install_tex_tooling",
    "AGENT_CANON_LEAN_TOOLCHAIN",
    "leanprover/lean4:v4.30.0",
    "AGENT_CANON_ELAN_VERSION",
    "v4.2.3",
    "AGENT_CANON_ELAN_X86_64_SHA256",
    "AGENT_CANON_ELAN_AARCH64_SHA256",
    "install_lean_toolchain",
    "leanprover/elan/releases/download",
    "elan-x86_64-unknown-linux-gnu.tar.gz",
    "elan-aarch64-unknown-linux-gnu.tar.gz",
    "sha256sum -c -",
    "elan-init",
    "elan toolchain install",
    "elan default",
    "for tool in elan lean lake",
    "/usr/local/bin/${tool}",
    "elan --version",
    "lean --version",
    "lake --version",
    "latexmk",
    "texlive-latex-recommended",
    "texlive-latex-extra",
    "texlive-fonts-recommended",
    "texlive-pictures",
    "texlive-xetex",
    "texlive-extra-utils",
    "dvisvgm",
    "ghostscript",
    "poppler-utils",
    "latexmk --version",
    "pdflatex --version",
    "xelatex --version",
    "dvisvgm --version",
    "pdfcrop --version",
    "gh --version",
    "codex --version",
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
) -> tuple[str, Finding | None]:
    """Read one required non-empty string field."""
    value = table.get(key)
    if isinstance(value, str) and value:
        return value, None
    return "", Finding("invalid_manifest", source, f"{section}.{key}-must-be-string")


def require_string_list(
    table: Mapping[str, object],
    key: str,
    source: str,
    section: str,
) -> tuple[tuple[str, ...], Finding | None]:
    """Read one optional list of strings."""
    value = table.get(key)
    if value is None:
        return (), None
    sequence = as_sequence(value)
    if sequence is None or not all(isinstance(item, str) for item in sequence):
        return (), Finding("invalid_manifest", source, f"{section}.{key}-must-be-string-list")
    return tuple(cast(Sequence[str], sequence)), None


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

    required_pack_fields = {
        "name": "",
        "dockerfile": "",
        "context": "",
        "image_tag": "",
    }
    for field_name in required_pack_fields:
        value, finding = require_string(pack, field_name, source, "pack")
        required_pack_fields[field_name] = value
        if finding is not None:
            findings.append(finding)
    name = required_pack_fields["name"]
    dockerfile = required_pack_fields["dockerfile"]
    context = required_pack_fields["context"]
    image_tag = required_pack_fields["image_tag"]
    target_value = pack.get("target")
    target = target_value if isinstance(target_value, str) else None
    if target_value is not None and target is None:
        findings.append(Finding("invalid_manifest", source, "pack.target-must-be-string"))

    for table, key, section in (
        (smoke, "commands", "smoke"),
        (runtime, "env", "runtime"),
        (runtime, "mounts", "runtime"),
    ):
        _, finding = require_string_list(table, key, source, section)
        if finding is not None:
            findings.append(finding)
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
    if re.search(r"pip\s+install\b.*-r\s+\S*requirements\.txt", text, re.DOTALL):
        findings.append(
            Finding(
                "dependency_contract_violation",
                relative,
                "docker-build-must-not-install-python-requirements",
            )
        )
    if "COPY docker/requirements.txt" in text or "requirements.txt /tmp" in text:
        findings.append(
            Finding(
                "dependency_contract_violation",
                relative,
                "docker-build-must-not-copy-python-requirements",
            )
        )
    for snippet, detail in REQUIRED_DOCKERFILE_SNIPPETS:
        if snippet not in text:
            findings.append(Finding("dependency_contract_violation", relative, detail))
    for pattern, detail in FORBIDDEN_DOCKERFILE_PATTERNS:
        if pattern.search(text):
            findings.append(Finding("dependency_contract_violation", relative, detail))
    return findings


def validate_dockerignore(root: Path) -> list[Finding]:
    """Validate Docker build context exclusions."""
    path = root / ".dockerignore"
    relative = ".dockerignore"
    if not path.is_file():
        return [Finding("missing_file", relative, "missing")]
    text = path.read_text(encoding="utf-8")
    findings: list[Finding] = []
    for ignored_path in (".git", ".state", "*.gguf", "*.safetensors", "pytorch_model*.bin", "model-*.bin", ".cache/huggingface", ".cache/llama.cpp", "vendor/local-llm-server/llama-cpp/models", "vendor/local-llm-server/llama-cpp/cache", "vendor/local-llm-server/llama-cpp/runtime", "vendor/agent-canon"):
        if not re.search(rf"(^|\n){re.escape(ignored_path)}(\n|$)", text):
            findings.append(
                Finding("dependency_contract_violation", relative, f"missing-ignore:{ignored_path}")
            )
    return findings


def validate_post_create(root: Path) -> list[Finding]:
    """Validate devcontainer post-create setup centralizes Python dependency installs."""
    path = root / ".devcontainer" / "post-create.sh"
    relative = ".devcontainer/post-create.sh"
    if not path.is_file():
        return [Finding("missing_file", relative, "missing")]
    text = path.read_text(encoding="utf-8")
    findings: list[Finding] = []
    for snippet in REQUIRED_POST_CREATE_SNIPPETS:
        if snippet not in text:
            findings.append(Finding("dependency_contract_violation", relative, f"missing:{snippet}"))
    return findings


def validate_python_dependency_installer(root: Path) -> list[Finding]:
    """Validate the central Python dependency installer script."""
    path = root / "docker" / "install_python_dependencies.sh"
    relative = "docker/install_python_dependencies.sh"
    if not path.is_file():
        return [Finding("missing_file", relative, "missing")]
    text = path.read_text(encoding="utf-8")
    findings: list[Finding] = []
    for snippet in (
        "docker/requirements.txt",
        "python3 -m pip install --upgrade pip",
        'python3 -m pip install --no-cache-dir -r "$requirements"',
        "sha256sum",
        "python3 -m pip check",
    ):
        if snippet not in text:
            findings.append(Finding("dependency_contract_violation", relative, f"missing:{snippet}"))
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


def validate_devcontainer_json(config: Mapping[str, object]) -> list[Finding]:
    """Validate required devcontainer JSON fields."""
    findings: list[Finding] = []
    expected_json = {
        "name": "${localWorkspaceFolderBasename}-devcontainer",
        "initializeCommand": "bash .devcontainer/generate-runtime-compose.sh",
        "dockerComposeFile": "docker-compose.generated.yml",
        "service": "workspace",
        "postCreateCommand": "bash .devcontainer/post-create.sh /workspace",
        "postAttachCommand": "bash .devcontainer/post-attach.sh",
    }
    for key, expected in expected_json.items():
        if config.get(key) != expected:
            findings.append(
                Finding("inconsistency", ".devcontainer/devcontainer.json", f"{key}-expected:{expected}")
            )
    return findings


def validate_devcontainer_workspace(config: Mapping[str, object], pack: PackConfig) -> list[Finding]:
    """Validate devcontainer workspace mount alignment with one runtime pack."""
    if config.get("workspaceFolder") == pack.workspace_mount:
        return []
    return [
        Finding(
            "inconsistency",
            ".devcontainer/devcontainer.json",
            f"workspaceFolder-expected:{pack.workspace_mount}",
        )
    ]


def validate_generate_runtime_compose_script(devcontainer_dir: Path) -> list[Finding]:
    """Validate the shared compose generation script."""
    script_path = devcontainer_dir / "generate-runtime-compose.sh"
    if not script_path.is_file():
        return [Finding("missing_file", ".devcontainer/generate-runtime-compose.sh", "missing")]
    script = script_path.read_text(encoding="utf-8")
    findings: list[Finding] = []
    for snippet in (
        "docker/packs/default.toml",
        ".devcontainer/docker-compose.generated.yml",
        "DEVCONTAINER_PROJECT_NAME",
        "default_project_name",
        "agent-canon-source-only",
        "mcr.microsoft.com/devcontainers/base:ubuntu-22.04",
        "AGENT_CANON_SECRET_DIR",
        "AGENT_CANON_SECRET_MOUNT",
        "AGENT_CANON_SECRET_DIR_MODE",
        "vendor/agent-canon",
    ):
        findings.extend(validate_generate_runtime_compose_snippet(script, snippet))
    for snippet in ("DEVCONTAINER_SUBNET", "DEVCONTAINER_GATEWAY", "ipam:", "subnet:", "gateway:"):
        if snippet in script:
            findings.append(
                Finding("inconsistency", ".devcontainer/generate-runtime-compose.sh", f"forbidden:{snippet}")
            )
    return findings


def validate_generate_runtime_compose_snippet(script: str, snippet: str) -> list[Finding]:
    """Validate one required or forbidden compose-generation snippet."""
    path = ".devcontainer/generate-runtime-compose.sh"
    if snippet == "vendor/agent-canon":
        if snippet in script:
            return [Finding("inconsistency", path, f"forbidden:{snippet}")]
        return []
    if snippet not in script:
        return [Finding("inconsistency", path, f"missing:{snippet}")]
    return []


def validate_generated_compose(devcontainer_dir: Path, pack: PackConfig) -> list[Finding]:
    """Validate the generated Docker Compose file when present."""
    compose_path = devcontainer_dir / "docker-compose.generated.yml"
    if not compose_path.exists():
        return []
    compose = compose_path.read_text(encoding="utf-8")
    expected_snippets = (
        "name:",
        "services:",
        "workspace:",
        "context: ..",
        f"dockerfile: {pack.dockerfile}",
        f"working_dir: {pack.workdir}",
        f"- ..:{pack.workspace_mount}:cached",
    )
    findings = [
        Finding("inconsistency", ".devcontainer/docker-compose.generated.yml", f"missing:{snippet}")
        for snippet in expected_snippets
        if snippet not in compose
    ]
    for snippet in ("ipam:", "subnet:", "gateway:"):
        if snippet in compose:
            findings.append(
                Finding("inconsistency", ".devcontainer/docker-compose.generated.yml", f"forbidden:{snippet}")
            )
    return findings


def validate_devcontainer(root: Path) -> list[Finding]:
    """Validate shared devcontainer entrypoint configuration."""
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

    findings.extend(validate_devcontainer_json(config))
    post_attach = devcontainer_dir / "post-attach.sh"
    if not post_attach.is_file():
        findings.append(Finding("missing_file", ".devcontainer/post-attach.sh", "missing"))
    findings.extend(validate_generate_runtime_compose_script(devcontainer_dir))
    findings.extend(validate_post_create(root))
    return findings


def validate_devcontainer_pack_alignment(root: Path, pack: PackConfig) -> list[Finding]:
    """Validate devcontainer paths that depend on the repo-local runtime pack."""
    devcontainer_dir = root / ".devcontainer"
    json_path = devcontainer_dir / "devcontainer.json"
    if not json_path.is_file():
        return []
    config, json_findings = load_devcontainer_json(json_path)
    if config is None:
        return json_findings
    return [
        *json_findings,
        *validate_devcontainer_workspace(config, pack),
        *validate_generated_compose(devcontainer_dir, pack),
    ]


def has_vscode_contract(root: Path) -> bool:
    """Return whether this root declares an AgentCanon VS Code surface."""
    vscode_dir = root / ".vscode"
    vendor_manifest = root / "vendor" / "agent-canon" / "documents" / "shared-runtime-surfaces.toml"
    return (
        (root / "documents" / "shared-runtime-surfaces.toml").is_file()
        or vendor_manifest.is_file()
        or vscode_dir.exists()
        or vscode_dir.is_symlink()
    )


def load_shared_surface_manifest(root: Path) -> tuple[SurfaceManifest | None, list[Finding]]:
    """Load the shared runtime surface manifest through its canonical parser."""
    try:
        return load_manifest(root, "vendor/agent-canon", "documents/shared-runtime-surfaces.toml"), []
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        return None, [
            Finding(
                "invalid_manifest",
                "documents/shared-runtime-surfaces.toml",
                f"load-failed:{exc}",
            )
        ]


def load_vscode_surface(root: Path) -> tuple[SurfaceEntry | None, SurfaceManifest | None, list[Finding]]:
    """Load the .vscode entry from the shared runtime surface manifest."""
    manifest, findings = load_shared_surface_manifest(root)
    if manifest is None:
        return None, None, findings
    entry = next((candidate for candidate in manifest.entries if candidate.path == ".vscode"), None)
    if entry is None:
        return (
            None,
            manifest,
            [
                Finding(
                    "dependency_contract_violation",
                    "documents/shared-runtime-surfaces.toml",
                    "missing-surface:.vscode",
                )
            ],
        )
    return entry, manifest, []


def validate_vscode_manifest(entry: SurfaceEntry) -> list[Finding]:
    """Validate the .vscode manifest entry keeps AgentCanon symlink ownership."""
    findings: list[Finding] = []
    expected = {
        "mode": "symlink",
        "owner": "agent-canon",
        "surface_class": "runtime_surface",
    }
    actual = {
        "mode": entry.mode,
        "owner": entry.owner,
        "surface_class": entry.surface_class,
    }
    for field, expected_value in expected.items():
        if actual[field] != expected_value:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    "documents/shared-runtime-surfaces.toml",
                    f".vscode-{field}-expected:{expected_value}",
                )
            )
    return findings


def validate_vscode(root: Path) -> list[Finding]:
    """Validate shared VS Code workspace surface ownership."""
    entry, manifest, findings = load_vscode_surface(root)
    if entry is None or manifest is None:
        return findings
    findings.extend(validate_vscode_manifest(entry))
    source_checkout = not (root / "vendor" / "agent-canon" / "documents" / "shared-runtime-surfaces.toml").is_file()
    source = entry.source_or_default()
    source_relative = source if source_checkout else f"{manifest.prefix}/{source}"
    source_dir = root / source_relative
    if not source_dir.is_dir():
        findings.append(Finding("missing_file", source_relative, "missing"))
    if source_checkout:
        return findings
    vscode_dir = root / ".vscode"
    expected_target = target_for_entry(root, manifest.prefix, entry)
    if not vscode_dir.is_symlink():
        findings.append(
            Finding("inconsistency", ".vscode", f"expected-shared-view:{expected_target}")
        )
        return findings
    target = vscode_dir.readlink()
    target_path = target if target.is_absolute() else (vscode_dir.parent / target)
    try:
        target_matches = target_path.resolve(strict=True) == source_dir.resolve(strict=True)
    except FileNotFoundError:
        target_matches = False
    if target.as_posix() != expected_target and not target_matches:
        findings.append(
            Finding(
                "inconsistency",
                ".vscode",
                f"unexpected-shared-view-target:{target.as_posix()}",
            )
        )
    return findings

def validate(root: Path) -> ValidationReport:
    """Run all container configuration checks."""
    root = root.resolve()
    docker_dir = root / "docker"
    devcontainer_dir = root / ".devcontainer"
    vscode_configured = has_vscode_contract(root)
    if not docker_dir.exists() and not devcontainer_dir.exists() and not vscode_configured:
        return ValidationReport("skip", (), (), ())

    findings: list[Finding] = []
    checked: list[str] = []
    packs: list[PackConfig] = []
    if docker_dir.exists():
        checked.extend((".dockerignore", "docker/Dockerfile", "docker/requirements.txt", "docker/packs"))
        findings.extend(validate_dockerignore(root))
        findings.extend(validate_dockerfile(root))
        findings.extend(validate_python_dependency_installer(root))
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
        findings.extend(validate_devcontainer(root))
        if default_pack is not None:
            findings.extend(validate_devcontainer_pack_alignment(root, default_pack))
    if vscode_configured:
        checked.append(".vscode")
        findings.extend(validate_vscode(root))

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
