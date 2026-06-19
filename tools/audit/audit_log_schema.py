# @dependency-start
# contract tool
# responsibility Defines the portable audit-log JSON schema and dataclasses.
# upstream design ../README.md shared tool index
# downstream implementation audit_logger.py writes entries that follow this schema
# @dependency-end
"""
Audit Log Schema — 監査ログデータモデル

JSON Schema と TypeScript 型定義で監査ログの形式を厳密に定義。
静的型チェック・バリデーション・実行時チェックで一貫性を保証。
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TypeAlias, cast

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

# ========== JSON Schema Definition ==========

AUDIT_LOG_JSON_SCHEMA: dict[str, object] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Audit Log Entry",
    "description": "統一監査ログスキーマ",
    "type": "object",
    "required": [
        "timestamp",
        "action",
        "actor",
        "level",
        "outcome",
    ],
    "properties": {
        "timestamp": {
            "type": "string",
            "format": "date-time",
            "description": "ISO 8601 UTC timestamp"
        },
        "action": {
            "type": "string",
            "enum": [
                "skill_executed",
                "skill_failed",
                "code_reviewed",
                "test_run",
                "experiment_started",
                "experiment_completed",
                "security_check",
                "rbac_enforced",
                "secret_accessed",
                "deployment_started",
                "deployment_completed",
                "pr_opened",
                "pr_approved",
                "pr_merged",
            ],
            "description": "実行されたアクション"
        },
        "actor": {
            "type": "string",
            "description": "実行者（ユーザー/ロール/システムコンポーネント）"
        },
        "level": {
            "type": "string",
            "enum": ["INFO", "WARNING", "ERROR", "SECURITY", "COMPLIANCE"],
            "description": "ログレベル"
        },
        "resource": {
            "type": ["string", "null"],
            "description": "対象リソース（ファイル/PR/etc）"
        },
        "outcome": {
            "type": "string",
            "enum": ["success", "failure", "warning", "partial"],
            "description": "実行結果"
        },
        "details": {
            "type": "object",
            "description": "アクション固有の詳細情報",
            "additionalProperties": True
        },
        "metadata": {
            "type": "object",
            "description": "追加メタデータ",
            "properties": {
                "duration_ms": {
                    "type": "integer",
                    "description": "実行時間（ミリ秒）"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "タグリスト"
                }
            },
            "additionalProperties": True
        },
        "git_commit": {
            "type": "string",
            "description": "Git commit SHA（最初の8文字）"
        },
        "branch": {
            "type": "string",
            "description": "Git branch name"
        },
        "error": {
            "type": ["object", "null"],
            "properties": {
                "type": {"type": "string"},
                "message": {"type": "string"},
                "traceback": {"type": ["string", "null"]},
            },
            "description": "エラー情報（失敗時）"
        }
    },
    "additionalProperties": False
}


# ========== TypeScript Type Definitions (as comments) ==========

TYPE_DEFINITIONS = '''
// TypeScript definitions for audit log (reference)

type AuditLevel = "INFO" | "WARNING" | "ERROR" | "SECURITY" | "COMPLIANCE";

type AuditAction = 
  | "skill_executed"
  | "skill_failed"
  | "code_reviewed"
  | "test_run"
  | "experiment_started"
  | "experiment_completed"
  | "security_check"
  | "rbac_enforced"
  | "secret_accessed"
  | "deployment_started"
  | "deployment_completed"
  | "pr_opened"
  | "pr_approved"
  | "pr_merged";

type AuditOutcome = "success" | "failure" | "warning" | "partial";

interface AuditLogEntry {
  timestamp: string;          // ISO 8601 UTC
  action: AuditAction;
  actor: string;              // user/role/system component
  level: AuditLevel;
  resource?: string | null;   // file/PR/resource identifier
  outcome: AuditOutcome;
  details: Record<string, any>;
  metadata?: Record<string, any> & {
    duration_ms?: number;
    tags?: string[];
  };
  git_commit: string;         // first 8 chars of SHA
  branch: string;
  error?: {
    type: string;
    message: string;
    traceback?: string | null;
  } | null;
}

interface AuditLogQuery {
  action?: AuditAction;
  actor?: string;
  level?: AuditLevel;
  outcome?: AuditOutcome;
  resource?: string;
  start_date?: string;        // ISO 8601
  end_date?: string;          // ISO 8601
  limit?: number;
}

interface AuditLogStatistics {
  total_entries: number;
  date_range: {
    start: string;
    end: string;
  };
  by_action: Record<AuditAction, number>;
  by_actor: Record<string, number>;
  by_level: Record<AuditLevel, number>;
  by_outcome: Record<AuditOutcome, number>;
  error_rate: number;         // percentage
  security_events: number;
}
'''


_REQUIRED_FIELDS = {"timestamp", "action", "actor", "level", "outcome"}
_SCHEMA_PROPERTIES = cast(dict[str, dict[str, object]], AUDIT_LOG_JSON_SCHEMA["properties"])
_ALLOWED_FIELDS = set(_SCHEMA_PROPERTIES.keys())
_ALLOWED_ACTIONS = set(cast(list[str], _SCHEMA_PROPERTIES["action"]["enum"]))
_ALLOWED_LEVELS = set(cast(list[str], _SCHEMA_PROPERTIES["level"]["enum"]))
_ALLOWED_OUTCOMES = set(cast(list[str], _SCHEMA_PROPERTIES["outcome"]["enum"]))


# ========== Python Dataclass Models ==========

@dataclass
class ErrorInfo:
    """エラー情報"""
    type: str
    message: str
    traceback: str | None = None
    
    def to_dict(self) -> JsonObject:
        return cast(JsonObject, asdict(self))


@dataclass
class AuditLogMetadata:
    """監査ログメタデータ"""
    duration_ms: int | None = None
    tags: list[str] = field(default_factory=lambda: [])
    
    def to_dict(self) -> JsonObject:
        data = cast(JsonObject, asdict(self))
        return {k: v for k, v in data.items() if v is not None}


@dataclass
class AuditLogEntry:
    """監査ログエントリ"""
    timestamp: str              # ISO 8601 UTC
    action: str
    actor: str
    level: str                  # INFO, WARNING, ERROR, SECURITY, COMPLIANCE
    outcome: str                # success, failure, warning, partial
    details: JsonObject = field(default_factory=lambda: cast(JsonObject, {}))
    resource: str | None = None
    metadata: JsonObject | None = None
    git_commit: str = "unknown"
    branch: str = "unknown"
    error: JsonObject | None = None
    
    def validate(self) -> bool:
        """スキーマバリデーション"""
        is_valid, error = validate_entry(self.to_dict())
        if not is_valid and error:
            print(f"Validation error: {error}")
        return is_valid
    
    def to_dict(self) -> JsonObject:
        """辞書に変換"""
        data = {
            "timestamp": self.timestamp,
            "action": self.action,
            "actor": self.actor,
            "level": self.level,
            "outcome": self.outcome,
            "details": self.details,
            "git_commit": self.git_commit,
            "branch": self.branch,
        }
        
        if self.resource:
            data["resource"] = self.resource
        
        if self.metadata:
            data["metadata"] = self.metadata
        
        if self.error:
            data["error"] = self.error
        
        return cast(JsonObject, data)
    
    def to_json(self) -> str:
        """JSON 文字列に変換"""
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class AuditLogQuery:
    """監査ログクエリ"""
    action: str | None = None
    actor: str | None = None
    level: str | None = None
    outcome: str | None = None
    resource: str | None = None
    start_date: str | None = None  # ISO 8601
    end_date: str | None = None     # ISO 8601
    limit: int = 100
    
    def to_dict(self) -> JsonObject:
        data = cast(JsonObject, asdict(self))
        return {k: v for k, v in data.items() if v is not None}


@dataclass
class AuditLogStatistics:
    """監査ログ統計"""
    total_entries: int
    date_range: dict[str, str]
    by_action: dict[str, int]
    by_actor: dict[str, int]
    by_level: dict[str, int]
    by_outcome: dict[str, int]
    error_rate: float
    security_events: int
    
    def to_dict(self) -> JsonObject:
        return cast(JsonObject, asdict(self))
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ========== Schema Export ==========

def get_json_schema() -> dict[str, object]:
    """JSON Schema を取得"""
    return AUDIT_LOG_JSON_SCHEMA


def get_typescript_definitions() -> str:
    """TypeScript 型定義を取得"""
    return TYPE_DEFINITIONS


def _is_iso8601_datetime(value: object) -> bool:
    """ISO 8601 の日時文字列かを判定"""
    if not isinstance(value, str):
        return False

    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _validate_manual_schema(entry: JsonObject) -> tuple[bool, str | None]:
    """jsonschema 非依存の最小バリデーション"""
    missing = sorted(_REQUIRED_FIELDS - set(entry.keys()))
    if missing:
        return False, f"Missing required fields: {', '.join(missing)}"

    unexpected = sorted(set(entry.keys()) - _ALLOWED_FIELDS)
    if unexpected:
        return False, f"Unexpected fields: {', '.join(unexpected)}"

    if not _is_iso8601_datetime(entry.get("timestamp")):
        return False, "timestamp must be an ISO 8601 datetime string"

    if not isinstance(entry.get("action"), str):
        return False, "action must be a string"
    if entry["action"] not in _ALLOWED_ACTIONS:
        return False, f"Invalid action: {entry['action']}"

    if not isinstance(entry.get("actor"), str):
        return False, "actor must be a string"

    if not isinstance(entry.get("level"), str):
        return False, "level must be a string"
    if entry["level"] not in _ALLOWED_LEVELS:
        return False, f"Invalid level: {entry['level']}"

    if not isinstance(entry.get("outcome"), str):
        return False, "outcome must be a string"
    if entry["outcome"] not in _ALLOWED_OUTCOMES:
        return False, f"Invalid outcome: {entry['outcome']}"

    if (
        "resource" in entry
        and entry["resource"] is not None
        and not isinstance(entry["resource"], str)
    ):
        return False, "resource must be a string or null"

    if "details" in entry and not isinstance(entry["details"], dict):
        return False, "details must be an object"

    if (
        "metadata" in entry
        and entry["metadata"] is not None
        and not isinstance(entry["metadata"], dict)
    ):
        return False, "metadata must be an object or null"

    if "git_commit" in entry and not isinstance(entry["git_commit"], str):
        return False, "git_commit must be a string"

    if "branch" in entry and not isinstance(entry["branch"], str):
        return False, "branch must be a string"

    if "error" in entry and entry["error"] is not None:
        if not isinstance(entry["error"], dict):
            return False, "error must be an object or null"
        required_error_fields = {"type", "message"}
        missing_error_fields = sorted(required_error_fields - set(entry["error"].keys()))
        if missing_error_fields:
            return False, f"Missing error fields: {', '.join(missing_error_fields)}"

    return True, None


def validate_entry(entry: JsonObject) -> tuple[bool, str | None]:
    """ログエントリをバリデーション
    
    Args:
        entry: バリデーション対象の辞書
    
    Returns:
        (是否, エラーメッセージ or None)
    """
    return _validate_manual_schema(entry)


if __name__ == "__main__":
    print("Audit Log Schema")
    print("=" * 60)
    
    print("\n1. JSON Schema:")
    print(json.dumps(get_json_schema(), indent=2, ensure_ascii=False)[:500])
    
    print("\n2. TypeScript Definitions:")
    print(get_typescript_definitions()[:300])
    
    # テストエントリ
    entry = AuditLogEntry(
        timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        action="skill_executed",
        actor="test_user",
        level="INFO",
        outcome="success",
        details={"skill_id": "01-static-check"},
        git_commit="abc12345",
        branch="main",
    )
    
    print("\n3. Sample Entry:")
    print(entry.to_json())
    
    # バリデーション
    is_valid, error = validate_entry(entry.to_dict())
    print(f"\n4. Validation: {'✅ PASS' if is_valid else '❌ FAIL'}")
    if error:
        print(f"   Error: {error}")
