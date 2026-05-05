#!/usr/bin/env python3
# @dependency-start
# responsibility Preserves imported jax_solver_util legacy script for provenance.
# upstream design ../README.md legacy import policy
# @dependency-end
"""
RBAC (Role-Based Access Control) — ロールベースアクセス制御

3 つのロール（Manager/Researcher/Auditor）に基づいて、
read/write/execute 権限を管理。
"""

from enum import Enum
from typing import Dict, Set, Optional
from dataclasses import dataclass, field
import json
import sys
from pathlib import Path

# error_handler をインポート
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.error_handler import ExecutionResult, ErrorCode


class Role(Enum):
    """ロール定義。"""

    MANAGER = "MANAGER"  # 完全アクセス
    RESEARCHER = "RESEARCHER"  # 読/実行、制限付き書込
    AUDITOR = "AUDITOR"  # 読のみ
    GUEST = "GUEST"  # 限定読


class Permission(Enum):
    """権限定義。"""

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DELETE = "delete"
    ADMIN = "admin"


class Resource(Enum):
    """リソース種別。"""

    PYTHON_CODE = "python_code"
    TEST_CODE = "test_code"
    EXPERIMENT = "experiment"
    RESULT = "result"
    CONFIG = "config"
    LOG = "log"
    SECURITY = "security"
    AUDIT = "audit"


@dataclass
class AccessRule:
    """アクセス規則。"""

    role: Role
    permission: Permission
    resource: Resource
    allowed: bool = True
    conditions: Dict[str, str] = field(default_factory=dict)  # 条件（例: owner など）

    def to_dict(self) -> Dict:
        """辞書形式に変換。"""
        return {
            "role": self.role.value,
            "permission": self.permission.value,
            "resource": self.resource.value,
            "allowed": self.allowed,
            "conditions": self.conditions,
        }


