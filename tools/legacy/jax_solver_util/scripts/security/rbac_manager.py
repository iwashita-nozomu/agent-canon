# @dependency-start
# upstream implementation ../README.md directory index and local context contract
# @dependency-end
"""
RBAC Manager — ロールベースアクセス制御

エージェント、スキル、リソースに対するロール・権限管理。
3層レイヤー（Tenant → Role → Permission）で厳密にアクセス制御。
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum


class Tenant(Enum):
    """組織テナント"""
    INTERNAL = "internal"          # 内部開発
    RESEARCH = "research"          # 研究チーム
    GOVERNANCE = "governance"      # ガバナンス
    EXTERNAL = "external"          # 外部パートナー


class RoleLevel(Enum):
    """ロールレベル"""
    ADMIN = "admin"                # システム管理
    MAINTAINER = "maintainer"      # メンテナ
    DEVELOPER = "developer"        # 開発者
    RESEARCHER = "researcher"      # 研究者
    REVIEWER = "reviewer"          # レビュアー
    VIEWER = "viewer"              # 閲覧のみ


class PermissionType(Enum):
    """権限タイプ"""
    EXECUTE = "execute"            # 実行権限
    READ = "read"                  # 読み取り権限
    WRITE = "write"                # 書き込み権限
    DELETE = "delete"              # 削除権限
    ADMIN = "admin"                # 管理権限


class ResourceType(Enum):
    """リソースタイプ"""
    SKILL = "skill"                # Skill
    SCRIPT = "script"              # スクリプト
    EXPERIMENT = "experiment"      # 実験
    REVIEW = "review"              # コードレビュー
    AUDIT_LOG = "audit_log"        # 監査ログ
    SECRET = "secret"              # シークレット


# ========== デフォルト権限マトリックス ==========

DEFAULT_PERMISSIONS = {
    "admin": {
        "skill": ["execute", "read", "write", "delete", "admin"],
        "script": ["execute", "read", "write", "delete", "admin"],
        "experiment": ["execute", "read", "write", "delete", "admin"],
        "review": ["execute", "read", "write", "delete", "admin"],
        "audit_log": ["read", "admin"],
        "secret": ["read", "write", "admin"],
    },
    "maintainer": {
        "skill": ["execute", "read", "write"],
        "script": ["execute", "read", "write"],
        "experiment": ["execute", "read", "write"],
        "review": ["execute", "read", "write"],
        "audit_log": ["read"],
        "secret": ["read"],
    },
    "developer": {
        "skill": ["execute", "read"],
        "script": ["execute", "read"],
        "experiment": ["execute", "read"],
        "review": ["read", "write"],
        "audit_log": ["read"],
        "secret": [],
    },
    "researcher": {
        "skill": ["execute", "read"],
        "script": ["read"],
        "experiment": ["execute", "read", "write"],
        "review": ["read"],
        "audit_log": ["read"],
        "secret": [],
    },
    "reviewer": {
        "skill": ["read"],
        "script": ["read"],
        "experiment": ["read"],
        "review": ["execute", "read", "write"],
        "audit_log": ["read"],
        "secret": [],
    },
    "viewer": {
        "skill": ["read"],
        "script": ["read"],
        "experiment": ["read"],
        "review": ["read"],
        "audit_log": [],
        "secret": [],
    },
}


@dataclass
class User:
    """ユーザー情報"""
    username: str
    roles: List[str] = field(default_factory=list)
    tenant: str = "internal"
    scopes: List[str] = field(default_factory=list)  # リソースフィルター
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Role:
    """ロール定義"""
    name: str
    tenant: str
    permissions: Dict[str, List[str]] = field(default_factory=dict)
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AccessControl:
    """アクセス制御エントリ"""
    user: str
    resource_type: str
    resource_id: str
    permissions: List[str]
    grant_date: str = ""
    expires_at: Optional[str] = None


class RBACManager:
    """ロールベースアクセス制御マネージャー"""
    
    def __init__(self, config_dir: Optional[Path] = None):
        """初期化
        
        Args:
            config_dir: 設定ディレクトリ
        """
        if config_dir is None:
            config_dir = Path(os.getenv("RBAC_CONFIG_DIR", "scripts/security"))
        
        self.config_dir = config_dir
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # インメモリキャッシュ
        self.users: Dict[str, User] = {}
        self.roles: Dict[str, Role] = {}
        self.access_controls: List[AccessControl] = []
        
        # デフォルトロール初期化
        self._init_default_roles()
        self._load_config()
    
    def _init_default_roles(self) -> None:
        """デフォルトロールを初期化"""
        for role_name, permissions in DEFAULT_PERMISSIONS.items():
            self.roles[role_name] = Role(
                name=role_name,
                tenant="internal",
                permissions=permissions,
                description=f"Built-in {role_name} role",
            )
    
    def _load_config(self) -> None:
        """設定ファイルから ロール・ユーザーを読み込み"""
        users_file = self.config_dir / "users.json"
        roles_file = self.config_dir / "roles.json"
        
        if users_file.exists():
            try:
                with open(users_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for user_data in data:
                        user = User(**user_data)
                        self.users[user.username] = user
            except Exception as e:
                print(f"Warning: Failed to load users: {e}")
        
        if roles_file.exists():
            try:
                with open(roles_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for role_data in data:
                        role = Role(**role_data)
                        self.roles[role.name] = role
            except Exception as e:
                print(f"Warning: Failed to load roles: {e}")
    
    def add_user(
        self,
        username: str,
        roles: List[str],
        tenant: str = "internal",
        scopes: Optional[List[str]] = None,
    ) -> User:
        """ユーザーを追加
        
        Args:
            username: ユーザー名
            roles: ロールリスト
            tenant: テナント
            scopes: リソーススコープ
        """
        user = User(
            username=username,
            roles=roles,
            tenant=tenant,
            scopes=scopes or [],
        )
        self.users[username] = user
        self._save_users()
        return user
    
    def add_role(
        self,
        name: str,
        tenant: str,
        permissions: Dict[str, List[str]],
        description: str = "",
    ) -> Role:
        """ロールを追加
        
        Args:
            name: ロール名
            tenant: テナント
            permissions: 権限マップ
            description: 説明
        """
        role = Role(
            name=name,
            tenant=tenant,
            permissions=permissions,
            description=description,
        )
        self.roles[name] = role
        self._save_roles()
        return role
    
    def check_permission(
        self,
        username: str,
        resource_type: str,
        permission: str,
    ) -> bool:
        """権限をチェック
        
        Args:
            username: ユーザー名
            resource_type: リソースタイプ
            permission: 権限タイプ（execute, read, write, delete, admin）
        
        Returns:
            権限あり/なし
        """
        user = self.users.get(username)
        if not user or not user.enabled:
            return False
        
        # ユーザーのロール全てをチェック
        for role_name in user.roles:
            role = self.roles.get(role_name)
            if not role:
                continue
            
            permissions = role.permissions.get(resource_type, [])
            if permission in permissions:
                return True
        
        return False
    
    def get_permissions(
        self,
        username: str,
        resource_type: Optional[str] = None,
    ) -> Dict[str, List[str]]:
        """ユーザーの権限を取得
        
        Args:
            username: ユーザー名
            resource_type: 特定のリソースタイプ（省略可）
        
        Returns:
            権限マップ
        """
        user = self.users.get(username)
        if not user:
            return {}
        
        result = {}
        
        for role_name in user.roles:
            role = self.roles.get(role_name)
            if not role:
                continue
            
            for rtype, perms in role.permissions.items():
                if resource_type and rtype != resource_type:
                    continue
                
                if rtype not in result:
                    result[rtype] = set()
                
                result[rtype].update(perms)
        
        # set を list に変換
        return {k: list(v) for k, v in result.items()}
    
    def grant_permission(
        self,
        username: str,
        resource_type: str,
        resource_id: str,
        permissions: List[str],
        expires_at: Optional[str] = None,
    ) -> AccessControl:
        """特定リソースへのアクセスを許可
        
        Args:
            username: ユーザー名
            resource_type: リソースタイプ
            resource_id: リソース ID
            permissions: 権限リスト
            expires_at: 有効期限（ISO 8601）
        """
        from datetime import datetime
        
        ac = AccessControl(
            user=username,
            resource_type=resource_type,
            resource_id=resource_id,
            permissions=permissions,
            grant_date=datetime.utcnow().isoformat() + "Z",
            expires_at=expires_at,
        )
        self.access_controls.append(ac)
        return ac
    
    def revoke_permission(
        self,
        username: str,
        resource_type: str,
        resource_id: str,
    ) -> bool:
        """アクセス許可を取り消し"""
        self.access_controls = [
            ac for ac in self.access_controls
            if not (ac.user == username and ac.resource_type == resource_type
                    and ac.resource_id == resource_id)
        ]
        return True
    
    def _save_users(self) -> None:
        """ユーザー設定を保存"""
        users_file = self.config_dir / "users.json"
        with open(users_file, "w", encoding="utf-8") as f:
            data = [user.to_dict() for user in self.users.values()]
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _save_roles(self) -> None:
        """ロール設定を保存"""
        roles_file = self.config_dir / "roles.json"
        with open(roles_file, "w", encoding="utf-8") as f:
            data = [role.to_dict() for role in self.roles.values()]
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def export_config(self) -> Dict[str, Any]:
        """設定をエクスポート"""
        return {
            "users": {k: v.to_dict() for k, v in self.users.items()},
            "roles": {k: v.to_dict() for k, v in self.roles.items()},
        }


# グローバルインスタンス
_rbac_manager = None


def get_rbac_manager() -> RBACManager:
    """グローバル RBAC マネージャーを取得"""
    global _rbac_manager
    if _rbac_manager is None:
        _rbac_manager = RBACManager()
    return _rbac_manager


if __name__ == "__main__":
    print("RBAC Manager Test")
    print("=" * 60)
    
    manager = RBACManager()
    
    # ユーザー追加
    manager.add_user("alice", ["developer"], "internal")
    manager.add_user("bob", ["reviewer"], "internal")
    manager.add_user("charlie", ["admin"], "internal")
    
    print("\n1. Users:")
    for username, user in manager.users.items():
        print(f"  {username}: {user.roles}")
    
    # 権限チェック
    print("\n2. Permission Checks:")
    print(f"  alice.execute(skill): {manager.check_permission('alice', 'skill', 'execute')}")
    print(f"  alice.delete(skill): {manager.check_permission('alice', 'skill', 'delete')}")
    print(f"  bob.write(review): {manager.check_permission('bob', 'review', 'write')}")
    print(f"  charlie.admin(skill): {manager.check_permission('charlie', 'skill', 'admin')}")
    
    # パーミッション取得
    print("\n3. Alice's Permissions:")
    perms = manager.get_permissions("alice")
    for rtype, prms in perms.items():
        print(f"  {rtype}: {prms}")
    
    print("\n✅ RBAC Manager ready")
