#!/usr/bin/env python3
"""Apply the one-time template Agent-definition boundary fix for Issue #781."""

from __future__ import annotations

import ast
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def remove_path(relative: str) -> None:
    path = ROOT / relative
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


REMOVED_SURFACES = (
    "documents/contracts/static-seed-allowlist.toml",
    "documents/contracts/static-seed-export.md",
    "documents/tools/export_static_seed.md",
    "tools/agent_tools/export_static_seed.py",
    "tests/agent_tools/test_export_static_seed.py",
)
for surface in REMOVED_SURFACES:
    remove_path(surface)

# Remove consumer-only fields from the canonical model-profile registry. Live
# Agent definitions remain AgentCanon-owned and continue to materialize normally.
profiles_path = ROOT / "agents/model_profiles.toml"
profiles = profiles_path.read_text(encoding="utf-8")
profiles = "\n".join(
    line
    for line in profiles.splitlines()
    if not re.match(r"^\s*(consumer_static_text|static_obligations)\s*=", line)
) + "\n"
profiles = re.sub(
    r"(?m)^registry_version\s*=\s*(\d+)\s*$",
    lambda match: f"registry_version = {int(match.group(1)) + 1}",
    profiles,
    count=1,
)
profiles_path.write_text(profiles, encoding="utf-8")

registry_path = ROOT / "tools/agent_tools/model_profile_registry.py"
registry = registry_path.read_text(encoding="utf-8")
registry = "\n".join(
    line
    for line in registry.splitlines()
    if "consumer_static_clause_projection" not in line
    and "consumer_static_obligation" not in line
) + "\n"
registry = re.sub(
    r"(?m)^_CLAUSE_FIELDS\s*=.*$",
    '_CLAUSE_FIELDS = {"id", "text", "priority"}',
    registry,
    count=1,
)

start_marker = "# These are exact, case-normalized producer prefixes."
end_marker = "class StructuralDesignGap"
if start_marker in registry:
    start = registry.index(start_marker)
    end = registry.index(end_marker, start)
    registry = registry[:start] + registry[end:]

static_dataclass = "@dataclass(frozen=True)\nclass ConsumerStaticClauseProjection"
role_dataclass = "@dataclass(frozen=True)\nclass RoleInstructionClause"
if static_dataclass in registry:
    start = registry.index(static_dataclass)
    end = registry.index(role_dataclass, start)
    registry = registry[:start] + registry[end:]
registry = "\n".join(
    line for line in registry.splitlines() if "consumer_static_projection:" not in line
) + "\n"

method_start = "    def projection_digest_for_role("
method_end = "\ndef _read_toml_file"
if method_start not in registry or method_end not in registry:
    raise SystemExit("model profile digest method boundary not found")
start = registry.index(method_start)
end = registry.index(method_end, start)
replacement_method = '''    def projection_digest_for_role(self, role_id: str, profile_id: str) -> str:
        """Bind each executable role view to one canonical live clause digest."""
        profile = self.profile_for_role(role_id)
        clauses = self.instruction_clauses_for_role(role_id, profile_id)
        return _stable_digest(
            {
                "profile_id": profile.id,
                "role_id": role_id,
                "clauses": [
                    {
                        "id": clause.clause_id,
                        "priority": clause.priority,
                        "text": clause.text,
                    }
                    for clause in clauses
                ],
            }
        )
'''
registry = registry[:start] + replacement_method + registry[end:]


def remove_keyword_argument(source: str, marker: str) -> str:
    lines = source.splitlines()
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if marker not in line:
            output.append(line)
            index += 1
            continue
        balance = line.count("(") - line.count(")")
        index += 1
        while index < len(lines) and balance > 0:
            balance += lines[index].count("(") - lines[index].count(")")
            index += 1
    return "\n".join(output) + "\n"


registry = remove_keyword_argument(
    registry,
    "consumer_static_projection=_static_projection(",
)

helper_start = "def _validate_projection_mode"
helper_end = "def generate_role_views"
if helper_start not in registry or helper_end not in registry:
    raise SystemExit("role projection helper boundary not found")
