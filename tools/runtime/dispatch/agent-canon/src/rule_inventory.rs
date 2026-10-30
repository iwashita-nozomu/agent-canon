// @dependency-start
// contract implementation
// responsibility Inventories Python and C++ OOP policy, tool, document, and test surfaces.
// upstream design ../../../../../documents/conventions/object-oriented-design.md OOP policy and inventory contract
// downstream implementation ../../../../../tests/agent_tools/test_oop_rule_inventory.py preserves CLI behavior
// @dependency-end

use serde::Serialize;
use std::env;
use std::fs;
use std::path::{Component, Path, PathBuf};

pub const PYTHON_SELECTOR: &str = "oop-python-rule-inventory";
pub const CPP_SELECTOR: &str = "oop-cpp-rule-inventory";

const NATIVE_OWNER_PATH: &str = "tools/runtime/dispatch/agent-canon/src/rule_inventory.rs";

#[derive(Clone, Copy)]
struct InventoryEntry {
    kind: &'static str,
    path: &'static str,
    purpose: &'static str,
}

#[derive(Serialize)]
struct RenderedEntry {
    kind: &'static str,
    path: &'static str,
    purpose: &'static str,
    exists: bool,
    resolved_path: String,
}

#[derive(Serialize)]
struct InventoryPayload {
    status: &'static str,
    entries: Vec<RenderedEntry>,
    missing: Vec<&'static str>,
}

#[derive(Clone, Copy)]
struct Inventory {
    description: &'static str,
    prefix: &'static str,
    title: &'static str,
    entries: &'static [InventoryEntry],
}

const PYTHON_ENTRIES: &[InventoryEntry] = &[
    InventoryEntry {
        kind: "policy",
        path: "documents/conventions/object-oriented-design.md",
        purpose: "OOP boundary, responsibility, and mechanical-evaluation policy.",
    },
    InventoryEntry {
        kind: "policy",
        path: "documents/conventions/coding-conventions-python.md",
        purpose: "Python type-boundary and readability policy entrypoint.",
    },
    InventoryEntry {
        kind: "tool",
        path: "tools/validation/code/oop/python/readability.py",
        purpose: "Python-specific OOP readability analyzer entrypoint.",
    },
    InventoryEntry {
        kind: "tool",
        path: NATIVE_OWNER_PATH,
        purpose: "Python OOP policy/tool/doc/test inventory.",
    },
    InventoryEntry {
        kind: "document",
        path: "documents/tools/oop/python/readability.md",
        purpose: "Japanese explanation of Python readability checks.",
    },
    InventoryEntry {
        kind: "document",
        path: "documents/tools/oop/python/rule_inventory.md",
        purpose: "Japanese explanation of this inventory check.",
    },
    InventoryEntry {
        kind: "reviewer",
        path: ".codex/agents/oop_readability_reviewer.toml",
        purpose: "Read-only reviewer role for mechanical OOP reports.",
    },
    InventoryEntry {
        kind: "test",
        path: "tests/agent_tools/test_analyze_oop_readability.py",
        purpose: "Regression tests for Python readability findings.",
    },
    InventoryEntry {
        kind: "test",
        path: "tests/agent_tools/test_oop_rule_inventory.py",
        purpose: "Regression tests for OOP inventory behavior.",
    },
];

const CPP_ENTRIES: &[InventoryEntry] = &[
    InventoryEntry {
        kind: "policy",
        path: "documents/conventions/object-oriented-design.md",
        purpose: "OOP boundary, responsibility, and mechanical-evaluation policy.",
    },
    InventoryEntry {
        kind: "policy",
        path: "documents/conventions/coding-conventions-cpp.md",
        purpose: "C/C++ ownership, header, and public-surface policy entrypoint.",
    },
    InventoryEntry {
        kind: "tool",
        path: "tools/validation/code/oop/cpp/readability.py",
        purpose: "C++-specific OOP readability analyzer entrypoint.",
    },
    InventoryEntry {
        kind: "tool",
        path: NATIVE_OWNER_PATH,
        purpose: "C++ OOP policy/tool/doc/test inventory.",
    },
    InventoryEntry {
        kind: "document",
        path: "documents/tools/oop/cpp/readability.md",
        purpose: "Japanese explanation of C++ readability checks.",
    },
    InventoryEntry {
        kind: "document",
        path: "documents/tools/oop/cpp/rule_inventory.md",
        purpose: "Japanese explanation of this inventory check.",
    },
    InventoryEntry {
        kind: "reviewer",
        path: ".codex/agents/oop_readability_reviewer.toml",
        purpose: "Read-only reviewer role for mechanical OOP reports.",
    },
    InventoryEntry {
        kind: "test",
        path: "tests/agent_tools/test_analyze_oop_readability.py",
        purpose: "Regression tests for C++ readability findings.",
    },
    InventoryEntry {
        kind: "test",
        path: "tests/agent_tools/test_oop_rule_inventory.py",
        purpose: "Regression tests for OOP inventory behavior.",
    },
];

