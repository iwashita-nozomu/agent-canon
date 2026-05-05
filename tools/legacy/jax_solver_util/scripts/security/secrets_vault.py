# @dependency-start
# upstream implementation ../README.md directory index and local context contract
# @dependency-end
"""
Secrets Vault — シークレット管理システム

GitHub Secrets / 環境変数を暗号化して安全に管理。
ローカル開発環境での検証テスト用。本番環境は GitHub Secrets 推奨。
"""

import json
import os
import base64
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum


class SecretType(Enum):
    """シークレットtype"""
    API_KEY = "api_key"
    DATABASE_URL = "database_url"
    TOKEN = "token"
    PASSWORD = "password"
    CONNECTION_STRING = "connection_string"
    PRIVATE_KEY = "private_key"
    CERTIFICATE = "certificate"
    OTHER = "other"


@dataclass
class Secret:
    """シークレットエントリ"""
    name: str
    secret_type: str
    value: str
    created_at: str
    expires_at: Optional[str] = None
    tags: list[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.metadata is None:
            self.metadata = {}
    
    def is_expired(self) -> bool:
        """有効期限切れかチェック"""
        if not self.expires_at:
            return False
        expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        return datetime.utcnow() > expires
    
    def to_dict_masked(self) -> Dict[str, Any]:
        """値をマスクして辞書に変換"""
        if len(self.value) > 4:
            masked_value = "****" + self.value[-4:]
        else:
            masked_value = "****"

        return {
            "name": self.name,
            "secret_type": self.secret_type,
            "value": masked_value,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "tags": self.tags,
        }


class SecretsVault:
    """シークレット管理ボルト"""
    
    def __init__(self, vault_dir: Optional[Path] = None):
        """初期化
        
        Args:
            vault_dir: ボルトディレクトリ（環境変数 SECRETS_VAULT_DIR で設定可能）
        """
        if vault_dir is None:
            vault_dir = Path(os.getenv("SECRETS_VAULT_DIR", "scripts/security/vault"))
        
        self.vault_dir = vault_dir
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        
        self.vault_file = self.vault_dir / "secrets.json"
        self.secrets: Dict[str, Secret] = {}
        
        self._load_secrets()
    
    def _load_secrets(self) -> None:
        """ディスクからシークレットを読み込み"""
        if not self.vault_file.exists():
            return
        
        try:
            with open(self.vault_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for secret_name, secret_data in data.items():
                    # 簡易復号化（本番環境では暗号化推奨）
                    secret_data["value"] = self._decrypt_value(secret_data.get("value", ""))
                    secret = Secret(**secret_data)
                    self.secrets[secret_name] = secret
        except Exception as e:
            print(f"Warning: Failed to load secrets: {e}")
    
    def _save_secrets(self) -> None:
        """シークレットをディスクに保存"""
        data = {}
        for secret_name, secret in self.secrets.items():
            secret_data = asdict(secret)
            # 簡易暗号化（本番環境では KMS/Vault 推奨）
            secret_data["value"] = self._encrypt_value(secret.value)
            data[secret_name] = secret_data
        
        with open(self.vault_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # ボルトファイルは secret 権限で保護（Unix のみ）
        if hasattr(os, 'chmod'):
            os.chmod(self.vault_file, 0o600)
    
    def _encrypt_value(self, value: str) -> str:
        """値を簡易暗号化（本番環境には非推奨）
        
        注: これは基本的な難読化。本番環境では KMS/HashiCorp Vault 使用。
        """
        # Base64 エンコード＋環境依存プレフィックス
        encoded = base64.b64encode(value.encode()).decode()
        return f"vault:{encoded}"
    
    def _decrypt_value(self, encrypted: str) -> str:
        """値を簡易復号化"""
        if not encrypted.startswith("vault:"):
            return encrypted
        
        try:
            encoded = encrypted[6:]  # "vault:" プレフィックス削除
            decoded = base64.b64decode(encoded).decode()
            return decoded
        except Exception:
            return encrypted
    
    def set_secret(
        self,
        name: str,
        value: str,
        secret_type: str = "other",
        expires_at: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> Secret:
        """シークレットを設定
        
        Args:
            name: シークレット名
            value: 値
            secret_type: タイプ（api_key, token, etc）
            expires_at: 有効期限（ISO 8601）
            tags: タグ
        
        Returns:
            作成されたシークレット
        """
        secret = Secret(
            name=name,
            secret_type=secret_type,
            value=value,
            created_at=datetime.utcnow().isoformat() + "Z",
            expires_at=expires_at,
            tags=tags or [],
        )
        
        self.secrets[name] = secret
        self._save_secrets()
        
        return secret
    
    def get_secret(self, name: str) -> Optional[Secret]:
        """シークレットを取得
        
        Args:
            name: シークレット名
        
        Returns:
            シークレット（存在しない場合は None）
        
        Raises:
            ValueError: 有効期限切れの場合
        """
        secret = self.secrets.get(name)
        
        if secret is None:
            return None
        
        if secret.is_expired():
            raise ValueError(f"Secret '{name}' has expired")
        
        return secret
    
    def get_secret_value(self, name: str) -> Optional[str]:
        """シークレット値を直接取得"""
        secret = self.get_secret(name)
        return secret.value if secret else None
    
    def update_secret_expiry(
        self,
        name: str,
        expires_in_days: int = 90,
    ) -> Optional[Secret]:
        """有効期限を更新"""
        secret = self.secrets.get(name)
        if secret:
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
            secret.expires_at = expires_at.isoformat() + "Z"
            self._save_secrets()
        
        return secret
    
    def delete_secret(self, name: str) -> bool:
        """シークレットを削除"""
        if name in self.secrets:
            del self.secrets[name]
            self._save_secrets()
            return True
        return False
    
    def list_secrets(
        self,
        secret_type: Optional[str] = None,
        include_values: bool = False,
    ) -> list[Dict[str, Any]]:
        """シークレット一覧を取得（値は隠蔽）
        
        Args:
            secret_type: フィルタータイプ
            include_values: 値を含めるか（監査対象外）
        
        Returns:
            シークレットリスト
        """
        result = []
        
        for secret_name, secret in self.secrets.items():
            if secret_type and secret.secret_type != secret_type:
                continue
            
            if include_values:
                result.append(asdict(secret))
            else:
                result.append(secret.to_dict_masked())
        
        return result
    
    def validate_secrets(self) -> Dict[str, Any]:
        """シークレット状態を検証"""
        stats = {
            "total": len(self.secrets),
            "by_type": {},
            "expired": [],
            "expiring_soon": [],
        }
        
        now = datetime.utcnow()
        week_later = now + timedelta(days=7)
        
        for secret in self.secrets.values():
            # Type 別集計
            stype = secret.secret_type
            stats["by_type"][stype] = stats["by_type"].get(stype, 0) + 1
            
            # 有効期限チェック
            if secret.is_expired():
                stats["expired"].append(secret.name)
            elif secret.expires_at:
                expires = datetime.fromisoformat(secret.expires_at.replace("Z", "+00:00"))
                if expires < week_later:
                    stats["expiring_soon"].append({
                        "name": secret.name,
                        "expires_at": secret.expires_at,
                    })
        
        return stats
    
    def rotate_secret(
        self,
        name: str,
        new_value: str,
        keep_history: bool = False,
    ) -> Secret:
        """シークレットをローテーション
        
        Args:
            name: シークレット名
            new_value: 新しい値
            keep_history: 履歴を保持するか
        
        Returns:
            更新されたシークレット
        """
        secret = self.get_secret(name)
        if not secret:
            raise ValueError(f"Secret '{name}' not found")
        
        if keep_history:
            # 履歴ファイルに旧値を記録
            history_file = self.vault_dir / f"{name}.history.jsonl"
            with open(history_file, "a", encoding="utf-8") as f:
                history = {
                    "rotated_at": datetime.utcnow().isoformat() + "Z",
                    "old_hash": hash(secret.value),
                }
                f.write(json.dumps(history) + "\n")
        
        secret.value = new_value
        secret.created_at = datetime.utcnow().isoformat() + "Z"
        self._save_secrets()
        
        return secret


# グローバルインスタンス
_vault = None


def get_secrets_vault() -> SecretsVault:
    """グローバルボルトを取得"""
    global _vault
    if _vault is None:
        _vault = SecretsVault()
    return _vault


if __name__ == "__main__":
    print("Secrets Vault Test")
    print("=" * 60)
    
    vault = SecretsVault()
    
    # シークレット設定
    print("\n1. Setting secrets...")
    vault.set_secret(
        "github_token",
        "ghp_1234567890abcdef",
        secret_type="token",
        tags=["ci", "github"],
    )
    vault.set_secret(
        "db_connection",
        "postgresql://user:pass@localhost/db",
        secret_type="connection_string",
    )
    
    # リスト表示（マスク）
    print("\n2. Secrets (masked):")
    for secret in vault.list_secrets():
        print(f"  {secret['name']}: {secret['value']} ({secret['secret_type']})")
    
    # 取得テスト
    print("\n3. Retrieve secret:")
    token_secret = vault.get_secret("github_token")
    if token_secret:
        print(f"  Found: {token_secret.name}")
    
    # 検証
    print("\n4. Validation:")
    stats = vault.validate_secrets()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    
    print("\n✅ Secrets Vault ready")
