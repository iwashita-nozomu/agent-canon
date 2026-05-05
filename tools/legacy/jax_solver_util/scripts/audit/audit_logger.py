# @dependency-start
# upstream implementation ../README.md directory index and local context contract
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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from enum import Enum


class AuditLevel(Enum):
    """監査ログレベル"""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SECURITY = "SECURITY"
    COMPLIANCE = "COMPLIANCE"


class AuditLogger:
    """監査ログ記録システム"""
    
    def __init__(self, log_dir: Path = None):
        """初期化
        
        Args:
            log_dir: ログ出力ディレクトリ（環境変数 AUDIT_LOG_DIR で設定可能）
        """
        if log_dir is None:
            log_dir = Path(os.getenv("AUDIT_LOG_DIR", "reports/audit"))
        
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "audit.jsonl"
    
    def log(
        self,
        action: str,
        actor: str,
        level: AuditLevel = AuditLevel.INFO,
        details: Optional[Dict[str, Any]] = None,
        resource: Optional[str] = None,
        outcome: str = "success",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
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
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        log_entry = {
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
        }
        
        # ファイルに追記
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        
        # セキュリティログの場合は別ファイルにも
        if level == AuditLevel.SECURITY or level == AuditLevel.COMPLIANCE:
            self._log_to_security_file(log_entry)
        
        return log_entry
    
    def _log_to_security_file(self, entry: Dict[str, Any]) -> None:
        """セキュリティ・コンプライアンスログを分離ファイルに記録"""
        security_file = self.log_dir / "security.jsonl"
        with open(security_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    def _get_current_commit(self) -> str:
        """現在の git commit SHA を取得"""
        try:
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd="/workspace"
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
                cwd="/workspace"
            )
            return result.stdout.strip()
        except Exception:
            return "unknown"
    
    def get_logs(
        self,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        level: Optional[AuditLevel] = None,
        limit: int = 100,
    ) -> list[Dict[str, Any]]:
        """監査ログを検索
        
        Args:
            actor: 特定のアクターでフィルター
            action: 特定のアクションでフィルター
            level: 特定のレベルでフィルター
            limit: 最大取得件数
        
        Returns:
            フィルター済みログリスト
        """
        logs = []
        
        if not self.log_file.exists():
            return logs
        
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    
                    # フィルター適用
                    if actor and entry.get("actor") != actor:
                        continue
                    if action and entry.get("action") != action:
                        continue
                    if level and entry.get("level") != level.value:
                        continue
                    
                    logs.append(entry)
                except json.JSONDecodeError:
                    continue
        
        return logs[-limit:]
    
    def get_statistics(self) -> Dict[str, Any]:
        """監査ログ統計を計算"""
        if not self.log_file.exists():
            return {
                "total_entries": 0,
                "by_action": {},
                "by_actor": {},
                "by_level": {},
                "by_outcome": {},
            }
        
        stats = {
            "total_entries": 0,
            "by_action": {},
            "by_actor": {},
            "by_level": {},
            "by_outcome": {},
        }
        
        logs = self.get_logs(limit=10000)
        
        for entry in logs:
            stats["total_entries"] += 1
            
            action = entry.get("action", "unknown")
            stats["by_action"][action] = stats["by_action"].get(action, 0) + 1
            
            actor = entry.get("actor", "unknown")
            stats["by_actor"][actor] = stats["by_actor"].get(actor, 0) + 1
            
            level = entry.get("level", "unknown")
            stats["by_level"][level] = stats["by_level"].get(level, 0) + 1
            
            outcome = entry.get("outcome", "unknown")
            stats["by_outcome"][outcome] = stats["by_outcome"].get(outcome, 0) + 1
        
        return stats


# グローバルインスタンス
_logger = None


def get_audit_logger() -> AuditLogger:
    """グローバル監査ロガーを取得"""
    global _logger
    if _logger is None:
        _logger = AuditLogger()
    return _logger


def audit_log(action: str, level: AuditLevel = AuditLevel.INFO):
    """監査ログデコレーター
    
    使用例:
        @audit_log("skill_execution", AuditLevel.INFO)
        def run_skill(skill_id: str):
            pass
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger = get_audit_logger()
            actor = os.getenv("GITHUB_ACTOR", os.getenv("USER", "unknown"))
            
            try:
                result = func(*args, **kwargs)
                logger.log(
                    action=action,
                    actor=actor,
                    level=level,
                    outcome="success",
                    details={"args": str(args), "kwargs": str(kwargs)},
                )
                return result
            except Exception as e:
                logger.log(
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
    logger.log(
        action="test_action",
        actor="test_user",
        level=AuditLevel.INFO,
        details={"test": "data"},
    )
    
    # セキュリティログ
    logger.log(
        action="security_check",
        actor="system",
        level=AuditLevel.SECURITY,
        details={"vulnerability": "none"},
    )
    
    # 統計表示
    stats = logger.get_statistics()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    
    print("✅ Audit logger working")
