// @dependency-start
// contract implementation
// responsibility Compares before/after python-structure-hash-report JSON artifacts.
// upstream design ../../../documents/design/python-structure-hash.md Python structural duplicate analysis policy
// downstream implementation main.rs exposes python-structure-hash-impact
// @dependency-end

use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::PathBuf;

#[derive(Debug, PartialEq, Eq)]
struct Args {
    before: PathBuf,
    after: PathBuf,
    output: Option<PathBuf>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct FindingSummary {
    hash: String,
    rank: Option<usize>,
    score: Option<usize>,
    block_kind: String,
    role: String,
    instances: Vec<String>,
    source_groups: Vec<String>,
}

pub fn run(args: &[String]) -> i32 {
    match Args::parse(args).and_then(compare_reports) {
        Ok(()) => 0,
        Err(message) => {
            eprintln!("PY_STRUCTURE_HASH_IMPACT=fail");
            eprintln!("PY_STRUCTURE_HASH_IMPACT_FINDING={message}");
            2
        }
    }
}

impl Args {
    fn parse(args: &[String]) -> Result<Self, String> {
        let mut before = None;
        let mut after = None;
        let mut output = None;
        let mut index = 0;
        while index < args.len() {
            match args[index].as_str() {
                "--before" => {
                    before = Some(PathBuf::from(value_after(args, index, "--before")?));
                    index += 2;
                }
                "--after" => {
                    after = Some(PathBuf::from(value_after(args, index, "--after")?));
                    index += 2;
                }
                "--output" => {
                    output = Some(PathBuf::from(value_after(args, index, "--output")?));
                    index += 2;
                }
                value if value.starts_with("--") => {
                    return Err(format!("unknown argument {value}"));
                }
                value => return Err(format!("unexpected positional argument {value}")),
            }
        }
        Ok(Self {
            before: before.ok_or_else(|| "--before is required".to_string())?,
            after: after.ok_or_else(|| "--after is required".to_string())?,
            output,
        })
    }
}

fn value_after(args: &[String], index: usize, flag: &str) -> Result<String, String> {
    args.get(index + 1)
        .cloned()
        .ok_or_else(|| format!("{flag} requires a value"))
}

fn compare_reports(args: Args) -> Result<(), String> {
    let before = read_json(&args.before)?;
    let after = read_json(&args.after)?;
    let before_findings = finding_map(&before);
    let after_findings = finding_map(&after);
    let before_hashes = before_findings.keys().cloned().collect::<BTreeSet<_>>();
    let after_hashes = after_findings.keys().cloned().collect::<BTreeSet<_>>();
    let removed = before_hashes
        .difference(&after_hashes)
        .filter_map(|hash| before_findings.get(hash))
        .map(finding_json)
        .collect::<Vec<_>>();
    let added = after_hashes
        .difference(&before_hashes)
        .filter_map(|hash| after_findings.get(hash))
        .map(finding_json)
        .collect::<Vec<_>>();
    let rank_changes = before_hashes
        .intersection(&after_hashes)
        .filter_map(|hash| {
            let before = before_findings.get(hash)?;
            let after = after_findings.get(hash)?;
            if before.rank == after.rank && before.score == after.score {
                return None;
            }
            Some(json!({
                "hash": hash,
                "before_rank": before.rank,
                "after_rank": after.rank,
                "before_score": before.score,
                "after_score": after.score,
                "representative_instances": after.instances,
            }))
        })
        .collect::<Vec<_>>();
    let payload = json!({
        "summary": {
            "before_groups": group_count(&before),
            "after_groups": group_count(&after),
            "delta_groups": group_count(&after) as isize - group_count(&before) as isize,
            "removed_hash_count": removed.len(),
            "added_hash_count": added.len(),
            "rank_change_count": rank_changes.len(),
            "before_repair_slice": repair_slice_summary(&before),
            "after_repair_slice": repair_slice_summary(&after),
        },
        "removed_findings": removed,
        "added_findings": added,
        "rank_changes": rank_changes,
    });
    let rendered = serde_json::to_string_pretty(&payload)
        .map_err(|error| format!("failed to render JSON: {error}"))?
        + "\n";
    if let Some(output) = args.output {
        fs::write(&output, rendered)
            .map_err(|error| format!("failed to write {}: {error}", output.display()))?;
        println!("PY_STRUCTURE_HASH_IMPACT_OUTPUT={}", output.display());
    } else {
        print!("{rendered}");
    }
    Ok(())
}

fn read_json(path: &PathBuf) -> Result<Value, String> {
    let text = fs::read_to_string(path)
        .map_err(|error| format!("failed to read {}: {error}", path.display()))?;
    serde_json::from_str(&text)
        .map_err(|error| format!("failed to parse {}: {error}", path.display()))
}

fn finding_map(payload: &Value) -> BTreeMap<String, FindingSummary> {
    let mut map = BTreeMap::new();
    if let Some(items) = payload.get("findings").and_then(Value::as_array) {
        for item in items {
            if let Some(summary) = finding_summary(item) {
                map.insert(summary.hash.clone(), summary);
            }
        }
    }
    map
}

fn finding_summary(item: &Value) -> Option<FindingSummary> {
    let hash = item.get("hash")?.as_str()?.to_string();
    let instances = item
        .get("instances")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|instance| {
                    let path = instance.get("path")?.as_str()?;
                    let line = instance.get("line_start")?.as_u64()?;
                    let end = instance.get("line_end")?.as_u64()?;
                    let qualname = instance.get("qualname")?.as_str()?;
                    Some(format!("{path}:{line}-{end}:{qualname}"))
                })
                .collect()
        })
        .unwrap_or_default();
    let priority = item.get("priority");
    Some(FindingSummary {
        hash,
        rank: priority
            .and_then(|value| value.get("rank"))
            .and_then(Value::as_u64)
            .and_then(|value| usize::try_from(value).ok()),
        score: priority
            .and_then(|value| value.get("score"))
            .and_then(Value::as_u64)
            .and_then(|value| usize::try_from(value).ok()),
        block_kind: item
            .get("block_kind")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        role: item
            .get("role")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        source_groups: priority
            .and_then(|value| value.get("source_groups"))
            .and_then(Value::as_array)
            .map(|items| {
                items
                    .iter()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect()
            })
            .unwrap_or_default(),
        instances,
    })
}

