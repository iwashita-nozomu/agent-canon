// @dependency-start
// contract implementation
// responsibility Reads existing token comparison and runtime summary evidence for the dashboard.
// upstream implementation path_resolution.rs owns Python-compatible glob expansion
// upstream implementation python_cli_integer.rs owns Python-compatible integer parsing
// downstream implementation agent_runtime_dashboard.rs composes token observations with other evidence
// @dependency-end

use crate::path_resolution::python_pathlib_glob_paths;
use crate::python_cli_integer;
use regex::{Captures, Regex};
use rustpython_ast::bigint::BigInt;
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};
use std::sync::LazyLock;
use std::time::UNIX_EPOCH;
use time::{format_description::well_known::Rfc3339, Date, Month};

static COMPARISON: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"baseline_total=(?P<baseline>\d+)\s+candidate_total=(?P<candidate>\d+)\s+token_ratio=(?P<ratio>[0-9.]+)").unwrap()
});
static MARKDOWN: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?s)baseline_total_tokens:\s*(?P<baseline>\d+).*?candidate_total_tokens:\s*(?P<candidate>\d+).*?token_ratio:\s*(?P<ratio>[0-9.]+)").unwrap()
});
static SUMMARY: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"token_usage_summary=present\s+session_count=(?P<sessions>\d+)\s+token_event_count=(?P<events>\d+)\s+total_tokens=(?P<total>\d+)\s+moving_average_window=(?P<window>\d+)\s+latest_moving_average_total=(?P<moving>[0-9.]+)\s+average_tokens_per_event=(?P<average>[0-9.]+)").unwrap()
});
static SUMMARY_MARKDOWN: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?s)TOKEN_USAGE_SESSION_COUNT=(?P<sessions>\d+).*?TOKEN_USAGE_TOKEN_EVENT_COUNT=(?P<events>\d+).*?TOKEN_USAGE_TOTAL_TOKENS=(?P<total>\d+).*?TOKEN_USAGE_AVERAGE_TOKENS_PER_EVENT=(?P<average>[0-9.]+).*?TOKEN_USAGE_MOVING_AVERAGE_WINDOW=(?P<window>\d+).*?TOKEN_USAGE_LATEST_MOVING_AVERAGE_TOTAL=(?P<moving>[0-9.]+)").unwrap()
});
static OBJECTIVE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)(?:token_efficiency_protocol\s*=\s*active|token_reduction(?:_objective)?\s*=\s*(?:selected|active|true)|objective\s*=\s*token[-_]reduction)").unwrap()
});
static OPT_OUT: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)token_efficiency_not_required\b").unwrap());
static ISO_TIME: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z").unwrap());
static RUN_TIME: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\d{8}T\d{6}(?:\d{6})?Z").unwrap());

#[derive(Clone, Debug)]
pub(crate) struct TimedIntMetric {
    pub epoch: i64,
    pub value: BigInt,
}
#[derive(Clone, Debug)]
pub(crate) struct TimedFloatMetric {
    pub epoch: i64,
    pub value: f64,
}

#[derive(Clone, Debug, Default)]
pub(crate) struct TokenUsageBreakdown {
    pub comparison_files: Vec<PathBuf>,
    pub comparison_count: usize,
    pub summary_files: Vec<PathBuf>,
    pub summary_count: usize,
    pub baseline_total_tokens: BigInt,
    pub candidate_total_tokens: BigInt,
    pub baseline_token_counts: Vec<BigInt>,
    pub candidate_token_counts: Vec<BigInt>,
    pub token_ratios: Vec<f64>,
    pub session_count: BigInt,
    pub token_event_count: BigInt,
    pub total_tokens: BigInt,
    pub latest_moving_average_total: f64,
    pub average_tokens_per_event: f64,
    pub timed_candidate_token_counts: Vec<TimedIntMetric>,
    pub timed_token_ratios: Vec<TimedFloatMetric>,
    pub objective_selected: bool,
    pub objective_not_selected: bool,
}

pub(crate) fn candidate_paths(
    root: &Path,
    runtime_root: Option<&Path>,
) -> Result<Vec<PathBuf>, String> {
    let evidence = runtime_root.unwrap_or(root);
    let mut paths = BTreeSet::new();
    for pattern in [
        "reports/agents/**/workflow_monitoring.md",
        "reports/agents/**/*token*.md",
        "reports/**/*token*.md",
        ".agent-canon/log-archive/eval-results/**/*.md",
    ] {
        for path in python_pathlib_glob_paths(&evidence.join(pattern).to_string_lossy())? {
            if path.is_file() {
                paths.insert(path);
            }
        }
    }
    Ok(paths.into_iter().collect())
}

pub(crate) fn evidence_epoch(path: &Path, text: &str) -> i64 {
    if let Some(value) = ISO_TIME.find(text) {
        return time::OffsetDateTime::parse(value.as_str(), &Rfc3339)
            .map_or(0, |value| value.unix_timestamp());
    }
    let path_text = path.to_string_lossy().replace('\\', "/");
    let Some(value) = RUN_TIME.find(&path_text) else {
        return 0;
    };
    let value = value.as_str();
    let parsed = || -> Option<i64> {
        let year = value.get(0..4)?.parse::<i32>().ok()?;
        let month = Month::try_from(value.get(4..6)?.parse::<u8>().ok()?).ok()?;
        let day = value.get(6..8)?.parse::<u8>().ok()?;
        let hour = value.get(9..11)?.parse::<u8>().ok()?;
        let minute = value.get(11..13)?.parse::<u8>().ok()?;
        let second = value.get(13..15)?.parse::<u8>().ok()?;
        Some(
            Date::from_calendar_date(year, month, day)
                .ok()?
                .with_hms(hour, minute, second)
                .ok()?
                .assume_utc()
                .unix_timestamp(),
        )
    };
    parsed().unwrap_or(0)
}

