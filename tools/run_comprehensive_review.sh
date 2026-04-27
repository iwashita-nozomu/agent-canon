#!/usr/bin/env bash
# @dependency-start
# upstream design README.md shared automation index
# @dependency-end

#
# 統合コードレビューチェック実行スクリプト（v2.0）
# スキルファイル section 12 の自動化スクリプトを一括実行
# 
# 用法:
#   ./tools/run_comprehensive_review.sh [--parallel] [--report]
#
# オプション:
#   --parallel     ツールを並行実行（高速化）
#   --report       実行後、JSON レポート生成
#   --verbose      詳細ログを出力
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR%/*}"
LOG_DIR="${PROJECT_ROOT}/logs"
REPORT_DIR="${PROJECT_ROOT}/reports"

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    elif command -v python >/dev/null 2>&1; then
        PYTHON_BIN="python"
    else
        echo "python3 or python is required" >&2
        exit 127
    fi
fi

export PYTHONPATH="${PROJECT_ROOT}/python:${PYTHONPATH:-}"
export JAX_PLATFORMS="${JAX_PLATFORMS:-cpu}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-}"
export NVIDIA_VISIBLE_DEVICES="${NVIDIA_VISIBLE_DEVICES:-}"

# ファラメータ解析
RUN_PARALLEL=false
GENERATE_REPORT=false
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --parallel) RUN_PARALLEL=true; shift ;;
        --report) GENERATE_REPORT=true; shift ;;
        --verbose) VERBOSE=true; shift ;;
        --help)
            cat <<'EOF'
Usage: ./tools/run_comprehensive_review.sh [--parallel] [--report] [--verbose]

Runs static checks, tests, and workflow validators used in the comprehensive
review flow. Logs are written under ./logs/.
EOF
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ログディレクトリ作成
mkdir -p "$LOG_DIR"

# タイムスタンプ
START_TIME=$(date +%s)
START_DATE=$(date '+%Y-%m-%d %H:%M:%S')

SUCCESS_COUNT=0
FAILURE_COUNT=0

# ロギング関数
log_info() {
    echo "[$(date '+%H:%M:%S')] ℹ️  $*" | tee -a "$LOG_DIR/comprehensive_review.log"
}

log_success() {
    echo "[$(date '+%H:%M:%S')] ✅ $*" | tee -a "$LOG_DIR/comprehensive_review.log"
    ((SUCCESS_COUNT+=1))
}

log_error() {
    echo "[$(date '+%H:%M:%S')] ❌ $*" | tee -a "$LOG_DIR/comprehensive_review.log"
    ((FAILURE_COUNT+=1))
}

log_info "================================================"
log_info "🚀 Comprehensive Code Review Checks v2.0"
log_info "Start time: $START_DATE"
log_info "Python interpreter: $PYTHON_BIN"
log_info "JAX test platform: $JAX_PLATFORMS"
log_info "Parallel mode: $RUN_PARALLEL"
log_info "================================================"

# ===== Python Checks =====
log_info ""
log_info "【Python Checks】"

# Pyright
log_info "1/4️⃣ Type checking with pyright..."
if "$PYTHON_BIN" -m pyright > "$LOG_DIR/pyright.log" 2>&1; then
    log_success "pyright: OK"
else
    log_error "pyright: FAILED (see $LOG_DIR/pyright.log)"
fi

# Ruff
log_info ""
log_info "2/4️⃣ Style check with ruff..."
if "$PYTHON_BIN" -m ruff check python tests > "$LOG_DIR/ruff.log" 2>&1; then
    log_success "ruff: OK"
else
    log_error "ruff: FAILED (see $LOG_DIR/ruff.log)"
fi

# Pytest
log_info ""
log_info "3/4️⃣ Test execution..."
if "$PYTHON_BIN" -m pytest tests/ -v --tb=short > "$LOG_DIR/pytest.log" 2>&1; then
    log_success "pytest: OK"
else
    log_error "pytest: FAILED (see $LOG_DIR/pytest.log)"
fi

# ===== Extended Skill Checks =====
log_info ""
log_info "【Extended Skill Checks】"

if [ "$RUN_PARALLEL" = true ]; then
    log_info "Running tools in parallel mode..."
    
    # Background jobs
    "$PYTHON_BIN" "$SCRIPT_DIR/check_doc_test_triplet.py" > "$LOG_DIR/triplet_check.log" 2>&1 &
    PID_TRIPLET=$!
    
    "$PYTHON_BIN" "$SCRIPT_DIR/check_convention_consistency.py" > "$LOG_DIR/convention_check.log" 2>&1 &
    PID_CONVENTION=$!
    
    bash "$SCRIPT_DIR/docker_dependency_validator.sh" > "$LOG_DIR/docker_check.log" 2>&1 &
    PID_DOCKER=$!
    
    "$PYTHON_BIN" "$SCRIPT_DIR/requirement_sync_validator.py" > "$LOG_DIR/requirement_check.log" 2>&1 &
    PID_REQUIREMENT=$!
    
    # Wait for all background jobs
    if wait $PID_TRIPLET 2>/dev/null; then
        log_success "triplet check: OK"
    else
        log_error "triplet check: FAILED"
    fi
    
    if wait $PID_CONVENTION 2>/dev/null; then
        log_success "convention check: OK"
    else
        log_error "convention check: FAILED"
    fi
    
    if wait $PID_DOCKER 2>/dev/null; then
        log_success "docker check: OK"
    else
        log_error "docker check: FAILED"
    fi
    
    if wait $PID_REQUIREMENT 2>/dev/null; then
        log_success "requirement check: OK"
    else
        log_error "requirement check: FAILED"
    fi
    
else
    # Sequential execution
    log_info ""
    log_info "4/4️⃣ Doc-Test-Code Triplet Check..."
    if "$PYTHON_BIN" "$SCRIPT_DIR/check_doc_test_triplet.py" > "$LOG_DIR/triplet_check.log" 2>&1; then
        log_success "triplet check: OK"
    else
        log_error "triplet check: FAILED"
    fi
    
    log_info ""
    log_info "5️⃣/6️⃣ Convention Consistency Check..."
    if "$PYTHON_BIN" "$SCRIPT_DIR/check_convention_consistency.py" > "$LOG_DIR/convention_check.log" 2>&1; then
        log_success "convention check: OK"
    else
        log_error "convention check: FAILED"
    fi
    
    log_info ""
    log_info "6️⃣/7️⃣ Docker Dependency Validation..."
    if bash "$SCRIPT_DIR/docker_dependency_validator.sh" > "$LOG_DIR/docker_check.log" 2>&1; then
        log_success "docker check: OK"
    else
        log_error "docker check: FAILED"
    fi
    
    log_info ""
    log_info "7️⃣/8️⃣ Requirement Sync Validation..."
    if "$PYTHON_BIN" "$SCRIPT_DIR/requirement_sync_validator.py" > "$LOG_DIR/requirement_check.log" 2>&1; then
        log_success "requirement check: OK"
    else
        log_error "requirement check: FAILED"
    fi
fi

# ===== Document Checks =====
log_info ""
log_info "【Document Checks】"

log_info ""
log_info "8️⃣ Documentation checks..."
if bash "$SCRIPT_DIR/ci/run_docs_checks.sh" > "$LOG_DIR/docs_check.log" 2>&1; then
    log_success "docs-check: OK"
else
    log_error "docs-check: FAILED (see $LOG_DIR/docs_check.log)"
fi

# ===== Summary =====
END_TIME=$(date +%s)
END_DATE=$(date '+%Y-%m-%d %H:%M:%S')
ELAPSED=$((END_TIME - START_TIME))

log_info ""
log_info "================================================"
log_info "✅ Review Complete!"
log_info "================================================"
log_info "Passed: $SUCCESS_COUNT"
log_info "Failed: $FAILURE_COUNT"
log_info "Elapsed: ${ELAPSED}s"
log_info "End time: $END_DATE"
log_info ""

# Generate JSON report
if [ "$GENERATE_REPORT" = true ]; then
    mkdir -p "$REPORT_DIR"
    REPORT_FILE="$REPORT_DIR/comprehensive_review_$(date +%Y%m%d_%H%M%S).json"
    TOTAL_COUNT=$((SUCCESS_COUNT + FAILURE_COUNT))
    PASS_RATE=$(
        "$PYTHON_BIN" - <<PY
total = ${TOTAL_COUNT}
passed = ${SUCCESS_COUNT}
print(f"{(passed * 100 / total):.2f}" if total else "0.00")
PY
    )
    
    cat > "$REPORT_FILE" << EOF
{
  "metadata": {
    "title": "Comprehensive Code Review",
    "start_time": "$START_DATE",
    "end_time": "$END_DATE",
    "elapsed_seconds": $ELAPSED,
    "parallel_mode": $RUN_PARALLEL
  },
  "summary": {
    "total": ${TOTAL_COUNT},
    "passed": $SUCCESS_COUNT,
    "failed": $FAILURE_COUNT,
    "pass_rate": "${PASS_RATE}%"
  },
  "log_dir": "$LOG_DIR",
  "report_file": "$REPORT_FILE"
}
EOF
    
    log_info "Report generated: $REPORT_FILE"
fi

log_info "Log directory: $LOG_DIR"

# Exit with failure if any check failed
if [ $FAILURE_COUNT -gt 0 ]; then
    exit 1
else
    exit 0
fi
