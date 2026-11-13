//! Test-only process adapter that supplies fake Docker bind mount namespaces.

use agent_canon::bootstrap_runtime::{run_with_target_namespace, TargetNamespace};
use std::env;
use std::path::PathBuf;
use std::collections::BTreeMap;

fn namespace_from_process_environment() -> Result<TargetNamespace, String> {
    let source_root = env::var_os("AGENT_CANON_RUNTIME_TOOLS_ROOT")
        .map(PathBuf::from)
        .ok_or_else(|| "test driver: runtime tools root is missing".to_string())?;
    let control_root = env::var_os("AGENT_CANON_CONTROL_PARENT_ROOT")
        .map(PathBuf::from)
        .ok_or_else(|| "test driver: control root is missing".to_string())?;
    let runtime_root = env::var_os("AGENT_CANON_RUNTIME_ROOT")
        .map(PathBuf::from)
        .ok_or_else(|| "test driver: runtime root is missing".to_string())?;
    let mounts = match (
        env::var("AGENT_CANON_TARGET_DIGEST").ok(),
        env::var("AGENT_CANON_TARGET_HOST_ROOT").ok(),
    ) {
        (Some(digest), Some(host_root)) => vec![(
            PathBuf::from("/targets").join(digest),
            PathBuf::from(host_root),
        )],
        (None, None) => Vec::new(),
        _ => return Err("test driver: incomplete target mount binding".to_string()),
    };
    TargetNamespace::from_readonly_mounts(mounts)?
        .with_source_root(&source_root)?
        .with_runtime_roots(&control_root, &runtime_root)
}

fn run_tool_wrapper(arguments: &[String]) -> i32 {
    if arguments.get(1).map(String::as_str) != Some("run") {
        eprintln!("usage: agent-canon tool run <catalog-id> -- [args...]");
        return 64;
    }
    let namespace = match namespace_from_process_environment() {
        Ok(namespace) => namespace,
        Err(detail) => {
            eprintln!("{detail}");
            return 2;
        }
    };
    let mut dispatch_args = vec![
        "run".to_string(),
        "--container-exec".to_string(),
        "--root".to_string(),
        "/opt/agent-canon/source".to_string(),
    ];
    dispatch_args.extend(arguments.iter().skip(2).cloned());
    let dispatch_args = namespace.map_process_argv(&dispatch_args);
    let mut environment = env::vars().collect::<BTreeMap<_, _>>();
    environment.insert("AGENT_CANON_EXECUTION_PLANE".to_string(), "tool-container".to_string());
    environment.insert("AGENT_CANON_SOURCE_ROOT".to_string(), "/opt/agent-canon/source".to_string());
    environment.insert("AGENT_CANON_RUNTIME_TOOLS_ROOT".to_string(), "/opt/agent-canon/source".to_string());
    for (key, value) in namespace.map_process_environment(&environment) {
        env::set_var(key, value);
    }
    if let Ok(digest) = env::var("AGENT_CANON_TARGET_DIGEST") {
        let logical_target = format!("/targets/{digest}");
        let target_environment = BTreeMap::from([
            ("AGENT_CANON_TARGET_ROOT".to_string(), logical_target.clone()),
            ("AGENT_CANON_TASK_ROOT".to_string(), logical_target.clone()),
            ("GIT_CONFIG_VALUE_0".to_string(), logical_target),
        ]);
        for (key, value) in namespace.map_process_environment(&target_environment) {
            env::set_var(key, value);
        }
    }
    agent_canon::tool_dispatch::run_cli_in_test_namespace(&dispatch_args, &namespace)
}

fn main() {
    let arguments = env::args().skip(1).collect::<Vec<_>>();
    let mut mounts = Vec::new();
    let mut control_root = None;
    let mut runtime_root = None;
    let mut source_root = None;
    let mut forwarded = Vec::new();
    let mut index = 0;
    while index < arguments.len() {
        if arguments[index] == "--test-target-mount" {
            let Some(logical) = arguments.get(index + 1) else {
                eprintln!("test driver: missing logical target mount path");
                std::process::exit(2);
            };
            let Some(physical) = arguments.get(index + 2) else {
                eprintln!("test driver: missing physical target mount source");
                std::process::exit(2);
            };
            mounts.push((PathBuf::from(logical), PathBuf::from(physical)));
            index += 3;
        } else if arguments[index] == "--test-control-root" {
            let Some(root) = arguments.get(index + 1) else {
                eprintln!("test driver: missing physical control root");
                std::process::exit(2);
            };
            control_root = Some(PathBuf::from(root));
            index += 2;
        } else if arguments[index] == "--test-runtime-root" {
            let Some(root) = arguments.get(index + 1) else {
                eprintln!("test driver: missing physical runtime root");
                std::process::exit(2);
            };
            runtime_root = Some(PathBuf::from(root));
            index += 2;
        } else if arguments[index] == "--test-source-root" {
            let Some(root) = arguments.get(index + 1) else {
                eprintln!("test driver: missing physical source root");
                std::process::exit(2);
            };
            source_root = Some(PathBuf::from(root));
            index += 2;
        } else {
            forwarded.push(arguments[index].clone());
            index += 1;
        }
    }
    let namespace = match TargetNamespace::from_readonly_mounts(mounts) {
        Ok(namespace) => namespace,
        Err(detail) => {
            eprintln!("test driver: invalid target mount namespace: {detail}");
            std::process::exit(2);
        }
    };
    let namespace = match (control_root, runtime_root, source_root) {
        (Some(control), Some(runtime), Some(source)) => {
            match namespace.with_runtime_roots(&control, &runtime)
                .and_then(|namespace| namespace.with_source_root(&source)) {
                Ok(namespace) => namespace,
                Err(detail) => {
                    eprintln!("test driver: invalid resident mount namespace: {detail}");
                    std::process::exit(2);
                }
            }
        }
        (None, None, None) => namespace,
        _ => {
            eprintln!("test driver: control, runtime, and source roots must be provided together");
            std::process::exit(2);
        }
    };
    if forwarded.first().map(String::as_str) == Some("bootstrap-runtime") {
        std::process::exit(run_with_target_namespace(&forwarded[1..], namespace));
    }
    if forwarded.first().map(String::as_str) == Some("tool") {
        std::process::exit(run_tool_wrapper(&forwarded));
    }
    eprintln!("test driver: unsupported command");
    std::process::exit(2);
}
