#!/bin/bash
# @dependency-start
# responsibility Preserves imported jax_solver_util legacy script for provenance.
# upstream design ../README.md legacy import policy
# @dependency-end

# VS Code キャッシュクリーニングスクリプト
# 定期的に実行して VS Code の動作を軽く保つ

echo "Starting VS Code cache cleanup..."

# キャッシュディレクトリを削除
if [ -d ~/.vscode-server ]; then
    rm -rf ~/.vscode-server
    echo "✓ ~/.vscode-server 削除完了"
fi

# Pylance キャッシュを清掃
if [ -d ~/.pylance-cache ]; then
    rm -rf ~/.pylance-cache
    echo "✓ ~/.pylance-cache 削除完了"
fi

# Node.js キャッシュ
if [ -d ~/.node-gyp ]; then
    rm -rf ~/.node-gyp
    echo "✓ ~/.node-gyp 削除完了"
fi

echo "Cleanup complete! VS Code cache has been cleared."