pub fn run(selector: &str, args: &[String]) -> i32 {
    let inventory = match inventory_for(selector) {
        Some(inventory) => inventory,
        None => {
            eprintln!("agent-canon: unknown OOP rule inventory selector `{selector}`");
            return 2;
        }
    };
    let parsed = match parse_args(args) {
        Ok(ParsedArgs::Help) => {
            println!("{}\n\n{}", usage(selector), inventory.description);
            return 0;
        }
        Ok(ParsedArgs::Run(parsed)) => parsed,
        Err(message) => {
            eprintln!("agent-canon {selector}: {message}");
            eprintln!("{}", usage(selector));
            return 2;
        }
    };

    let root = resolve_root(&parsed.root);
    let payload = inventory_payload(&root, inventory.entries);
    match parsed.format.as_str() {
        "json" => print_json(&payload),
        "markdown" => print_markdown(inventory, &payload),
        _ => print_text(inventory, &payload),
    }
    if payload.missing.is_empty() {
        0
    } else {
        1
    }
}

#[derive(Debug, PartialEq, Eq)]
struct ParsedOptions {
    root: PathBuf,
    format: String,
}

enum ParsedArgs {
    Help,
    Run(ParsedOptions),
}

fn inventory_for(selector: &str) -> Option<Inventory> {
    match selector {
        PYTHON_SELECTOR => Some(Inventory {
            description: "Inventory Python OOP rule surfaces.",
            prefix: "OOP_PYTHON",
            title: "Python OOP Rule Inventory",
            entries: PYTHON_ENTRIES,
        }),
        CPP_SELECTOR => Some(Inventory {
            description: "Inventory C++ OOP rule surfaces.",
            prefix: "OOP_CPP",
            title: "C++ OOP Rule Inventory",
            entries: CPP_ENTRIES,
        }),
        _ => None,
    }
}

fn usage(selector: &str) -> String {
    format!("usage: agent-canon {selector} [--root ROOT] [--format {{text,json,markdown}}]")
}

fn parse_args(args: &[String]) -> Result<ParsedArgs, String> {
    let mut root = PathBuf::from(".");
    let mut format = String::from("text");
    let mut index = 0;
    while index < args.len() {
        let argument = &args[index];
        if argument == "-h" || argument == "--help" {
            return Ok(ParsedArgs::Help);
        }
        if argument == "--root" || argument == "--format" {
            let option = argument.as_str();
            index += 1;
            let Some(value) = args.get(index) else {
                return Err(format!("argument {option}: expected one argument"));
            };
            if value.starts_with('-') {
                return Err(format!("argument {option}: expected one argument"));
            }
            if option == "--root" {
                root = PathBuf::from(value);
            } else {
                format = value.clone();
            }
        } else if let Some(value) = argument.strip_prefix("--root=") {
            root = PathBuf::from(value);
        } else if let Some(value) = argument.strip_prefix("--format=") {
            format = value.to_owned();
        } else {
            return Err(format!("unrecognized arguments: {argument}"));
        }
        index += 1;
    }
    if !matches!(format.as_str(), "text" | "json" | "markdown") {
        return Err(format!(
            "argument --format: invalid choice: `{format}` (choose from `text`, `json`, `markdown`)"
        ));
    }
    Ok(ParsedArgs::Run(ParsedOptions { root, format }))
}

fn resolve_root(path: &Path) -> PathBuf {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join(path)
    };
    let mut resolved = PathBuf::new();
    for component in absolute.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                if let Ok(canonicalized) = fs::canonicalize(&resolved) {
                    resolved = canonicalized;
                }
                if !resolved.pop() && !resolved.has_root() {
                    resolved.push(component.as_os_str());
                }
            }
            Component::Normal(_) => {
                resolved.push(component.as_os_str());
                if let Ok(canonicalized) = fs::canonicalize(&resolved) {
                    resolved = canonicalized;
                }
            }
            _ => resolved.push(component.as_os_str()),
        }
    }
    resolved
}

