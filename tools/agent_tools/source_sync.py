#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Owns one-shot source and immutable registry-image synchronization.
# upstream design ../../documents/runtime/bootstrap-runtime.md source sync lifecycle
# upstream implementation ./bootstrap_runtime.py shared lifecycle and Docker adapter
# downstream implementation ../../bootstrap.sh host command entrypoint
# @dependency-end
"""One-shot AgentCanon source and registry-image synchronization."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

try:
    from .bootstrap_runtime import BootstrapError, BootstrapRuntime, _atomic_json, _now
except ImportError:  # direct script/module compatibility
    from bootstrap_runtime import (  # type: ignore[no-redef]
        BootstrapError,
        BootstrapRuntime,
        _atomic_json,
        _now,
    )


class SourceSync:
    """Own the live shallow-checkout and immutable OCI update transaction."""

    def __init__(
        self,
        runtime: BootstrapRuntime,
        install_root: Path,
        *,
        remote: str = "origin",
        branch: str = "main",
    ) -> None:
        self.runtime = runtime
        self.install_root = install_root.resolve()
        self.remote = remote
        self.branch = branch

    def _git(
        self,
        argv: list[str],
        *,
        cwd: Path | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *argv],
            cwd=str(cwd or self.install_root),
            check=False,
            capture_output=True,
            text=True,
        )
        if check and result.returncode:
            raise BootstrapError(
                "source_sync_git_failed",
                f"git operation failed: git {' '.join(argv[:3])}",
                evidence={"exit": result.returncode},
            )
        return result

    def _source_identity(self, root: Path) -> tuple[str, str]:
        head = self._git(["rev-parse", "--verify", "HEAD"], cwd=root).stdout.strip()
        tree = self._git(["rev-parse", "--verify", "HEAD^{tree}"], cwd=root).stdout.strip()
        if len(head) != 40 or len(tree) != 40:
            raise BootstrapError("source_sync_git_failed", "source identity is not a full Git identity")
        return head, tree

    def _require_live_checkout(self) -> tuple[str, str]:
        if self.install_root.is_symlink() or not self.install_root.is_dir():
            raise BootstrapError("install_root_invalid", "live install root must be a directory")
        if not (self.install_root / ".git").exists():
            raise BootstrapError("install_root_not_git", "live install root must retain .git")
        status = self._git(["status", "--porcelain"], cwd=self.install_root).stdout
        if status:
            raise BootstrapError("install_root_dirty", "live install root has uncommitted changes")
        shallow = self._git(["rev-parse", "--is-shallow-repository"], cwd=self.install_root).stdout.strip()
        count = self._git(["rev-list", "--count", "HEAD"], cwd=self.install_root).stdout.strip()
        if shallow != "true" or count != "1":
            raise BootstrapError(
                "install_root_not_shallow",
                "live install root must be a clean depth-one checkout",
                evidence={"shallow": shallow, "commit_count": count},
            )
        return self._source_identity(self.install_root)

    def _remote_head(self) -> tuple[str, str]:
        result = self._git(
            ["ls-remote", self.remote, f"refs/heads/{self.branch}"],
            cwd=self.install_root,
        )
        fields = result.stdout.split()
        if len(fields) < 2 or len(fields[0]) != 40:
            raise BootstrapError("source_remote_unavailable", "remote main branch has no full commit")
        remote_url = self._git(["remote", "get-url", self.remote], cwd=self.install_root).stdout.strip()
        if not remote_url:
            raise BootstrapError("source_remote_unavailable", "remote URL is empty")
        return fields[0], remote_url

    def _registry_image(self, source_head: str) -> str:
        registry = self.runtime.manifest.get("registry", {})
        image = registry.get("image") if isinstance(registry, dict) else None
        if not isinstance(image, str) or not image:
            raise BootstrapError("registry_manifest_invalid", "manifest.registry.image is required")
        return f"{image}:sha-{source_head}"

    def _pull(self, image_ref: str) -> dict[str, Any]:
        config = self.runtime.paths.docker_config
        try:
            try:
                record = self.runtime.docker.pull_image(image_ref)
            except BootstrapError as anonymous_error:
                # GHCR private authentication is temporary and runtime-local.
                if config.exists():
                    shutil.rmtree(config)
                config.mkdir(parents=True, mode=0o700)
                os.chmod(config, 0o700)
                token = subprocess.run(
                    ["gh", "auth", "token"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                user = subprocess.run(
                    ["gh", "api", "user", "--jq", ".login"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if token.returncode or user.returncode or not token.stdout.strip() or not user.stdout.strip():
                    raise anonymous_error
                self.runtime.docker.run(
                    [self.runtime.docker.executable, "login", "ghcr.io", "--username", user.stdout.strip(), "--password-stdin"],
                    environment={"DOCKER_CONFIG": str(config)},
                    stdin=token.stdout.strip() + "\n",
                )
                record = self.runtime.docker.pull_image(image_ref, docker_config=config)
            self.runtime.docker.validate_registry_image(
                record,
                source_head=image_ref.rsplit(":sha-", 1)[-1],
                image_ref=image_ref,
            )
            return record
        finally:
            if config.exists():
                shutil.rmtree(config)

    def _remove_exact(self, path: Path) -> None:
        if not path.exists() and not path.is_symlink():
            return
        if path.is_symlink() or not path.resolve().is_relative_to(self.runtime.paths.runtime_root.resolve()):
            raise BootstrapError("source_sync_path_rejected", f"owned staging path is unsafe: {path}")
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    def _write_sync_state(self, payload: dict[str, Any]) -> None:
        _atomic_json(self.runtime.paths.source_sync, {"schema": "agent-canon.source-sync.v1", **payload})

    def _run_candidate_bootstrap(self, image_digest: str) -> None:
        common = [
            str(self.install_root / "bootstrap.sh"),
            "--control-parent-root",
            str(self.runtime.paths.control_parent_root),
            "--runtime-root",
            str(self.runtime.paths.runtime_root),
        ]
        commands = (
            [
                *common,
                "update",
                "--source-sync",
                "--image-ref",
                image_digest,
            ],
            [*common, "start"],
            [*common, "codex", "prepare"],
        )
        environment = {**os.environ, "AGENT_CANON_LOCK_HELD": "1"}
        for args in commands:
            result = subprocess.run(
                args, check=False, capture_output=True, text=True, env=environment
            )
            if result.returncode:
                raise BootstrapError(
                    "candidate_bootstrap_failed",
                    f"candidate bootstrap command failed: {args[-2] if len(args) > 1 else args[-1]}",
                    evidence={"exit": result.returncode},
                )

    def sync(self) -> dict[str, Any]:
        """Synchronize source and image once; unchanged main is a no-op."""
        with self.runtime.locked():
            state = self.runtime._read_state(allow_manifest_drift=True)
            old_head, old_tree = self._require_live_checkout()
            target_head, remote_url = self._remote_head()
            if target_head == old_head:
                payload = {
                    "source_root": str(self.install_root),
                    "source_head": old_head,
                    "source_tree": old_tree,
                    "status": "unchanged",
                    "updated_at": _now(),
                }
                self._write_sync_state(payload)
                return {"code": "unchanged", **payload}
            staging = self.runtime.paths.source_staging
            backup = self.runtime.paths.source_backup
            self._remove_exact(staging)
            self._remove_exact(backup)
            staging.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            backup.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            try:
                self._git(
                    ["clone", "--depth=1", "--single-branch", "--branch", self.branch, remote_url, str(staging)],
                    cwd=self.runtime.paths.runtime_root,
                )
                staged_head, staged_tree = self._source_identity(staging)
                if staged_head != target_head:
                    raise BootstrapError("source_sync_git_failed", "staged checkout differs from remote main")
                count = self._git(["rev-list", "--count", "HEAD"], cwd=staging).stdout.strip()
                if count != "1":
                    raise BootstrapError("source_sync_git_failed", "staged checkout accumulated history")
                image_ref = self._registry_image(staged_head)
                record = self._pull(image_ref)
                correspondence = self.runtime.docker.validate_registry_image(
                    record, source_head=staged_head, image_ref=image_ref
                )
                digest = correspondence["image_repo_digest"]
                os.rename(self.install_root, backup)
                os.rename(staging, self.install_root)
                try:
                    self._run_candidate_bootstrap(digest)
                except BootstrapError:
                    current = self.runtime._read_state(allow_manifest_drift=True)
                    self.runtime._stop_owned_container(current)
                    self.runtime._write_state(state)
                    os.rename(self.install_root, staging)
                    os.rename(backup, self.install_root)
                    restored = self.runtime._read_state(allow_manifest_drift=True)
                    self.runtime._ensure_container(restored, start=bool(state.get("state") in {"ready", "running"}))
                    self.runtime._write_state(restored)
                    self._remove_exact(staging)
                    raise
                payload = {
                    "source_root": str(self.install_root),
                    "source_head": staged_head,
                    "source_tree": staged_tree,
                    "image_ref": image_ref,
                    "image_id": correspondence["image_id"],
                    "image_repo_digest": digest,
                    "image_os": correspondence["image_os"],
                    "image_architecture": correspondence["image_architecture"],
                    "status": "active",
                    "updated_at": _now(),
                }
                self._write_sync_state(payload)
                self._remove_exact(backup)
                self._remove_exact(staging)
                return {"code": "updated", **payload}
            except Exception as exc:
                if not isinstance(exc, BootstrapError):
                    raise BootstrapError("source_sync_failed", "source synchronization failed") from exc
                failed = {"status": "failed", "updated_at": _now(), "failure": exc.code}
                self._write_sync_state(failed)
                raise