class RBACEngine:
    """RBAC エンジン。"""

    def __init__(self):
        """初期化。"""
        self.rules: Dict[str, AccessRule] = {}
        self._initialize_default_rules()

    def _initialize_default_rules(self) -> None:
        """デフォルト規則を初期化。"""

        # Manager: 全権限
        for resource in Resource:
            for permission in [Permission.READ, Permission.WRITE, Permission.EXECUTE,
                             Permission.DELETE, Permission.ADMIN]:
                key = f"{Role.MANAGER.value}_{permission.value}_{resource.value}"
                self.rules[key] = AccessRule(
                    role=Role.MANAGER,
                    permission=permission,
                    resource=resource,
                    allowed=True,
                )

        # Researcher: 読・実行・書込（限定）
        for resource in Resource:
            # 読: 全リソース
            key = f"{Role.RESEARCHER.value}_read_{resource.value}"
            self.rules[key] = AccessRule(
                role=Role.RESEARCHER,
                permission=Permission.READ,
                resource=resource,
                allowed=True,
            )

            # 実行: 実験・テストのみ
            if resource in [Resource.EXPERIMENT, Resource.TEST_CODE]:
                key = f"{Role.RESEARCHER.value}_execute_{resource.value}"
                self.rules[key] = AccessRule(
                    role=Role.RESEARCHER,
                    permission=Permission.EXECUTE,
                    resource=resource,
                    allowed=True,
                )

            # 書込: Python/テストコードのみ
            if resource in [Resource.PYTHON_CODE, Resource.TEST_CODE]:
                key = f"{Role.RESEARCHER.value}_write_{resource.value}"
                self.rules[key] = AccessRule(
                    role=Role.RESEARCHER,
                    permission=Permission.WRITE,
                    resource=resource,
                    allowed=True,
                )

        # Auditor: 読のみ
        for resource in Resource:
            key = f"{Role.AUDITOR.value}_read_{resource.value}"
            self.rules[key] = AccessRule(
                role=Role.AUDITOR,
                permission=Permission.READ,
                resource=resource,
                allowed=True,
            )

        # Guest: 限定読（ログ・結果のみ）
        for resource in [Resource.LOG, Resource.RESULT]:
            key = f"{Role.GUEST.value}_read_{resource.value}"
            self.rules[key] = AccessRule(
                role=Role.GUEST,
                permission=Permission.READ,
                resource=resource,
                allowed=True,
            )

    def has_permission(
        self,
        role: Role,
        permission: Permission,
        resource: Resource,
        user_id: Optional[str] = None,
    ) -> bool:
        """権限チェック。"""
        key = f"{role.value}_{permission.value}_{resource.value}"

        if key not in self.rules:
            return False

        rule = self.rules[key]
        return rule.allowed

    def grant_permission(
        self,
        role: Role,
        permission: Permission,
        resource: Resource,
    ) -> None:
        """権限を付与。"""
        key = f"{role.value}_{permission.value}_{resource.value}"
        self.rules[key] = AccessRule(
            role=role,
            permission=permission,
            resource=resource,
            allowed=True,
        )

    def revoke_permission(
        self,
        role: Role,
        permission: Permission,
        resource: Resource,
    ) -> None:
        """権限を剥奪。"""
        key = f"{role.value}_{permission.value}_{resource.value}"
        if key in self.rules:
            self.rules[key].allowed = False

    def get_role_permissions(self, role: Role) -> Dict[str, Set[str]]:
        """ロールの全権限を取得。"""
        permissions: Dict[str, Set[str]] = {}

        for resource in Resource:
            for permission in Permission:
                key = f"{role.value}_{permission.value}_{resource.value}"
                if key in self.rules and self.rules[key].allowed:
                    if resource.value not in permissions:
                        permissions[resource.value] = set()
                    permissions[resource.value].add(permission.value)

        return permissions

    def to_json(self) -> str:
        """JSON 形式で出力。"""
        data = {
            "roles": [r.value for r in Role],
            "permissions": [p.value for p in Permission],
            "resources": [r.value for r in Resource],
            "rules": {k: v.to_dict() for k, v in self.rules.items()},
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Markdown テーブルで権限マトリックスを出力。"""
        lines = []
        lines.append("# RBAC 権限マトリックス")
        lines.append("")

        # ロール別に権限を表示
        for role in Role:
            lines.append(f"## {role.value}")
            lines.append("")

            # テーブルヘッダー
            permissions_list = list(Permission)
            lines.append(
                "| リソース | " + " | ".join(p.value for p in permissions_list) + " |"
            )
            lines.append(
                "|---------|" + "|".join(["---"] * len(permissions_list)) + "|"
            )

            # テーブル内容
            for resource in Resource:
                row = [resource.value]
                for permission in permissions_list:
                    key = f"{role.value}_{permission.value}_{resource.value}"
                    if key in self.rules and self.rules[key].allowed:
                        row.append("✅")
                    else:
                        row.append("❌")
                lines.append("| " + " | ".join(row) + " |")

            lines.append("")

        return "\n".join(lines)


class RBACValidator:
    """RBAC 検証スクリプト（Skill から呼ばれる）。"""

def verify_rbac() -> ExecutionResult:
    """RBAC 設定検証。"""
    engine = RBACEngine()
    result = ExecutionResult(
        success=True,
        script_name="rbac_validator",
    )

    # 検証 1: すべてのロール/リソースについて権限が定義されているか
    for role in Role:
        for resource in Resource:
            perms = engine.get_role_permissions(role)
            if resource.value not in perms or not perms[resource.value]:
                if role in [Role.MANAGER, Role.RESEARCHER]:
                    result.add_warning(
                        code=ErrorCode.PERMISSION_DENIED,
                        message=f"ロール {role.value} にリソース {resource.value} の権限がありません",
                    )

    # 検証 2: Manager が常にフル権限を持っているか
    has_full_permission = True
    for resource in Resource:
        if not engine.has_permission(Role.MANAGER, Permission.READ, resource):
            has_full_permission = False
            result.add_error(
                code=ErrorCode.RBAC_DENIED,
                message=f"Manager が {resource.value} の READ 権限を持っていない",
            )

    if has_full_permission:
        # Set を List に変換
        manager_perms = engine.get_role_permissions(Role.MANAGER)
        researcher_perms = engine.get_role_permissions(Role.RESEARCHER)
        auditor_perms = engine.get_role_permissions(Role.AUDITOR)

        result.output = {
            "status": "RBAC configured correctly",
            "manager_permissions": {
                k: list(v) for k, v in manager_perms.items()
            },
            "researcher_permissions": {
                k: list(v) for k, v in researcher_perms.items()
            },
            "auditor_permissions": {
                k: list(v) for k, v in auditor_perms.items()
            },
        }

    return result


def main():
    """メイン処理。"""
    engine = RBACEngine()

    # 権限マトリックス表示
    print("=" * 70)
    print(engine.to_markdown())
    print("=" * 70)

    # 検証実行
    result = verify_rbac()

    if "--json" in sys.argv:
        print(result.to_json())
    else:
        print(result.to_markdown())

    result.exit_with_status()


if __name__ == "__main__":
    main()