start = registry.index(helper_start)
end = registry.index(helper_end, start)
replacement_helpers = '''def _validate_projection_mode(projection: str) -> str:
    if projection != "live":
        raise ModelProfileRegistryError(
            f"role_projection:unsupported_projection:{projection}"
        )
    return projection


def _render_instruction_clauses(
    clauses: Sequence[RoleInstructionClause],
    projection: str,
) -> str:
    _validate_projection_mode(projection)
    return " ".join(clause.text for clause in clauses)


'''
registry = registry[:start] + replacement_helpers + registry[end:]

render_start = "def _render_role_view"
render_end = "def _projection_records"
if render_start not in registry or render_end not in registry:
    raise SystemExit("role view renderer boundary not found")
start = registry.index(render_start)
end = registry.index(render_end, start)
replacement_renderer = '''def _render_role_view(view: GeneratedRoleView, projection: str = "live") -> str:
    _validate_projection_mode(projection)
    nicknames = ", ".join(_toml_string(value) for value in view.nickname_candidates)
    comments = (
        "# @dependency-start",
        "# contract configuration",
        f"# responsibility Projects the canonical {view.role_id} model profile into executable Codex settings.",
        "# upstream implementation ../../agents/model_profiles.toml owns model/profile authority",
        "# upstream implementation ../../tools/agent_tools/model_profile_registry.py materializes this view",
        "# downstream implementation ../../tools/agent_tools/check_agent_runtime_alignment.py validates projection parity",
        "# @dependency-end",
        "# generated role view: generated_role_view_v1",
        "# generated from agents/model_profiles.toml plus canonical team/runtime role metadata",
        "# materializer: tools/agent_tools/model_profile_registry.py",
        f"# source canonical digest: {view.source_canonical_digest}",
    )
    return "\\n".join(
        (
            *comments,
            "",
            f"name = {_toml_string(view.name)}",
            f"description = {_toml_string(view.description)}",
            f"nickname_candidates = [{nicknames}]",
            f"sandbox_mode = {_toml_string(view.sandbox_mode)}",
            f"approval_policy = {_toml_string(view.approval_policy)}",
            f"model = {_toml_string(view.model)}",
            f"model_reasoning_effort = {_toml_string(view.reasoning_effort)}",
            "",
            f"developer_instructions = {_toml_string(view.rendered_instructions)}",
            "",
        )
    )


'''
registry = registry[:start] + replacement_renderer + registry[end:]
registry = registry.replace(
    'choices=("live", "consumer-static")',
    'choices=("live",)',
)
for forbidden in (
    "consumer-static",
    "consumer_static_text",
    "static_obligations",
    "ConsumerStaticClauseProjection",
    "compose_consumer_static_clause",
):
    if forbidden in registry:
        raise SystemExit(f"stale consumer projection token in registry: {forbidden}")
ast.parse(registry)
registry_path.write_text(registry, encoding="utf-8")


def remove_source_ranges(source: str, ranges: list[tuple[int, int]]) -> str:
    lines = source.splitlines()
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    for start, end in reversed(merged):
        del lines[start - 1 : end]
    return "\n".join(lines) + "\n"


def strip_static_consumer_mode(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        segment = ast.get_source_segment(source, node) or ""
        lowered = segment.casefold()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if "static_seed" in node.name.casefold():
                ranges.append((node.lineno, node.end_lineno or node.lineno))
                continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets: list[str] = []
            raw_targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in raw_targets:
                if isinstance(target, ast.Name):
                    targets.append(target.id)
            if any("STATIC_SEED" in target for target in targets):
                ranges.append((node.lineno, node.end_lineno or node.lineno))
                continue
        if isinstance(node, ast.Expr) and "--static-seed-consumer" in lowered:
            ranges.append((node.lineno, node.end_lineno or node.lineno))
            continue
        if isinstance(node, ast.If):
            test = ast.get_source_segment(source, node.test) or ""
            if "static_seed_consumer" in test.casefold():
                ranges.append((node.lineno, node.end_lineno or node.lineno))
    updated = remove_source_ranges(source, ranges)
    # Remove dependency-header lines and stale explanatory comments only after
    # executable nodes have been removed.
    updated = "\n".join(
        line
        for line in updated.splitlines()
        if "static-seed-consumer" not in line.casefold()
        and "static_seed_consumer" not in line.casefold()
    ) + "\n"
    ast.parse(updated)
    path.write_text(updated, encoding="utf-8")


bootstrap_checker = ROOT / "tools/docs/check_bootstrap_docs.py"
if bootstrap_checker.is_file():
    strip_static_consumer_mode(bootstrap_checker)


def rewrite_test_without_consumer_mode(path: Path) -> None:
    if not path.is_file():
        return
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    class Transformer(ast.NodeTransformer):
        def _drop(self, node: ast.AST) -> bool:
            segment = ast.get_source_segment(source, node) or ""
            lowered = segment.casefold()
            return any(
                marker in lowered
                for marker in (
                    "consumer-static",
                    "consumer_static",
                    "static-seed-consumer",
                    "static_seed_consumer",
                    "static_obligation",
                )
            )

        def visit_FunctionDef(self, node: ast.FunctionDef):  # type: ignore[override]
            if self._drop(node):
                return None
            return self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):  # type: ignore[override]
            if self._drop(node):
                return None
            return self.generic_visit(node)

        def visit_Assign(self, node: ast.Assign):  # type: ignore[override]
            if self._drop(node):
                return None
            return self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign):  # type: ignore[override]
            if self._drop(node):
                return None
            return self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef):  # type: ignore[override]
            node = self.generic_visit(node)
            if isinstance(node, ast.ClassDef) and not node.body:
                node.body = [ast.Pass()]
            return node

    transformed = Transformer().visit(tree)
    ast.fix_missing_locations(transformed)
    rendered = ast.unparse(transformed) + "\n"
    path.write_text(rendered, encoding="utf-8")


