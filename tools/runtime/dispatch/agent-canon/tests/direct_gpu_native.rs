// @dependency-start
// contract test
// responsibility Checks native direct-command descendant retention and CLI preflight with independent process and file oracles.
// upstream implementation ../src/gpu_command_admission.rs owns admitted command execution
// @dependency-end

#[cfg(target_os="linux")]
mod linux {
    use agent_canon::gpu_command_admission::{execute_direct_command,FrozenDirectGpuCommandPlan};
    use sha2::{Digest,Sha256};
    use std::collections::BTreeMap;
    use std::process::{Command,Stdio};
    use std::sync::Mutex;
    use std::time::Instant;
    static PROCESS_TEST:Mutex<()>=Mutex::new(());
    const GPU:&str="GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
    fn plan(root:&std::path::Path,argv:Vec<String>)->FrozenDirectGpuCommandPlan {
        let mut value=serde_json::json!({"schema_version":"agentcanon-gpu-command-plan/v1","plan_id":"fixture","argv":argv,"cwd":root,"candidate_ids":[GPU],"selected_ids":[GPU],"candidate_source":"cli","candidate_inventory_fingerprint":"inventory","candidate_mig_parent_by_uuid":{},"requested_gpu_count":1,"minimum_free_memory_bytes":0,"selected_free_memory_bytes":{GPU:1000},"initial_unit_states":{GPU:"FREE"},"final_unit_states":{GPU:"FREE"},"initial_observation_fingerprint":"initial","final_observation_fingerprint":"final","initial_event_id":"initial-event","final_event_id":"final-event","reservation_fingerprint":"reservation","reservation_ids":["reservation-id"],"lock_identities":[[11,22]],"admission_fingerprint":"admission","base_environment_fingerprint":"environment","environment_key_witness":{},"output_dir":root,"unknown_initial_ids":[],"unknown_final_ids":[]});
        let bytes=agent_canon::artifacts::artifact_identity::canonical_json_ascii_bytes(&value).expect("canonical fixture");value["plan_fingerprint"]=serde_json::json!(format!("{:x}",Sha256::digest(bytes)));
        serde_json::from_value(value).expect("valid frozen input")
    }
    #[test]
    fn waits_for_detached_descendant_before_returning_exit_and_logs(){
        let _guard=PROCESS_TEST.lock().expect("isolated process fixture");
        let root=tempfile::tempdir_in(std::env::temp_dir().canonicalize().expect("canonical temporary parent")).expect("fixture root");let marker=root.path().join("descendant-finished");
        let command=vec!["sh".into(),"-c".into(),"(sleep 0.15; printf done > \"$1\") & printf stdout; printf stderr >&2; exit 7".into(),"fixture".into(),marker.to_string_lossy().into_owned()];
        let frozen=plan(root.path(),command);let environment=std::env::vars().collect::<BTreeMap<_,_>>();
        let result=execute_direct_command(&frozen,&environment,0.005).expect("quiescent execution");
        assert_eq!(result.returncode,7);assert_eq!(std::fs::read(marker).expect("descendant completion"),b"done");assert_eq!(std::fs::read(result.stdout_path).expect("stdout"),b"stdout");assert_eq!(std::fs::read(result.stderr_path).expect("stderr"),b"stderr");assert!(!result.lifecycle.observed_descendant_identities.is_empty());
    }
    #[test]
    fn preexisting_child_is_outside_command_scope(){
        let _guard=PROCESS_TEST.lock().expect("isolated process fixture");
        let root=tempfile::tempdir_in(std::env::temp_dir().canonicalize().expect("canonical temporary parent")).expect("fixture root");
        let mut unrelated=Command::new("sleep").arg("1.5").stdout(Stdio::null()).stderr(Stdio::null()).spawn().expect("unrelated fixture child");
        let frozen=plan(root.path(),vec!["sh".into(),"-c".into(),"printf done; exit 0".into()]);let environment=std::env::vars().collect::<BTreeMap<_,_>>();let start=Instant::now();
        let result=execute_direct_command(&frozen,&environment,0.005).expect("command execution");let elapsed=start.elapsed();let still_running=unrelated.try_wait().expect("unrelated state").is_none();let _=unrelated.kill();let _=unrelated.wait();
        assert_eq!(result.returncode,0);assert!(still_running);assert!(elapsed.as_secs_f64()<1.0);
    }
}

#[test]
fn public_cli_reports_preflight_without_a_managed_provider(){
    let output=std::process::Command::new(env!("CARGO_BIN_EXE_agent-canon")).args(["run-gpu-command","--"]).env_remove("AGENT_CANON_NATIVE_BIN").output().expect("native CLI");
    assert_eq!(output.status.code(),Some(125));let record:serde_json::Value=serde_json::from_slice(&output.stderr).expect("structured failure");assert_eq!(record["failure_code"],"gpu_command_argv_invalid");assert_eq!(record["schema_version"],"agentcanon-gpu-command-cli-error/v1");
}
