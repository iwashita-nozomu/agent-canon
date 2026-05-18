#!/usr/bin/env python3
# @dependency-start
# responsibility Logs Codex skill usage signals from hook payloads.
# upstream implementation ../hooks.json invokes this hook at prompt and stop boundaries.
# upstream design ../../agents/evals/README.md requires skill-use eval evidence.
# upstream implementation ./hook_event_log.py assigns Canon-owned hook log paths and IDs.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates hook logging.
# @dependency-end

"""Append local JSONL records for skill usage observed by Codex hooks."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from hook_event_log import HookLogContext, fingerprint_json, utc_now

LOG_PATH_ENV = "AGENT_CANON_SKILL_LOG_PATH"
WORKFLOW_MONITOR_REPORT_DIR_ENV = "AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR"
DISABLE_LOG_ENV = "AGENT_CANON_DISABLE_HOOK_LOG"
SKILL_TOKEN_RE = re.compile(r"\$([A-Za-z0-9][A-Za-z0-9_-]*)")
SKILLS_FIELD_RE = re.compile(r"(?:^|\s)(?:skills|skill_invocation)=([^\s]+)")
SKILL_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
GIT_ROOT_TIMEOUT_SECONDS = 5
SKILL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "agent-learning": ("人間からのフィードバック", "feedback", "runtime feedback", "学習"),
    "agent-orchestration": ("どのスキル", "どのskill", "workflow=", "routing", "フロー"),
    "md-style-check": ("markdown", "マークダウン", "md-style", "docs-check", "markdownlint"),
    "result-artifact-writeout": ("結果書き出し", "結果を書き出", "result writeout", "artifact"),
    "oop-readability-check": ("oop", "readability", "オブジェクト指向"),
}
WORKFLOW_KEYWORDS: dict[str, tuple[str, ...]] = {
    "adaptive-improvement-loop": ("goal.md", "next_action", "backlog", "iteration", "改善ループ"),
    "agent-canon-pr-workflow": ("agent-canon pr", "pull request", "pr #", "マージ", "merge"),
    "codex-task-workflow": ("実装", "修正", "組み込み", "続けて", "repo-changing"),
    "environment-maintenance": ("docker", "devcontainer", "container", "github actions", "ci"),
}
TOOL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "audit_and_fix_links.py": ("audit_and_fix_links.py", "broken link", "リンク切れ"),
    "check_markdown_lint.py": ("check_markdown_lint.py", "markdownlint"),
    "check_markdown_math.py": ("check_markdown_math.py", "markdown math"),
    "format_markdown.py": ("format_markdown.py", "markdown format"),
    "skill_usage_logger.py": ("入力プロンプト", "prompt", "skill usage", "skill_usage"),
    "workflow_monitor.py": ("workflow_monitor", "runtime-feedback", "runtime feedback"),
    "generate_agent_improvement_guide.py": ("improvement guide", "改善指南", "githubaction"),
    "tool_rejection_preflight.py": ("tool rejection", "preflight", "はじかれる"),
    "log_surface_inventory.py": ("ログ項目", "log surface", "hook log"),
    "run_docs_checks.sh": ("run_docs_checks.sh", "docs-check", "markdownlint"),
}
PROMPT_EXCERPT_LIMIT = 600
SECRET_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"-----BEGIN (RSA |DSA |EC |OPENSSH |)PRIVATE KEY-----.*?-----END [^-]+PRIVATE KEY-----", re.DOTALL), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_ACCESS_KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b"), "[REDACTED_API_KEY]"),
)
FEEDBACK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "quality_gap": ("弱い", "足り", "浅い", "甘い", "まずい", "だめ", "ダメ"),
    "repair_request": ("直して", "修正", "改善", "見直", "組み込み", "入れたい"),
    "missing_mechanism": ("機構", "仕組み", "メカニズム", "ログに積む"),
}


@dataclass(frozen=True)
class PromptIntakeSignals:
    """Classified prompt signals written by the skill usage hook."""

    skills: tuple[str, ...]
    candidate_skills: tuple[str, ...]
    candidate_workflows: tuple[str, ...]
    candidate_tools: tuple[str, ...]
    feedback_labels: tuple[str, ...]
    feedback_action: str

    def should_log(self) -> bool:
        """Return whether this payload contains durable prompt-intake evidence."""
        return bool(
            self.skills
            or self.candidate_skills
            or self.candidate_workflows
            or self.candidate_tools
            or self.feedback_labels
        )

    def feedback_targets(self) -> tuple[str, ...]:
        """Return concrete feedback targets for workflow monitor routing."""
        skill_targets = tuple(sorted(set(self.skills + self.candidate_skills)))
        targets = [
            *(f"skill:{item}" for item in skill_targets),
            *(f"workflow:{item}" for item in self.candidate_workflows),
            *(f"tool:{item}" for item in self.candidate_tools),
        ]
        return tuple(targets or (("agent-runtime",) if self.feedback_labels else ()))


@dataclass(frozen=True)
class PromptCapture:
    """Bounded prompt text capture for later routing analysis."""

    status: str
    excerpt_redacted: str
    fingerprint: str
    char_count: int
    truncated: bool

    def should_log(self) -> bool:
        """Return whether prompt evidence exists."""
        return self.status == "present"


@dataclass(frozen=True)
class ToolSelection:
    """PostToolUse tool selection evidence."""

    tool_name: str
    tool_input_fingerprint: str
    tool_input_key_count: int
    tool_input_keys: tuple[str, ...]
    command_verb: str

    def should_log(self) -> bool:
        """Return whether tool selection evidence exists."""
        return bool(self.tool_name)


def load_payload() -> dict[str, object]:
    """Read one JSON hook payload from stdin."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def repo_root() -> Path:
    """Resolve the active repository root for hook logs."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_ROOT_TIMEOUT_SECONDS,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return Path.cwd()


def hook_event_name(payload: dict[str, object]) -> str:
    """Return the hook event name."""
    value = payload.get("hookEventName")
    return value if isinstance(value, str) and value else "UnknownHookEvent"


def text_values(value: object) -> list[str]:
    """Return text leaves from nested hook payload data."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        values: list[str] = []
        for child in value.values():
            values.extend(text_values(child))
        return values
    if isinstance(value, list):
        values: list[str] = []
        for child in value:
            values.extend(text_values(child))
        return values
    return []