rewrite_test_without_consumer_mode(ROOT / "tests/agent_tools/test_model_profile_registry.py")
rewrite_test_without_consumer_mode(ROOT / "tests/tools/test_check_bootstrap_docs.py")

YAML_MARKERS = (
    "export_static_seed",
    "static-seed-allowlist",
    "static-seed-export",
    "static-seed-consumer",
    "consumer-static",
)


def remove_yaml_list_blocks(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    index = 0
    while index < len(lines):
        match = re.match(r"^(\s*)-\s+", lines[index])
        if not match:
            output.append(lines[index])
            index += 1
            continue
        indent = len(match.group(1))
        end = index + 1
        while end < len(lines):
            next_line = lines[end]
            next_match = re.match(r"^(\s*)-\s+", next_line)
            if next_match and len(next_match.group(1)) == indent:
                break
            if next_line.strip() and len(next_line) - len(next_line.lstrip()) < indent:
                break
            end += 1
        block = "\n".join(lines[index:end]).casefold()
        if any(marker in block for marker in YAML_MARKERS):
            index = end
            continue
        output.extend(lines[index:end])
        index = end
    return "\n".join(output) + "\n"


for relative in (
    ".github/workflows/agent-canon-static-gates.yml",
    "tools/catalog.yaml",
):
    path = ROOT / relative
    if path.is_file():
        cleaned = remove_yaml_list_blocks(path.read_text(encoding="utf-8"))
        cleaned = "\n".join(
            line
            for line in cleaned.splitlines()
            if not any(marker in line.casefold() for marker in YAML_MARKERS)
        ) + "\n"
        path.write_text(cleaned, encoding="utf-8")

DOC_MARKERS = (
    "export_static_seed",
    "static-seed-allowlist",
    "static-seed-export",
    "static-seed-consumer",
    "consumer-static",
    "consumer static",
)


def strip_markdown(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    skip_level: int | None = None
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            heading = stripped[level:].strip().casefold()
            if skip_level is not None and level <= skip_level:
                skip_level = None
            if skip_level is None and any(marker in heading for marker in DOC_MARKERS):
                skip_level = level
                continue
        if skip_level is not None:
            continue
        if any(marker in line.casefold() for marker in DOC_MARKERS):
            continue
        output.append(line)
    while output and not output[-1].strip():
        output.pop()
    return "\n".join(output) + "\n"


for path in ROOT.rglob("*.md"):
    if any(part in {"issues", "reports", "references"} for part in path.parts):
        continue
    path.write_text(strip_markdown(path.read_text(encoding="utf-8")), encoding="utf-8")

boundary_doc = ROOT / "documents/contracts/template-bootstrap.md"
if boundary_doc.is_file():
    text = boundary_doc.read_text(encoding="utf-8").rstrip() + "\n"
    heading = "## Agent definition distribution boundary"
    if heading not in text:
        text += f'''\n{heading}\n\nDefault project templates receive no Agent role definitions, prompts, model\nprofiles, Skill bindings, registration tables, provenance records, or import\nmechanisms. Those executable contracts remain in AgentCanon and the active\nruntime. A change to the Agent inventory must not produce a template payload or\nconsumer repository diff.\n'''
    boundary_doc.write_text(text, encoding="utf-8")

# Remove dependency-header references to deleted files from active source files.
exact_references = tuple(surface.casefold() for surface in REMOVED_SURFACES)
for path in ROOT.rglob("*"):
    if not path.is_file() or any(part in {".git", "issues", "reports", "references"} for part in path.parts):
        continue
    if path in {
        Path(__file__).resolve(),
        ROOT / "tests/agent_tools/test_template_agent_definition_boundary.py",
    }:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    lines = text.splitlines()
    filtered = [
        line
        for line in lines
        if not any(reference in line.casefold() for reference in exact_references)
    ]
    if filtered != lines:
        path.write_text("\n".join(filtered) + "\n", encoding="utf-8")

boundary_test = r'''from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REMOVED = (
    "documents/contracts/static-seed-allowlist.toml",
    "documents/contracts/static-seed-export.md",
    "documents/tools/export_static_seed.md",
    "tools/agent_tools/export_static_seed.py",
    "tests/agent_tools/test_export_static_seed.py",
)

ACTIVE_SURFACES = (
    "agents/model_profiles.toml",
    "tools/agent_tools/model_profile_registry.py",
    "tools/docs/check_bootstrap_docs.py",
    ".github/workflows/agent-canon-static-gates.yml",
    "tools/catalog.yaml",
    "tools/README.md",
    "documents/contracts",
    "documents/tools",
)

FORBIDDEN = (
    "consumer-static",
    "consumer_static_text",
    "static_obligations",
    "export_static_seed",
    "static-seed-allowlist",
    "static-seed-export",
    "--static-seed-consumer",
)


def test_default_template_agent_export_surfaces_are_absent() -> None:
    for relative in REMOVED:
        assert not (ROOT / relative).exists(), relative


def test_active_owners_do_not_reintroduce_template_agent_distribution() -> None:
    findings: list[str] = []
    for relative in ACTIVE_SURFACES:
        path = ROOT / relative
        candidates = [path] if path.is_file() else sorted(path.rglob("*")) if path.is_dir() else []
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                text = candidate.read_text(encoding="utf-8").casefold()
            except UnicodeDecodeError:
                continue
            for token in FORBIDDEN:
                if token.casefold() in text:
                    findings.append(f"{candidate.relative_to(ROOT)}:{token}")
    assert findings == []


def test_agentcanon_retains_the_live_agent_owner() -> None:
    assert (ROOT / "agents/model_profiles.toml").is_file()
    assert (ROOT / ".codex/agents/worker.toml").is_file()
    assert (ROOT / ".codex/agents/reviewer.toml").is_file()
'''
(ROOT / "tests/agent_tools/test_template_agent_definition_boundary.py").write_text(
    boundary_test,
    encoding="utf-8",
)

# Fail before materialization if any active owner still carries the old
# distribution vocabulary. Historical issue/report/reference records are
# intentionally excluded.
forbidden_active = (
    "consumer-static",
    "consumer_static_text",
    "static_obligations",
    "export_static_seed",
    "static-seed-allowlist",
    "static-seed-export",
    "--static-seed-consumer",
)
allowed = {
    Path(__file__).resolve(),
    ROOT / "tests/agent_tools/test_template_agent_definition_boundary.py",
}
for relative in (
    "agents/model_profiles.toml",
    "tools/agent_tools/model_profile_registry.py",
    "tools/docs/check_bootstrap_docs.py",
    ".github/workflows/agent-canon-static-gates.yml",
    "tools/catalog.yaml",
    "tools/README.md",
    "documents/contracts",
    "documents/tools",
):
    path = ROOT / relative
    candidates = [path] if path.is_file() else path.rglob("*") if path.is_dir() else []
    for candidate in candidates:
        if not candidate.is_file() or candidate in allowed:
            continue
        try:
            text = candidate.read_text(encoding="utf-8").casefold()
        except UnicodeDecodeError:
            continue
        residual = [token for token in forbidden_active if token in text]
        if residual:
            raise SystemExit(f"stale template Agent export owner: {candidate}: {residual}")

print("ISSUE_781_MIGRATION=applied")
