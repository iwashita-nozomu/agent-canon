// @dependency-start
// contract implementation
// responsibility Inventories branch, PR, and worktree lifecycle facts and validates exact cleanup selections.
// upstream design ../../../../../documents/operations/orphan-lifecycle.md owns semantic classification
// upstream implementation ./python_json.rs owns compatible canonical serialization
// downstream test ../../../../../tests/agent_tools/test_orphan_lifecycle.py verifies public Git fixtures
// @dependency-end

use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

const INVENTORY: &str = "agent_canon.orphan_inventory.v1";
const TRACE: &str = "agent_canon.orphan_trace.v1";
const ADMISSION: &str = "agent_canon.orphan_cleanup_admission.v1";
const POLICY: &str = "documents/operations/orphan-lifecycle.md";
type Result<T> = std::result::Result<T, String>;
fn digest(value: &Value) -> String {
    format!(
        "sha256:{:x}",
        Sha256::digest(serde_json::to_vec(value).expect("JSON serializes"))
    )
}
fn inventory_digest(value: &Value) -> String {
    let mut value = value.clone();
    value.as_object_mut().unwrap().remove("inventory_digest");
    digest(&value)
}
fn git_output(root: &Path, args: &[&str]) -> Result<Output> {
    Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .map_err(|error| error.to_string())
}
fn git_bytes(root: &Path, args: &[&str]) -> Result<Vec<u8>> {
    let output = git_output(root, args)?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).trim().to_owned());
    }
    Ok(output.stdout)
}
fn git(root: &Path, args: &[&str]) -> Result<String> {
    String::from_utf8(git_bytes(root, args)?).map_err(|error| error.to_string())
}
fn text<'a>(value: &'a Value, field: &str) -> &'a str {
    value.get(field).and_then(Value::as_str).unwrap_or("")
}
fn list(value: &Value, field: &str) -> Vec<Value> {
    value
        .get(field)
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
}
fn strings(value: &Value, field: &str) -> BTreeSet<String> {
    list(value, field)
        .into_iter()
        .filter_map(|value| value.as_str().map(str::to_owned))
        .collect()
}
fn branch(reference: &str) -> String {
    reference
        .strip_prefix("refs/heads/")
        .map(str::to_owned)
        .unwrap_or_else(|| {
            reference
                .strip_prefix("refs/remotes/")
                .unwrap_or(reference)
                .split_once('/')
                .map_or_else(
                    || {
                        reference
                            .strip_prefix("refs/remotes/")
                            .unwrap_or(reference)
                            .to_owned()
                    },
                    |(_, value)| value.into(),
                )
        })
}
fn read_json(path: &Path) -> Result<Value> {
    let raw: Value = serde_json::from_slice(&fs::read(path).map_err(|error| error.to_string())?)
        .map_err(|error| error.to_string())?;
    if !raw.is_object() {
        return Err("JSON root must be an object".into());
    }
    Ok(raw)
}
fn valid_strings(value: Option<&Value>, field: &str) -> Result<Vec<String>> {
    value
        .and_then(Value::as_array)
        .ok_or_else(|| format!("{field} must be a string list"))?
        .iter()
        .map(|value| {
            value
                .as_str()
                .filter(|value| !value.is_empty())
                .map(str::to_owned)
                .ok_or_else(|| format!("{field} must be a string list"))
        })
        .collect()
}
fn trace(path: Option<&Path>) -> Result<Value> {
    let Some(path) = path else {
        return Ok(json!({"schema":TRACE,"records":[],"pull_requests":[]}));
    };
    let raw = read_json(path)?;
    if raw["schema"] != TRACE {
        return Err(format!("trace schema must be {TRACE}"));
    }
    let records = raw["records"]
        .as_array()
        .ok_or("trace records and pull_requests must be lists")?;
    let prs = raw["pull_requests"]
        .as_array()
        .ok_or("trace records and pull_requests must be lists")?;
    let mut normalized = Vec::new();
    for record in records {
        let selector = record
            .get("selector")
            .and_then(Value::as_object)
            .filter(|value| value.len() == 1)
            .ok_or("trace selector must contain exactly one field")?;
        let (key, value) = selector.iter().next().unwrap();
        if ![
            "candidate_id",
            "branch",
            "ref",
            "pr_number",
            "worktree_path",
        ]
        .contains(&key.as_str())
        {
            return Err(format!("unsupported trace selector: {key}"));
        }
        if key == "pr_number" {
            if !value.as_u64().is_some_and(|value| value > 0) {
                return Err("trace pr_number must be positive".into());
            }
        } else if value.as_str().is_none_or(str::is_empty) {
            return Err(format!("trace selector {key} must be non-empty"));
        }
        let owners: BTreeSet<_> =
            valid_strings(record.get("active_owners"), "trace active_owners")?
                .into_iter()
                .collect();
        let mut successors = Vec::new();
        for successor in record
            .get("successors")
            .and_then(Value::as_array)
            .ok_or("trace successors must be a list")?
        {
            if text(successor, "id").is_empty() {
                return Err("trace successor id must be non-empty".into());
            }
            if !["complete", "partial", "unknown"].contains(&text(successor, "coverage")) {
                return Err("trace successor coverage is invalid".into());
            }
            successors.push(json!({"id":successor["id"],"coverage":successor["coverage"]}));
        }
        successors.sort_by(|left, right| text(left, "id").cmp(text(right, "id")));
        if !["resolved", "unresolved", "unknown"].contains(&text(record, "requirement_state")) {
            return Err("trace requirement_state is invalid".into());
        }
        if !record["resolution"].is_null()
            && record["resolution"].as_str().is_none_or(str::is_empty)
        {
            return Err("trace resolution must be null or non-empty".into());
        }
        let owner = record
            .get("worktree_owner")
            .and_then(Value::as_str)
            .unwrap_or("unknown");
        if !["runtime", "user", "unknown"].contains(&owner) {
            return Err("trace worktree_owner is invalid".into());
        }
        normalized.push(json!({"selector":selector,"active_owners":owners,"successors":successors,"requirement_state":record["requirement_state"],"resolution":record["resolution"],"worktree_owner":owner}));
    }
    let mut normalized_prs = BTreeMap::new();
    for pr in prs {
        let number = pr
            .get("number")
            .and_then(Value::as_u64)
            .filter(|value| *value > 0)
            .ok_or("pull request number must be positive")?;
        if !["open", "closed", "merged"].contains(&text(pr, "state")) {
            return Err("pull request state is invalid".into());
        }
        for key in ["head_ref", "head_sha", "url"] {
            if text(pr, key).is_empty() {
                return Err(format!("pull request {key} must be non-empty"));
            }
        }
        if normalized_prs.insert(number,json!({"number":number,"head_ref":pr["head_ref"],"head_sha":pr["head_sha"],"state":pr["state"],"url":pr["url"]})).is_some() { return Err("pull request numbers must be unique".into()); }
    }
    Ok(
        json!({"schema":TRACE,"records":normalized,"pull_requests":normalized_prs.into_values().collect::<Vec<_>>()}),
    )
}
fn relation(trace: &Value, candidate: &Value) -> Value {
    let matches: Vec<_> = list(trace, "records")
        .into_iter()
        .filter(|record| {
            let (key, value) = record["selector"]
                .as_object()
                .unwrap()
                .iter()
                .next()
                .unwrap();
            candidate[if key == "worktree_path" { "path" } else { key }] == *value
        })
        .collect();
    if matches.len() != 1 {
        return json!({"active_owners":[],"successors":[],"requirement_state":"unknown","resolution":null,"worktree_owner":"unknown","status":if matches.is_empty(){"unknown"}else{"ambiguous"},"blockers":[if matches.is_empty(){"ownership_successor_trace_missing"}else{"ownership_successor_trace_ambiguous"}]});
    }
    let mut result = matches[0].clone();
    result.as_object_mut().unwrap().remove("selector");
    let successors = list(&result, "successors");
    let mut blockers = Vec::new();
    if successors.len() > 1 {
        blockers.push("successor_trace_ambiguous");
    }
    if successors
        .iter()
        .any(|value| value["coverage"] == "unknown")
    {
        blockers.push("successor_coverage_unknown");
    }
    result["status"] = json!(if blockers.is_empty() {
        "known"
    } else {
        "ambiguous"
    });
    result["blockers"] = json!(blockers);
    result
}
fn semantic_unknown(commit: &str, error: &str) -> Value {
    json!({"status":"unknown","basis":"unverifiable","candidate_commit":commit,"merge_base":null,"ahead_commits":null,"behind_commits":null,"patch_equivalent_commits":null,"unique_patch_commits":null,"surface_equivalent":null,"changed_surface":[],"error":error})
}
fn semantic(root: &Path, main: &str, candidate: &str) -> Value {
    let evaluate = || -> Result<Value> {
        if !git_output(
            root,
            &["cat-file", "-e", &format!("{candidate}^{{commit}}")],
        )?
        .status
        .success()
        {
            return Err("candidate_commit_missing".into());
        }
        let base = git(root, &["merge-base", main, candidate])?
            .trim()
            .to_owned();
        let counts = git(
            root,
            &[
                "rev-list",
                "--left-right",
                "--count",
                &format!("{main}...{candidate}"),
            ],
        )?;
        let counts: Vec<_> = counts
            .split_whitespace()
            .map(str::parse::<u64>)
            .collect::<std::result::Result<_, _>>()
            .map_err(|error| error.to_string())?;
        if counts.len() != 2 {
            return Err("invalid commit counts".into());
        }
        let cherry = git(root, &["cherry", main, candidate])?;
        let equivalent = cherry.lines().filter(|line| line.starts_with('-')).count();
        let unique = cherry.lines().filter(|line| line.starts_with('+')).count();
        let changes = git_bytes(
            root,
            &[
                "diff",
                "--name-status",
                "-z",
                "--no-renames",
                &base,
                candidate,
            ],
        )?;
        let tokens: Vec<_> = changes
            .split(|value| *value == 0)
            .filter(|value| !value.is_empty())
            .map(|value| String::from_utf8_lossy(value).into_owned())
            .collect();
        let mut surface = Vec::new();
        let mut same = true;
        for pair in tokens.as_chunks::<2>().0 {
            surface.push(json!({"status":pair[0],"path":pair[1]}));
            if git_bytes(root, &["ls-tree", "-z", candidate, "--", &pair[1]])?
                != git_bytes(root, &["ls-tree", "-z", main, "--", &pair[1]])?
            {
                same = false;
            }
        }
        let ancestor = git_output(root, &["merge-base", "--is-ancestor", candidate, main])?
            .status
            .success();
        let (status, basis) = if ancestor || counts[1] == 0 {
            ("none", "reachable_from_main")
        } else if unique == 0 && equivalent > 0 {
            ("none", "patch_equivalent")
        } else if same {
            ("none", "surface_equivalent")
        } else {
            ("present", "unique_patch_and_surface_delta")
        };
        Ok(
            json!({"status":status,"basis":basis,"candidate_commit":candidate,"merge_base":base,"ahead_commits":counts[1],"behind_commits":counts[0],"patch_equivalent_commits":equivalent,"unique_patch_commits":unique,"surface_equivalent":same,"changed_surface":surface,"error":null}),
        )
    };
    evaluate().unwrap_or_else(|error| semantic_unknown(candidate, &error))
}
fn unpushed(root: &Path, reference: &str) -> Value {
    git(
        root,
        &["rev-list", "--count", reference, "--not", "--remotes"],
    )
    .ok()
    .and_then(|value| value.trim().parse::<u64>().ok())
    .map_or(Value::Null, |value| json!(value))
}
fn classify(candidate: &mut Value) {
    let semantic = &candidate["semantic_diff"];
    let user = &candidate["user_state"];
    let relation = &candidate["trace"];
    let mut owners = strings(relation, "active_owners");
    owners.extend(strings(candidate, "implicit_active_owners"));
    let mut blockers = strings(relation, "blockers");
    let protections = [
        ("primary_worktree", user["primary_worktree"] == true),
        ("user_managed_worktree", user["worktree_owner"] == "user"),
        ("dirty_worktree", user["dirty"] == true),
        (
            "untracked_worktree_state",
            !user["untracked_count"].is_null() && user["untracked_count"] != 0,
        ),
        (
            "unpushed_local_commits",
            !user["unpushed_commits"].is_null() && user["unpushed_commits"] != 0,
        ),
        (
            "dirty_linked_worktree",
            !list(user, "dirty_linked_worktrees").is_empty(),
        ),
    ];
    for (name, present) in protections {
        if present {
            blockers.insert(name.into());
        }
    }
    if user["status"] == "unknown" {
        blockers.insert("user_state_unverifiable".into());
    }
    if candidate["kind"] == "local_branch" && !list(user, "linked_worktrees").is_empty() {
        blockers.insert("linked_worktree_must_be_cleaned_first".into());
    }
    if candidate["kind"] == "worktree" && relation["worktree_owner"] == "unknown" {
        blockers.insert("worktree_owner_unknown".into());
    }
    let successors = list(relation, "successors");
    let complete = relation["status"] == "known"
        && successors.len() == 1
        && successors[0]["coverage"] == "complete";
    let state = if protections.iter().any(|(_, present)| *present) {
        "protected_user_state"
    } else if !owners.is_empty() || relation["requirement_state"] == "unresolved" {
        for owner in &owners {
            blockers.insert(format!("active_owner:{owner}"));
        }
        if relation["requirement_state"] == "unresolved" {
            blockers.insert("unresolved_requirement".into());
        }
        "active"
    } else if semantic["status"] == "present" {
        blockers.insert("unique_semantic_delta".into());
        if complete {
            "superseded"
        } else {
            "needs_extraction"
        }
    } else if semantic["status"] == "unknown" {
        blockers.insert("semantic_delta_unverifiable".into());
        "needs_verification"
    } else if relation["status"] != "known" || relation["requirement_state"] == "unknown" {
        blockers.insert("ownership_or_requirement_unverifiable".into());
        "needs_verification"
    } else if complete && relation["resolution"].is_null() {
        blockers.insert("missing_resolution_trace".into());
        "superseded"
    } else if relation["resolution"].is_null() {
        blockers.insert("missing_resolution_trace".into());
        "merged_equivalent"
    } else if blockers.is_empty() {
        "orphan_safe_to_remove"
    } else {
        blockers.insert("cleanup_preconditions_incomplete".into());
        "needs_verification"
    };
    let action = if blockers.contains("linked_worktree_must_be_cleaned_first") {
        "classify and clean the linked worktree before the local branch"
    } else {
        match state {
            "active" => "retain and follow the active Issue/PR or unresolved requirement",
            "merged_equivalent" => "record the main/resolution trace, then re-run inventory",
            "superseded" => "verify successor coverage reaches main and record resolution",
            "orphan_safe_to_remove" => "select this identity for the existing cleanup executor",
            "needs_extraction" => "extract only the unique delta onto a latest-main Issue branch",
            "needs_verification" => {
                "obtain missing semantic, owner, successor, or user-state evidence"
            }
            _ => "preserve state until its user owner publishes or removes it",
        }
    };
    candidate["classification"] = json!(state);
    candidate["active_owners"] = json!(owners);
    candidate["cleanup_blockers"] = json!(blockers);
    candidate["recommended_action"] = json!(action);
}
fn finish(
    root: &Path,
    main: &str,
    trace: &Value,
    mut candidate: Value,
    user: Value,
    owners: Vec<Value>,
) -> Value {
    candidate["semantic_diff"] = semantic(root, main, text(&candidate, "commit"));
    candidate["trace"] = relation(trace, &candidate);
    candidate["user_state"] = user;
    candidate["implicit_active_owners"] = json!(owners);
    classify(&mut candidate);
    candidate
}
fn worktrees(root: &Path) -> Result<Vec<Value>> {
    let bytes = git_bytes(root, &["worktree", "list", "--porcelain", "-z"])?;
    let mut rows = Vec::new();
    let mut fields = BTreeMap::new();
    let mut flags = BTreeSet::new();
    for token in bytes.split(|value| *value == 0) {
        if token.is_empty() {
            if let Some(path) = fields.get("worktree") {
                rows.push(json!({"path":path,"commit":fields.get("HEAD").unwrap_or(&String::new()),"ref":fields.get("branch").unwrap_or(&String::new()),"detached":flags.contains("detached"),"bare":flags.contains("bare"),"locked":flags.contains("locked"),"prunable":flags.contains("prunable")}));
            }
            fields.clear();
            flags.clear();
            continue;
        }
        let value = String::from_utf8_lossy(token);
        if let Some((key, value)) = value.split_once(' ') {
            fields.insert(key.to_owned(), value.to_owned());
        } else {
            flags.insert(value.into_owned());
        }
    }
    Ok(rows)
}
fn worktree_state(path: &Path) -> Value {
    let unknown = |error: String| json!({"status":"unknown","dirty":null,"untracked_count":null,"entries":[],"error":error});
    if !path.is_dir() {
        return unknown("worktree_path_missing".into());
    }
    let output = match git_output(
        path,
        &["status", "--porcelain=v1", "-z", "--untracked-files=all"],
    ) {
        Ok(output) => output,
        Err(error) => return unknown(error),
    };
    if !output.status.success() {
        return unknown(String::from_utf8_lossy(&output.stderr).trim().into());
    }
    let mut entries: Vec<_> = output
        .stdout
        .split(|value| *value == 0)
        .filter(|value| !value.is_empty())
        .map(|value| String::from_utf8_lossy(value).into_owned())
        .collect();
    entries.sort();
    json!({"status":"observed","dirty":!entries.is_empty(),"untracked_count":entries.iter().filter(|value|value.starts_with("??")).count(),"entries":entries,"error":null})
}
fn inventory(root: &Path, main_ref: &str, trace: &Value) -> Result<Value> {
    let root = fs::canonicalize(root).map_err(|error| error.to_string())?;
    let main = git(
        &root,
        &["rev-parse", "--verify", &format!("{main_ref}^{{commit}}")],
    )?
    .trim()
    .to_owned();
    let trees = worktrees(&root)?;
    let statuses: BTreeMap<_, _> = trees
        .iter()
        .map(|row| {
            (
                text(row, "path").to_owned(),
                worktree_state(Path::new(text(row, "path"))),
            )
        })
        .collect();
    let prs = list(trace, "pull_requests");
    let open = |name: &str| {
        prs.iter()
            .filter(|pr| pr["state"] == "open" && pr["head_ref"] == name)
            .map(|pr| json!(format!("pr:{}", pr["number"])))
            .collect::<Vec<_>>()
    };
    let mut candidates = Vec::new();
    let refs = git(
        &root,
        &[
            "for-each-ref",
            "--format=%(refname)%09%(objectname)%09%(symref)%09%(upstream)",
            "refs/heads",
            "refs/remotes",
        ],
    )?;
    for line in refs.lines() {
        let parts: Vec<_> = line.split('\t').collect();
        if parts.len() < 3 || !parts[2].is_empty() || parts[0].ends_with("/HEAD") {
            continue;
        }
        let reference = parts[0];
        let name = branch(reference);
        if name == "main" || reference == main_ref {
            continue;
        }
        let local = reference.starts_with("refs/heads/");
        let paths: Vec<_> = trees
            .iter()
            .filter(|row| row["ref"] == reference)
            .map(|row| row["path"].clone())
            .collect();
        let dirty: Vec<_> = paths
            .iter()
            .filter(|path| statuses[path.as_str().unwrap()]["dirty"] == true)
            .cloned()
            .collect();
        let unpushed = if local {
            unpushed(&root, reference)
        } else {
            json!(0)
        };
        let item = json!({"candidate_id":if local{format!("branch:local:{name}")}else{format!("branch:remote:{}",reference.strip_prefix("refs/remotes/").unwrap_or(reference))},"kind":if local{"local_branch"}else{"remote_branch"},"ref":reference,"branch":name,"commit":parts[1],"path":null,"pr_number":null});
        let user = json!({"status":if unpushed.is_null(){"unknown"}else{"observed"},"primary_worktree":false,"worktree_owner":null,"dirty":null,"untracked_count":null,"unpushed_commits":unpushed,"linked_worktrees":paths,"dirty_linked_worktrees":dirty});
        candidates.push(finish(&root, &main, trace, item, user, open(&name)));
    }
    for row in trees {
        let reference = text(&row, "ref");
        let name = if reference.is_empty() {
            None
        } else {
            Some(branch(reference))
        };
        let path = text(&row, "path");
        let item = json!({"candidate_id":format!("worktree:{path}"),"kind":"worktree","commit":row["commit"],"ref":if reference.is_empty(){Value::Null}else{json!(reference)},"branch":name,"path":path,"pr_number":null});
        let related = relation(trace, &item);
        let status = &statuses[path];
        let user = json!({"status":status["status"],"primary_worktree":fs::canonicalize(path).ok().as_ref()==Some(&root),"worktree_owner":related["worktree_owner"],"dirty":status["dirty"],"untracked_count":status["untracked_count"],"unpushed_commits":if reference.is_empty(){Value::Null}else{unpushed(&root,reference)},"linked_worktrees":[],"dirty_linked_worktrees":[],"locked":row["locked"],"prunable":row["prunable"],"detached":row["detached"],"bare":row["bare"],"status_entries":status["entries"],"status_error":status["error"]});
        candidates.push(finish(
            &root,
            &main,
            trace,
            item,
            user,
            open(name.as_deref().unwrap_or("")),
        ));
    }
    for pr in prs {
        let item = json!({"candidate_id":format!("pr:{}",pr["number"]),"kind":"pr_head","commit":pr["head_sha"],"ref":null,"branch":pr["head_ref"],"path":null,"pr_number":pr["number"],"pr_state":pr["state"],"pr_url":pr["url"]});
        let owners = if pr["state"] == "open" {
            vec![json!(format!("pr:{}", pr["number"]))]
        } else {
            Vec::new()
        };
        candidates.push(finish(&root,&main,trace,item,json!({"status":"observed","primary_worktree":false,"worktree_owner":null,"dirty":null,"untracked_count":null,"unpushed_commits":0,"linked_worktrees":[],"dirty_linked_worktrees":[]}),owners));
    }
    candidates.sort_by(|left, right| text(left, "candidate_id").cmp(text(right, "candidate_id")));
    let mut counts = BTreeMap::new();
    for candidate in &candidates {
        *counts
            .entry(text(candidate, "classification"))
            .or_insert(0usize) += 1;
    }
    let mut result = json!({"schema":INVENTORY,"policy_owner":POLICY,"repository_root":root.to_string_lossy().replace('\\',"/"),"main":{"ref":main_ref,"commit":main},"trace_schema":trace["schema"],"candidate_count":candidates.len(),"classification_counts":counts,"candidates":candidates,"cleanup_contract":{"mutation_owner":"existing branch/PR/worktree cleanup executor","inventory_is_read_only":true,"age_is_authorization_evidence":false,"explicit_selection_required":true,"live_inventory_recheck_required":true,"allowed_classification":"orphan_safe_to_remove","authorization_command":"agent-canon orphan-lifecycle authorize-cleanup","required_post_cleanup_readback":["candidate_identity","mutation_command","mutation_result","post_cleanup_ref_or_path_state","preserved_main_or_successor_trace","related_issue_or_pr_comment"]}});
    result["inventory_digest"] = json!(inventory_digest(&result));
    Ok(result)
}
fn authorize(old: &Value, fresh: &Value, expected: &str, selections: &[String]) -> Value {
    let mut blockers = Vec::new();
    for (raw, prefix) in [(old, ""), (fresh, "live_")] {
        if raw["schema"] != INVENTORY {
            blockers.push(format!("{prefix}inventory_schema_mismatch"));
        }
        if raw.get("inventory_digest").and_then(Value::as_str)
            != Some(inventory_digest(raw).as_str())
        {
            blockers.push(format!("{prefix}inventory_digest_invalid"));
        }
    }
    if old["inventory_digest"] != expected {
        blockers.push("selection_inventory_digest_mismatch".into());
    }
    if old["inventory_digest"] != fresh["inventory_digest"] {
        blockers.push("live_inventory_digest_mismatch".into());
    }
    if selections.is_empty() {
        blockers.push("explicit_selection_missing".into());
    }
    if selections.iter().collect::<BTreeSet<_>>().len() != selections.len() {
        blockers.push("duplicate_selection".into());
    }
    if !old["candidates"].is_array() {
        blockers.push("inventory_candidates_invalid".into());
    }
    let candidates = list(old, "candidates");
    let decisions:Vec<_>=selections.iter().map(|id|{let mut reasons:BTreeSet<_>=blockers.iter().cloned().collect();let candidate=candidates.iter().find(|value|value["candidate_id"]==*id);if let Some(candidate)=candidate{if candidate["classification"]!="orphan_safe_to_remove"{reasons.insert("candidate_not_orphan_safe_to_remove".into());}match candidate.get("cleanup_blockers").and_then(Value::as_array){None=>{reasons.insert("candidate_blockers_invalid".into());},Some(values)if !values.is_empty()=>{reasons.insert("candidate_has_cleanup_blockers".into());},_=>{}}}else{reasons.insert("candidate_not_in_inventory".into());}json!({"candidate_id":id,"classification":candidate.map(|value|&value["classification"]),"decision":if reasons.is_empty(){"authorized"}else{"refused"},"blockers":reasons})}).collect();
    let mut payload = json!({"schema":ADMISSION,"policy_owner":POLICY,"status":if !decisions.is_empty()&&decisions.iter().all(|value|value["decision"]=="authorized"){"authorized"}else{"refused"},"inventory_digest":old["inventory_digest"],"live_inventory_digest":fresh["inventory_digest"],"expected_inventory_digest":expected,"explicit_selections":selections,"decisions":decisions,"mutation_performed":false,"executor_obligations":old["cleanup_contract"].get("required_post_cleanup_readback").cloned().unwrap_or_else(||json!([]))});
    payload["admission_digest"] = json!(digest(&payload));
    payload
}
pub fn run(args: &[String]) -> i32 {
    const USAGE:&str="usage: agent-canon orphan-lifecycle <inventory|authorize-cleanup> [--root ROOT] [--main-ref REF] [--trace PATH] [--output PATH] [--inventory PATH --inventory-digest DIGEST --select ID]";
    if args.iter().any(|value| value == "--help" || value == "-h") {
        println!("{USAGE}");
        return 0;
    }
    let Some(operation) = args
        .first()
        .filter(|value| ["inventory", "authorize-cleanup"].contains(&value.as_str()))
    else {
        eprintln!("{USAGE}");
        return 2;
    };
    let mut values = BTreeMap::new();
    let mut selections = Vec::new();
    let mut index = 1;
    while index < args.len() {
        let name = args[index].as_str();
        if ![
            "--root",
            "--main-ref",
            "--trace",
            "--output",
            "--inventory",
            "--inventory-digest",
            "--select",
        ]
        .contains(&name)
            || index + 1 == args.len()
        {
            eprintln!("{USAGE}");
            return 2;
        }
        if name == "--select" {
            selections.push(args[index + 1].clone());
        } else {
            values.insert(name, args[index + 1].as_str());
        }
        index += 2;
    }
    let result: Result<i32> = (|| {
        let root = PathBuf::from(values.get("--root").copied().unwrap_or("."));
        let trace = trace(values.get("--trace").map(Path::new))?;
        let payload = if operation == "inventory" {
            inventory(
                &root,
                values
                    .get("--main-ref")
                    .copied()
                    .unwrap_or("refs/remotes/origin/main"),
                &trace,
            )?
        } else {
            let old = read_json(Path::new(
                values.get("--inventory").ok_or("--inventory is required")?,
            ))?;
            let main = old["main"]
                .get("ref")
                .and_then(Value::as_str)
                .ok_or("inventory main ref is missing")?;
            let fresh = inventory(&root, main, &trace)?;
            authorize(
                &old,
                &fresh,
                values
                    .get("--inventory-digest")
                    .ok_or("--inventory-digest is required")?,
                &selections,
            )
        };
        let rendered = format!(
            "{}\n",
            serde_json::to_string_pretty(&payload).map_err(|error| error.to_string())?
        );
        if let Some(output) = values.get("--output") {
            let configured = std::env::var_os("AGENT_CANON_RUNTIME_ROOT").map(PathBuf::from);
            let boundary = crate::runtime_boundary::RuntimeArtifactBoundary::for_source(
                &root,
                configured.as_deref(),
                true,
            )?;
            boundary.atomic_write_text(Path::new(output), &rendered, 0o644)?;
        }
        print!("{rendered}");
        Ok(
            if operation == "authorize-cleanup" && payload["status"] != "authorized" {
                1
            } else {
                0
            },
        )
    })();
    match result {
        Ok(code) => code,
        Err(error) => {
            eprintln!("ORPHAN_LIFECYCLE_ERROR={error}");
            2
        }
    }
}