def extract_skill_ids(text: str) -> set[str]:
    """Extract normalized skill ids from one text payload."""
    skills = {match.group(1).strip("-_") for match in SKILL_TOKEN_RE.finditer(text)}
    for match in SKILLS_FIELD_RE.finditer(text):
        raw_values = match.group(1).split(",")
        for raw_value in raw_values:
            value = raw_value.strip().strip("`'\"[](){}")
            value = value.removeprefix("$").strip("-_")
            if value and value != "-":
                skills.add(value)
    return {skill for skill in skills if SKILL_ID_RE.fullmatch(skill)}


def observed_text(payload: dict[str, object]) -> list[str]:
    """Return hook payload text fields relevant for skill-use discovery."""
    texts: list[str] = []
    for key in ("prompt", "last_assistant_message", "message", "tool_input"):
        if key in payload:
            texts.extend(text_values(payload[key]))
    return texts


def prompt_text(payload: dict[str, object]) -> str:
    """Return the raw UserPromptSubmit prompt text when present."""
    value = payload.get("prompt")
    return value if isinstance(value, str) else ""


def prompt_capture(payload: dict[str, object]) -> PromptCapture:
    """Return bounded redacted prompt evidence."""
    text = prompt_text(payload)
    if not text:
        return PromptCapture("missing", "", "", 0, False)
    redacted = redact_sensitive_text(text)
    excerpt = redacted[:PROMPT_EXCERPT_LIMIT]
    return PromptCapture(
        status="present",
        excerpt_redacted=excerpt,
        fingerprint=sha256(text.encode("utf-8")).hexdigest()[:16],
        char_count=len(text),
        truncated=len(redacted) > PROMPT_EXCERPT_LIMIT,
    )