fn mtime(path: &Path) -> i64 {
    path.metadata()
        .and_then(|metadata| metadata.modified())
        .ok()
        .and_then(|value| match value.duration_since(UNIX_EPOCH) {
            Ok(value) => i64::try_from(value.as_secs()).ok(),
            Err(value) => i64::try_from(value.duration().as_secs())
                .ok()
                .map(|value| -value),
        })
        .unwrap_or(0)
}

fn integer(capture: &Captures<'_>, field: &str) -> Result<BigInt, String> {
    python_cli_integer::parse(&capture[field])
        .ok_or_else(|| format!("invalid token integer: {}", &capture[field]))
}
fn number(capture: &Captures<'_>, field: &str) -> Result<f64, String> {
    capture[field]
        .parse()
        .map_err(|error| format!("invalid token number: {}: {error}", &capture[field]))
}

pub(crate) fn read(
    root: &Path,
    cutoff: Option<i64>,
    runtime_root: Option<&Path>,
) -> Result<TokenUsageBreakdown, String> {
    let mut result = TokenUsageBreakdown::default();
    for path in candidate_paths(root, runtime_root)? {
        let text = std::fs::read_to_string(&path)
            .map_err(|error| format!("{}: {error}", path.display()))?;
        let epoch = evidence_epoch(&path, &text);
        if cutoff.is_some_and(|cutoff| {
            if epoch > 0 {
                epoch < cutoff
            } else {
                mtime(&path) < cutoff
            }
        }) {
            continue;
        }
        let selected = OBJECTIVE.is_match(&text);
        result.objective_selected |= selected;
        result.objective_not_selected |= OPT_OUT.is_match(&text) && !selected;
        let mut comparison_found = false;
        for pattern in [&*COMPARISON, &*MARKDOWN] {
            for capture in pattern.captures_iter(&text) {
                comparison_found = true;
                let baseline = integer(&capture, "baseline")?;
                let candidate = integer(&capture, "candidate")?;
                let ratio = number(&capture, "ratio")?;
                result.baseline_total_tokens += &baseline;
                result.candidate_total_tokens += &candidate;
                result.baseline_token_counts.push(baseline);
                result.candidate_token_counts.push(candidate.clone());
                result.token_ratios.push(ratio);
                if epoch > 0 {
                    result.timed_candidate_token_counts.push(TimedIntMetric {
                        epoch,
                        value: candidate,
                    });
                    result.timed_token_ratios.push(TimedFloatMetric {
                        epoch,
                        value: ratio,
                    });
                }
                result.comparison_count += 1;
            }
        }
        if comparison_found {
            result.comparison_files.push(path.clone());
        }
        let mut summary_found = false;
        for pattern in [&*SUMMARY, &*SUMMARY_MARKDOWN] {
            for capture in pattern.captures_iter(&text) {
                summary_found = true;
                result.summary_count += 1;
                result.session_count += integer(&capture, "sessions")?;
                result.token_event_count += integer(&capture, "events")?;
                result.total_tokens += integer(&capture, "total")?;
                result.latest_moving_average_total = number(&capture, "moving")?;
                result.average_tokens_per_event = number(&capture, "average")?;
            }
        }
        if summary_found {
            result.summary_files.push(path);
        }
    }
    result
        .timed_candidate_token_counts
        .sort_by_key(|value| value.epoch);
    result.timed_token_ratios.sort_by_key(|value| value.epoch);
    result.objective_not_selected |= !result.objective_selected;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn chronological_evidence_keeps_explicit_objectives_and_arbitrary_counts() {
        let temp = tempfile::tempdir().unwrap();
        let path = temp
            .path()
            .join("reports/agents/run/workflow_monitoring.md");
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        let large = "10000000000000000000000000000000000000000";
        std::fs::write(&path,format!("2026-05-01T00:00:00Z\ntoken_efficiency_protocol=active\nbaseline_total={large} candidate_total=10 token_ratio=0.5\n")).unwrap();
        let value = read(temp.path(), None, None).unwrap();
        assert_eq!(value.comparison_count, 1);
        assert_eq!(value.baseline_total_tokens.to_string(), large);
        assert!(value.objective_selected);
        assert!(!value.objective_not_selected);
        assert_eq!(
            value.timed_candidate_token_counts[0].value,
            BigInt::from(10)
        );
        assert_eq!(
            read(temp.path(), Some(2_000_000_000), None)
                .unwrap()
                .comparison_count,
            0
        );
    }
    #[test]
    fn summary_rows_keep_all_five_fields_and_latest_report_values() {
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("reports/token-summary.md");
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path,"token_usage_summary=present session_count=2 token_event_count=3 total_tokens=12 moving_average_window=2 latest_moving_average_total=8.5 average_tokens_per_event=4.0").unwrap();
        let value = read(temp.path(), None, None).unwrap();
        assert_eq!(value.summary_count, 1);
        assert_eq!(value.total_tokens, BigInt::from(12));
        assert_eq!(value.latest_moving_average_total, 8.5);
        assert_eq!(value.average_tokens_per_event, 4.0);
        assert!(value.objective_not_selected);
    }
    #[test]
    fn pathlib_reports_include_hidden_directories() {
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("reports/.hidden/token.md");
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(
            &path,
            "baseline_total=20 candidate_total=10 token_ratio=0.5",
        )
        .unwrap();
        assert_eq!(read(temp.path(), None, None).unwrap().comparison_count, 1);
    }
}
