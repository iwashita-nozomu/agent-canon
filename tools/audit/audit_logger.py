# @dependency-start
# contract tool
# responsibility Writes JSONL audit logs for agent and repository automation events.
# upstream design ../README.md shared tool index
# upstream implementation audit_log_schema.py defines the entry schema
# downstream design ../../documents/experiments/result-log-retention-and-visualization.md result policy
# @dependency-end
"""
Audit Logger — 監査ログシステム

すべてのエージェント・スキル実行を記録：
- Who: ユーザー/ロール
- What: 操作内容
- When: タイムスタンプ
- Where: ファイル/場所
- Why: 理由/コンテキスト
- Outcome: 結果
"""

import json
import os
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import ParamSpec, TypeAlias, TypeVar, cast

try:
    from tools.agent_tools.runtime_artifacts import (
        RuntimeArtifactBoundary,
        RuntimeRootRequired,
        runtime_artifact_boundary,
    )
except ImportError:  # pragma: no cover - direct script invocation.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools.agent_tools.runtime_artifacts import (  # type: ignore[no-redef]
        RuntimeArtifactBoundary,
        RuntimeRootRequired,
        runtime_artifact_boundary,
    )

UTC = timezone.utc

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
P = ParamSpec("P")
R = TypeVar("R")


class AuditLevel(Enum):
    """監査ログレベル"""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SECURITY = "SECURITY"
    COMPLIANCE = "COMPLIANCE"