def redact_sensitive_text(text: str) -> str:
    """Redact high-confidence secret-like values from prompt excerpts."""
    redacted = text
    for pattern, replacement in SECRET_REDACTIONS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def observed_text_sources(payload: dict[str, object]) -> list[str]:
    """Return payload field names that contributed text for skill discovery."""
    sources: list[str] = []
    for key in ("prompt", "last_assistant_message", "message", "tool_input"):
        if key in payload and text_values(payload[key]):
            sources.append(key)
    return sources


def observed_skills(payload: dict[str, object]) -> list[str]:
    """Return sorted unique skill ids observed in a hook payload."""
    skills: set[str] = set()
    for text in observed_text(payload):
        skills.update(extract_skill_ids(text))
    return sorted(skills)


def keyword_matches(texts: list[str], mapping: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    """Return mapping keys whose keywords appear in observed prompt text."""
    haystack = "\n".join(texts).lower()
    return tuple(
        key
        for key, needles in sorted(mapping.items())
        if any(needle.lower() in haystack for needle in needles)
    )


def feedback_action(labels: tuple[str, ...]) -> str:
    """Return the workflow-monitor action for observed human feedback."""
    if not labels:
        return ""
    if "quality_gap" in labels or "repair_request" in labels:
        return "prompt_repair"
    return "memory_record"


def prompt_intake_signals(payload: dict[str, object]) -> PromptIntakeSignals:
    """Classify prompt text into explicit and candidate routing signals."""
    texts = observed_text(payload)
    labels = keyword_matches(texts, FEEDBACK_KEYWORDS)
    return PromptIntakeSignals(
        skills=tuple(observed_skills(payload)),
        candidate_skills=keyword_matches(texts, SKILL_KEYWORDS),
        candidate_workflows=keyword_matches(texts, WORKFLOW_KEYWORDS),
        candidate_tools=keyword_matches(texts, TOOL_KEYWORDS),
        feedback_labels=labels,
        feedback_action=feedback_action(labels),
    )


def tool_selection(payload: dict[str, object]) -> ToolSelection:
    """Return PostToolUse tool selection evidence."""
    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input")
    keys = tuple(sorted(tool_input.keys())) if isinstance(tool_input, dict) else ()
    return ToolSelection(
        tool_name=tool_name,
        tool_input_fingerprint=fingerprint_json(tool_input) if tool_input is not None else "",
        tool_input_key_count=len(keys),
        tool_input_keys=keys,
        command_verb=command_verb(tool_input),
    )


def command_verb(tool_input: object) -> str:
    """Return the first command token for shell-like tool input."""
    if not isinstance(tool_input, dict):
        return ""
    command = tool_input.get("cmd") or tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return ""
    return command.strip().split()[0]


def default_log_path(root: Path) -> Path:
    """Return the skill usage log path."""
    override = os.environ.get(LOG_PATH_ENV, "").strip()
    return HookLogContext(root, "skill_usage", override).result_path()


def _log_append_log(root: Path, entry: dict[str, object]) -> None:
    """Append one skill usage JSONL entry without blocking runtime progress."""
    if os.environ.get(DISABLE_LOG_ENV, "").strip() == "1":
        return
    try:
        path = default_log_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            json.dump(entry, stream, sort_keys=True)
            stream.write("\n")
    except OSError:
        return


def workflow_monitor_path(root: Path) -> Path:
    """Return the canonical workflow monitor tool path."""
    return root / "tools" / "agent_tools" / "workflow_monitor.py"


def workflow_monitor_report_dir() -> str:
    """Return the optional run-bundle report dir for behavior evidence."""
    return os.environ.get(WORKFLOW_MONITOR_REPORT_DIR_ENV, "").strip()


def append_workflow_monitor_events(root: Path, signals: PromptIntakeSignals) -> tuple[int, int]:
    """Append skill invocation and feedback events when a run bundle is active."""
    report_dir = workflow_monitor_report_dir()
    monitor = workflow_monitor_path(root)
    if not report_dir or not monitor.is_file():
        return 0, 0
    skill_event_count = 0
    feedback_event_count = 0
    for skill in signals.skills:
        result = subprocess.run(
            [
                sys.executable,
                str(monitor),
                "--report-dir",
                report_dir,
                "--behavior-event",
                f"skill_invocation=${skill} status=observed source=codex_hook",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_ROOT_TIMEOUT_SECONDS,
        )
        if result.returncode == 0:
            skill_event_count += 1
    if signals.feedback_labels and signals.feedback_action:
        for target in signals.feedback_targets():
            result = subprocess.run(
                [
                    sys.executable,
                    str(monitor),
                    "--report-dir",
                    report_dir,
                    "--runtime-feedback",
                    (
                        "source=user "
                        f"target={target} "
                        f"action={signals.feedback_action} "
                        "evidence=codex_prompt_intake"
                    ),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=GIT_ROOT_TIMEOUT_SECONDS,
            )
            if result.returncode == 0:
                feedback_event_count += 1
    return skill_event_count, feedback_event_count


def main() -> int:
    """Append one skill usage hook log entry."""
    payload = load_payload()
    root = repo_root()
    signals = prompt_intake_signals(payload)
    prompt = prompt_capture(payload)
    tool = tool_selection(payload)
    if not (signals.should_log() or prompt.should_log() or tool.should_log()):
        return 0
    text_sources = observed_text_sources(payload)
    text_values_seen = observed_text(payload)
    workflow_event_count, workflow_feedback_count = append_workflow_monitor_events(root, signals)
    timestamp = utc_now()
    payload_fingerprint = fingerprint_json(payload)
    context = HookLogContext(root, "skill_usage", os.environ.get(LOG_PATH_ENV, "").strip())
    _log_append_log(
        root,
        {
            "hook_run_id": context.run_id(timestamp, payload_fingerprint),
            "hook_log_namespace": context.runtime_namespace(),
            "timestamp": timestamp,
            "event": hook_event_name(payload),
            "event_fallback": hook_event_name(payload) == "UnknownHookEvent",
            "skills": list(signals.skills),
            "skill_count": len(signals.skills),
            "candidate_skills": list(signals.candidate_skills),
            "candidate_skill_count": len(signals.candidate_skills),
            "candidate_workflows": list(signals.candidate_workflows),
            "candidate_workflow_count": len(signals.candidate_workflows),
            "candidate_tools": list(signals.candidate_tools),
            "candidate_tool_count": len(signals.candidate_tools),
            "prompt_capture_status": prompt.status,
            "prompt_excerpt_redacted": prompt.excerpt_redacted,
            "prompt_fingerprint": prompt.fingerprint,
            "prompt_char_count": prompt.char_count,
            "prompt_excerpt_truncated": prompt.truncated,
            "tool_name": tool.tool_name,
            "tool_selection_kind": "executed_tool" if tool.should_log() else "",
            "tool_input_fingerprint": tool.tool_input_fingerprint,
            "tool_input_key_count": tool.tool_input_key_count,
            "tool_input_keys": list(tool.tool_input_keys),
            "tool_command_verb": tool.command_verb,
            "prompt_feedback_detected": bool(signals.feedback_labels),
            "feedback_labels": list(signals.feedback_labels),
            "feedback_targets": list(signals.feedback_targets()),
            "feedback_action": signals.feedback_action,
            "skill_source_fields": text_sources,
            "observed_text_field_count": len(text_sources),
            "observed_text_value_count": len(text_values_seen),
            "payload_key_count": len(payload),
            "payload_fingerprint": payload_fingerprint,
            "status": "pass",
            "workflow_monitor_event_count": workflow_event_count,
            "workflow_monitor_feedback_count": workflow_feedback_count,
            "workflow_monitor_report_dir": workflow_monitor_report_dir(),
            "root": str(root),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