fn resolve_surface_path(root: &Path, relative_path: &str) -> PathBuf {
    let root_path = root.join(relative_path);
    if root_path.exists() {
        return root_path;
    }
    let vendor_path = root.join("vendor/agent-canon").join(relative_path);
    if vendor_path.exists() {
        return vendor_path;
    }
    root_path
}

fn missing_entries<'a>(root: &Path, entries: &'a [InventoryEntry]) -> Vec<&'a InventoryEntry> {
    entries
        .iter()
        .filter(|entry| !resolve_surface_path(root, entry.path).exists())
        .collect()
}

fn inventory_payload(root: &Path, entries: &[InventoryEntry]) -> InventoryPayload {
    let missing = missing_entries(root, entries);
    let rendered_entries = entries
        .iter()
        .map(|entry| {
            let resolved = resolve_surface_path(root, entry.path);
            let exists = resolved.exists();
            let resolved_path = if exists {
                resolved
                    .strip_prefix(root)
                    .expect("resolved inventory path remains beneath its root")
                    .to_string_lossy()
                    .into_owned()
            } else {
                String::new()
            };
            RenderedEntry {
                kind: entry.kind,
                path: entry.path,
                purpose: entry.purpose,
                exists,
                resolved_path,
            }
        })
        .collect();
    InventoryPayload {
        status: if missing.is_empty() { "pass" } else { "fail" },
        entries: rendered_entries,
        missing: missing.iter().map(|entry| entry.path).collect(),
    }
}

fn print_text(inventory: Inventory, payload: &InventoryPayload) {
    println!("{}_RULE_INVENTORY={}", inventory.prefix, payload.status);
    println!(
        "{}_RULE_INVENTORY_ENTRIES={}",
        inventory.prefix,
        payload.entries.len()
    );
    println!(
        "{}_RULE_INVENTORY_MISSING={}",
        inventory.prefix,
        payload.missing.len()
    );
    for entry in &payload.entries {
        println!(
            "{}_RULE_SOURCE={}\t{}\texists={}\tresolved={}\t{}",
            inventory.prefix,
            entry.kind,
            entry.path,
            if entry.exists { "yes" } else { "no" },
            entry.resolved_path,
            entry.purpose
        );
    }
}

fn print_markdown(inventory: Inventory, payload: &InventoryPayload) {
    println!("# {}", inventory.title);
    println!();
    println!("- Status: `{}`", payload.status);
    println!("- Entries: `{}`", payload.entries.len());
    println!("- Missing entries: `{}`", payload.missing.len());
    println!();
    println!("| Kind | Path | Exists | Resolved Path | Purpose |");
    println!("| --- | --- | --- | --- | --- |");
    for entry in &payload.entries {
        println!(
            "| {} | `{}` | {} | `{}` | {} |",
            entry.kind,
            entry.path,
            if entry.exists { "yes" } else { "no" },
            entry.resolved_path,
            entry.purpose
        );
    }
}

fn print_json(payload: &InventoryPayload) {
    println!(
        "{}",
        serde_json::to_string_pretty(payload).expect("inventory payload serializes to JSON")
    );
}

#[cfg(test)]
mod tests {
    use super::{inventory_payload, missing_entries, resolve_surface_path, InventoryEntry};
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn shared_inventory_resolves_standalone_surfaces() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock is after the Unix epoch")
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "agent-canon-oop-rule-inventory-{}-{unique}",
            std::process::id()
        ));
        let source_doc = root
            .join("documents")
            .join("conventions")
            .join("object-oriented-design.md");
        fs::create_dir_all(source_doc.parent().expect("source document has parent"))
            .expect("create standalone source fixture");
        fs::write(&source_doc, "# OOP\n").expect("write standalone source fixture");
        let entry = InventoryEntry {
            kind: "policy",
            path: "documents/conventions/object-oriented-design.md",
            purpose: "OOP policy",
        };

        let resolved = resolve_surface_path(&root, entry.path);
        let payload = inventory_payload(&root, &[entry]);
        let missing = missing_entries(&root, &[entry]);

        assert_eq!(resolved, source_doc);
        assert!(missing.is_empty());
        assert_eq!(payload.status, "pass");
        assert!(payload.missing.is_empty());
        fs::remove_dir_all(root).expect("remove standalone source fixture");
    }
}