fn finding_json(item: &FindingSummary) -> Value {
    json!({
        "hash": item.hash,
        "rank": item.rank,
        "score": item.score,
        "block_kind": item.block_kind,
        "role": item.role,
        "source_groups": item.source_groups,
        "representative_instances": item.instances.iter().take(8).collect::<Vec<_>>(),
    })
}

fn group_count(payload: &Value) -> usize {
    payload
        .pointer("/summary/parsed_group_count")
        .and_then(Value::as_u64)
        .and_then(|value| usize::try_from(value).ok())
        .unwrap_or_default()
}

fn repair_slice_summary(payload: &Value) -> Value {
    let Some(slice) = payload.pointer("/summary/repair_slice") else {
        return json!(null);
    };
    json!({
        "actionability": slice.get("actionability"),
        "preferred_home_group": slice.get("preferred_home_group"),
        "root_rank": slice.pointer("/root_finding/rank"),
        "root_hash": slice.pointer("/root_finding/hash"),
        "root_instances": slice.pointer("/root_finding/representative_instances"),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compares_removed_and_added_hashes() {
        let before = json!({
            "summary": {"parsed_group_count": 1},
            "findings": [{"hash": "a", "block_kind": "Function", "role": "implementation"}]
        });
        let after = json!({
            "summary": {"parsed_group_count": 1},
            "findings": [{"hash": "b", "block_kind": "Function", "role": "implementation"}]
        });
        let before_map = finding_map(&before);
        let after_map = finding_map(&after);
        assert!(before_map.contains_key("a"));
        assert!(after_map.contains_key("b"));
    }
}