class AuditLogger:
    """監査ログ記録システム"""
    
    def __init__(
        self,
        log_dir: Path | None = None,
        *,
        source_root: Path | None = None,
        runtime_root: Path | str | None = None,
    ):
        """初期化
        
        Args:
            log_dir: Optional path below the explicitly selected runtime
                root.  Absolute paths must already be below that root;
                relative paths are interpreted below it.  It is not a second
                output capability and can never target a source checkout.
            source_root: Source checkout used to reject a runtime root that
                would overlap the source.  The checkout must be supplied by
                the caller or by the typed target-root capability; the current
                working directory is intentionally not inferred.
            runtime_root: Explicit external runtime root.  When ``log_dir``
                is omitted this must be supplied or available through
                ``AGENT_CANON_RUNTIME_ROOT``.
        """
        source_value = source_root
        if source_value is None:
            # Bootstrap supplies a typed target-root capability to child
            # processes.  It is an explicit handoff, unlike cwd/git-root
            # discovery, and therefore does not accidentally select a parent
            # repository when AgentCanon is invoked from one.
            capability_source = os.getenv("AGENT_CANON_TARGET_ROOT", "").strip()
            if capability_source:
                source_value = Path(capability_source)
        if source_value is None:
            raise RuntimeRootRequired(
                "explicit source root required; pass source_root or set "
                "AGENT_CANON_TARGET_ROOT"
            )
        self.source_root = Path(source_value).expanduser().resolve()
        self._runtime_boundary: RuntimeArtifactBoundary = runtime_artifact_boundary(
            self.source_root,
            runtime_root,
            create=True,
        )

        configured_log_dir = log_dir
        if configured_log_dir is None:
            explicit_log_dir = os.getenv("AUDIT_LOG_DIR", "").strip()
            if explicit_log_dir:
                configured_log_dir = Path(explicit_log_dir)
        destination = (
            Path(configured_log_dir) if configured_log_dir is not None else Path("audit")
        )
        self.log_dir = self._runtime_boundary.resolve(destination)
        self._runtime_boundary.ensure_directory(destination)
        self.log_file = self.log_dir / "audit.jsonl"

    def _append(self, path: Path, payload: bytes) -> None:
        """Append using the shared external resolver when one is active."""
        relative = path.relative_to(self._runtime_boundary.root)
        self._runtime_boundary.append_bytes(relative, payload)
    
    def record(
        self,
        action: str,
        actor: str,
        level: AuditLevel = AuditLevel.INFO,
        details: JsonObject | None = None,
        resource: str | None = None,
        outcome: str = "success",
        metadata: JsonObject | None = None,
    ) -> JsonObject:
        """監査ログを記録
        
        Args:
            action: 実行されたアクション（例: "skill_executed", "pr_reviewed"）
            actor: 実行者（ユーザー/ロール名）
            level: ログレベル
            details: 詳細情報（JSON化可能な辞書）
            resource: 対象リソース（ファイル/PR/etc）
            outcome: 結果（success/failure/warning）
            metadata: 追加メタデータ
        
        Returns:
            ログエントリ
        """
        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        
        log_entry = cast(JsonObject, {
            "timestamp": timestamp,
            "action": action,
            "actor": actor,
            "level": level.value,
            "resource": resource,
            "outcome": outcome,
            "details": details or {},
            "metadata": metadata or {},
            "git_commit": self._get_current_commit(),
            "branch": self._get_current_branch(),
        })
        
        # ファイルに追記。デフォルト経路は外部 runtime root に限定する。
        payload = (json.dumps(log_entry, ensure_ascii=False) + "\n").encode("utf-8")
        self._append(self.log_file, payload)
        
        # セキュリティログの場合は別ファイルにも
        if level == AuditLevel.SECURITY or level == AuditLevel.COMPLIANCE:
            self._log_to_security_file(log_entry)
        
        return log_entry
    
    def _log_to_security_file(self, entry: JsonObject) -> None:
        """セキュリティ・コンプライアンスログを分離ファイルに記録"""
        security_file = self.log_dir / "security.jsonl"
        self._append(
            security_file,
            (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8"),
        )
    
    def _get_current_commit(self) -> str:
        """現在の git commit SHA を取得"""
        try:
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=self.source_root
            )
            return result.stdout.strip()[:8]
        except Exception:
            return "unknown"
    
    def _get_current_branch(self) -> str:
        """現在の git branch を取得"""
        try:
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=self.source_root
            )
            return result.stdout.strip()
        except Exception:
            return "unknown"
    
    def get_logs(
        self,
        actor: str | None = None,
        action: str | None = None,
        level: AuditLevel | None = None,
        limit: int = 100,
    ) -> list[JsonObject]:
        """監査ログを検索
        
        Args:
            actor: 特定のアクターでフィルター
            action: 特定のアクションでフィルター
            level: 特定のレベルでフィルター
            limit: 最大取得件数
        
        Returns:
            フィルター済みログリスト
        """
        logs: list[JsonObject] = []
        
        if not self.log_file.exists():
            return logs
        
        with open(self.log_file, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = cast(object, json.loads(line))
                    if not isinstance(entry, dict):
                        continue
                    log_entry = cast(JsonObject, entry)
                    
                    # フィルター適用
                    if actor and log_entry.get("actor") != actor:
                        continue
                    if action and log_entry.get("action") != action:
                        continue
                    if level and log_entry.get("level") != level.value:
                        continue
                    
                    logs.append(log_entry)
                except json.JSONDecodeError:
                    continue
        
        return logs[-limit:]
    
    def get_statistics(self) -> JsonObject:
        """監査ログ統計を計算"""
        if not self.log_file.exists():
            return cast(JsonObject, {
                "total_entries": 0,
                "by_action": {},
                "by_actor": {},
                "by_level": {},
                "by_outcome": {},
            })
        
        logs = self.get_logs(limit=10000)
        by_action: dict[str, int] = {}
        by_actor: dict[str, int] = {}
        by_level: dict[str, int] = {}
        by_outcome: dict[str, int] = {}
        
        for entry in logs:
            action = entry.get("action", "unknown")
            action_key = str(action)
            by_action[action_key] = by_action.get(action_key, 0) + 1
            
            actor = entry.get("actor", "unknown")
            actor_key = str(actor)
            by_actor[actor_key] = by_actor.get(actor_key, 0) + 1
            
            level = entry.get("level", "unknown")
            level_key = str(level)
            by_level[level_key] = by_level.get(level_key, 0) + 1
            
            outcome = entry.get("outcome", "unknown")
            outcome_key = str(outcome)
            by_outcome[outcome_key] = by_outcome.get(outcome_key, 0) + 1
        
        return cast(JsonObject, {
            "total_entries": len(logs),
            "by_action": by_action,
            "by_actor": by_actor,
            "by_level": by_level,
            "by_outcome": by_outcome,
        })


# グローバルインスタンス
_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """グローバル監査ロガーを取得"""
    global _logger
    if _logger is None:
        _logger = AuditLogger()
    return _logger


def audit_log(
    action: str,
    level: AuditLevel = AuditLevel.INFO,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """監査ログデコレーター
    
    使用例:
        @audit_log("skill_execution", AuditLevel.INFO)
        def run_skill(skill_id: str):
            pass
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            logger = get_audit_logger()
            actor = os.getenv("GITHUB_ACTOR", os.getenv("USER", "unknown"))
            
            try:
                result = func(*args, **kwargs)
                logger.record(
                    action=action,
                    actor=actor,
                    level=level,
                    outcome="success",
                    details={"args": str(args), "kwargs": str(kwargs)},
                )
                return result
            except Exception as e:
                logger.record(
                    action=action,
                    actor=actor,
                    level=level,
                    outcome="failure",
                    details={"error": str(e)},
                )
                raise
        
        return wrapper
    return decorator


if __name__ == "__main__":
    # テスト
    logger = AuditLogger()
    
    print("Testing Audit Logger...")
    
    # テストログ
    logger.record(
        action="test_action",
        actor="test_user",
        level=AuditLevel.INFO,
        details={"test": "data"},
    )
    
    # セキュリティログ
    logger.record(
        action="security_check",
        actor="system",
        level=AuditLevel.SECURITY,
        details={"vulnerability": "none"},
    )
    
    # 統計表示
    stats = logger.get_statistics()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    
    print("✅ Audit logger working")
