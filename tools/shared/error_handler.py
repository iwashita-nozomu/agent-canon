#!/usr/bin/env python3
"""
共通エラーハンドリング・実行結果標準

すべてのスクリプト（Skill など）が統一してこのクラスを使用。
目的: エラー報告、成功/失敗の一貫した表現、JSON/Markdown 出力
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
import json
import sys


class Severity(Enum):
    """エラー/警告の重大度レベル。"""

    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"


class ErrorCode(Enum):
    """プロジェクト統一エラーコード体系。"""

    # 共通
    SUCCESS = "E0000"
    UNKNOWN = "E0001"
    TIMEOUT = "E0002"
    INVALID_INPUT = "E0003"
    PERMISSION_DENIED = "E0004"

    # Type Checker
    TYPE_ERROR = "E1001"
    TYPE_MISMATCH = "E1002"
    MISSING_ANNOTATION = "E1003"

    # Linter
    LINT_VIOLATION = "E2001"
    STYLE_ERROR = "E2002"
    NO_DOCSTRING = "E2003"

    # Test
    TEST_FAILED = "E3001"
    TEST_NOT_FOUND = "E3002"
    LOW_COVERAGE = "E3003"

    # Docker
    DOCKER_BUILD_FAILED = "E4001"
    DOCKER_NO_IMAGE = "E4002"
    DEPENDENCY_MISMATCH = "E4003"

    # Experiment
    EXPERIMENT_SETUP_FAILED = "E5001"
    EXPERIMENT_RUN_FAILED = "E5002"
    RESULT_INVALID = "E5003"

    # Security
    SECURITY_VIOLATION = "E6001"
    SECRET_DETECTED = "E6002"
    RBAC_DENIED = "E6003"


@dataclass
class ErrorDetail:
    """エラー詳細情報。"""

    code: ErrorCode
    message: str
    file: Optional[str] = None
    line: Optional[int] = None
    context: Optional[Dict[str, Any]] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換。"""
        return {
            "code": self.code.value,
            "message": self.message,
            "file": self.file,
            "line": self.line,
            "context": self.context,
            "suggestion": self.suggestion,
        }


@dataclass
class ExecutionResult:
    """スクリプト実行結果の標準形式。"""

    # 基本情報
    success: bool
    script_name: str
    execution_time: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # 結果データ
    output: Optional[Dict[str, Any]] = None
    errors: List[ErrorDetail] = field(default_factory=list)
    warnings: List[ErrorDetail] = field(default_factory=list)

    # メタデータ
    version: str = "1.0"
    tags: List[str] = field(default_factory=list)

    def add_error(
        self,
        code: ErrorCode,
        message: str,
        file: Optional[str] = None,
        line: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        suggestion: Optional[str] = None,
    ) -> None:
        """エラーを追加。"""
        error = ErrorDetail(
            code=code,
            message=message,
            file=file,
            line=line,
            context=context,
            suggestion=suggestion,
        )
        self.errors.append(error)
        self.success = False

    def add_warning(
        self,
        code: ErrorCode,
        message: str,
        file: Optional[str] = None,
        line: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        suggestion: Optional[str] = None,
    ) -> None:
        """警告を追加。"""
        warning = ErrorDetail(
            code=code,
            message=message,
            file=file,
            line=line,
            context=context,
            suggestion=suggestion,
        )
        self.warnings.append(warning)

    def get_status(self) -> str:
        """ステータス取得 (PASS/WARN/FAIL)。"""
        if self.success and not self.warnings:
            return "PASS"
        elif self.success and self.warnings:
            return "WARN"
        else:
            return "FAIL"

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換。"""
        return {
            "success": self.success,
            "status": self.get_status(),
            "script_name": self.script_name,
            "execution_time": self.execution_time,
            "timestamp": self.timestamp,
            "output": self.output,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "version": self.version,
            "tags": self.tags,
        }

    def to_json(self, indent: bool = True) -> str:
        """JSON 形式で出力。"""
        data = self.to_dict()
        return json.dumps(data, indent=2 if indent else None, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Markdown 形式で出力。"""
        lines = []
        lines.append(f"# {self.script_name}")
        lines.append(f"")
        lines.append(f"**ステータス**: {self.get_status()}")
        lines.append(f"**実行時間**: {self.execution_time:.2f} 秒")
        lines.append(f"**タイムスタンプ**: {self.timestamp}")
        lines.append(f"")

        if self.output:
            lines.append("## 出力")
            lines.append("```json")
            lines.append(json.dumps(self.output, indent=2, ensure_ascii=False))
            lines.append("```")
            lines.append(f"")

        if self.errors:
            lines.append(f"## エラー ({len(self.errors)}個)")
            for i, error in enumerate(self.errors, 1):
                lines.append(f"### {i}. {error.code.value}: {error.message}")
                if error.file:
                    lines.append(f"   ファイル: {error.file}:{error.line}")
                if error.suggestion:
                    lines.append(f"   💡 対応: {error.suggestion}")
                lines.append(f"")

        if self.warnings:
            lines.append(f"## 警告 ({len(self.warnings)}個)")
            for i, warning in enumerate(self.warnings, 1):
                lines.append(f"### {i}. {warning.code.value}: {warning.message}")
                if warning.file:
                    lines.append(f"   ファイル: {warning.file}:{warning.line}")
                if warning.suggestion:
                    lines.append(f"   💡 対応: {warning.suggestion}")
                lines.append(f"")

        return "\n".join(lines)

    def exit_with_status(self) -> None:
        """実行結果でプロセス終了。"""
        if self.success and not self.warnings:
            sys.exit(0)
        elif self.success and self.warnings:
            print(f"⚠️ Warning: {len(self.warnings)}個の警告", file=sys.stderr)
            sys.exit(0)
        else:
            print(f"❌ Error: {len(self.errors)}個のエラー", file=sys.stderr)
            sys.exit(1)


# ============================================================================
# 使用例
# ============================================================================

if __name__ == "__main__":
    # 例 1: 成功結果
    result = ExecutionResult(
        success=True,
        script_name="test_checker",
        execution_time=2.34,
    )
    result.output = {"passed": 10, "failed": 0}
    result.add_warning(
        code=ErrorCode.LOW_COVERAGE,
        message="テストカバレッジが 80% 未満",
        file="src/utils.py",
        suggestion="テストケースを追加してください",
    )

    print("=== Markdown 出力 ===")
    print(result.to_markdown())

    print("\n=== JSON 出力 ===")
    print(result.to_json())

    print(f"\n=== ステータス ===")
    print(f"Success: {result.success}")
    print(f"Status: {result.get_status()}")
    print(f"Errors: {len(result.errors)}")
    print(f"Warnings: {len(result.warnings)}")
