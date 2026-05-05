#!/bin/bash
# @dependency-start
# responsibility Preserves imported jax_solver_util legacy script for provenance.
# upstream design ../README.md legacy import policy
# @dependency-end
set -euo pipefail

read -p "Enter new repository name: " REPO_NAME

mkdir -p ./python/${REPO_NAME}

# touch ./python/${REPO_NAME}/__init__.py
# git add ./python/${REPO_NAME}/__init__.py
# git commit -m "chore: add ${REPO_NAME} package"

./scripts/create_toml.sh "${REPO_NAME}"

REMOTE_BASE="/mnt/git"
NEW_REMOTE="${REMOTE_BASE}/${REPO_NAME}.git"

# 前提チェック：template を clone した repo か
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: not inside a git repository."
  exit 1
fi

echo "[INFO] Creating bare repository: $NEW_REMOTE"

if [ -e "$NEW_REMOTE" ]; then
  echo "ERROR: '$NEW_REMOTE' already exists."
  exit 1
fi

# 新しい bare repo を /mnt/git に作る

mkdir -p "$NEW_REMOTE"
git init --bare "$NEW_REMOTE"

# origin を付け替える（= 以後の git push はここへ）
OLD_ORIGIN="$(git remote get-url origin 2>/dev/null || true)"
git remote set-url origin "$NEW_REMOTE"

echo "[INFO] origin changed:"
echo "  $OLD_ORIGIN"
echo "  -> $NEW_REMOTE"

# template remote を /mnt/git/template.git に固定し、push を無効化
TEMPLATE_URL="/mnt/git/template.git"
if git remote | grep -qx template; then
  git remote set-url template "$TEMPLATE_URL"
else
  git remote add template "$TEMPLATE_URL"
fi
git remote set-url --push template DISABLE

# 初回 push（テンプレの履歴込み）
BRANCH="$(git branch --show-current)"
git push -u origin "$BRANCH"

git branch -m main

git push -u origin main

git add .
git commit -m "chore: initialize ${REPO_NAME} repository"

echo "[OK] New project repository '$REPO_NAME' is ready."
