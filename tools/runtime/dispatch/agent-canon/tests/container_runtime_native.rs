// @dependency-start
// contract test
// responsibility Checks native project-container plans, explicit mounts, builder execution, and failure propagation.
// upstream implementation ../src/container_runtime.rs owns project container execution
// @dependency-end

use agent_canon::container_runtime::{run_command, ContainerPack, RunOptions};
use std::fs;
use std::path::Path;
use std::process::{Command, Output};

fn fixture() -> tempfile::TempDir {
    tempfile::tempdir_in(std::env::temp_dir().canonicalize().unwrap()).unwrap()
}

fn cli(root: &Path, mode: &str, args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .arg(mode)
        .args(args)
        .current_dir(root)
        .env_remove("AGENT_CANON_OPTIONAL_MOUNTS")
        .output()
        .unwrap()
}

fn pack(root: &Path, runtime: &str) -> std::path::PathBuf {
    fs::create_dir_all(root.join("docker/packs")).unwrap();
    let path = root.join("docker/packs/default.toml");
    fs::write(&path,format!("[pack]\nname='fixture'\ndockerfile='docker/Dockerfile'\ncontext='.'\nimage_tag='fixture:stable'\n[smoke]\ncommands=['printf smoke']\n[runtime]\n{runtime}\n")).unwrap();
    path
}

#[test]
fn all_four_entrypoints_project_the_same_pack_gpu_and_workspace() {
    let temp = fixture();
    let root = temp.path();
    let pack = pack(
        root,
        "gpus='all'\nworkspace_mount='/selected'\nworkdir='/selected'",
    );
    fs::write(root.join("consumer.py"), "# project-owned Python input\n").unwrap();
    for mode in [
        "run-container-pack",
        "run-in-repo-container",
        "run-repo-program",
        "run-python-in-dockerfile",
    ] {
        let mut args = vec![
            "--pack",
            pack.to_str().unwrap(),
            "--print-only",
            "--builder",
            "docker",
        ];
        match mode {
            "run-container-pack" => {}
            "run-python-in-dockerfile" => args.extend(["docker/Dockerfile", "consumer.py"]),
            "run-repo-program" => args.extend(["--skip-env-check", "consumer.py"]),
            _ => args.extend(["--", "python3", "--version"]),
        }
        let result = cli(root, mode, &args);
        assert!(
            result.status.success(),
            "{mode}: {}",
            String::from_utf8_lossy(&result.stderr)
        );
        let text = String::from_utf8(result.stdout).unwrap();
        assert!(text.contains("--gpus all"), "{text}");
        assert!(text.contains("-w /selected fixture:stable"), "{text}");
        assert!(text.contains("docker build -f"));
        assert!(!text.contains("project-install"));
    }
}

#[test]
fn program_resolution_keeps_python_shell_command_tail_and_preflight() {
    let temp = fixture();
    let root = temp.path();
    fs::write(root.join("consumer.py"), "# consumer input\n").unwrap();
    fs::write(root.join("run.sh"), "#!/bin/sh\nexit 0\n").unwrap();
    for (program, expected) in [
        ("consumer.py", "python3 /workspace/consumer.py"),
        ("run.sh", "/bin/bash /workspace/run.sh"),
        ("printf", "printf"),
    ] {
        let result = cli(
            root,
            "run-repo-program",
            &["--print-only", program, "--", "--argument"],
        );
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        let text = String::from_utf8(result.stdout).unwrap();
        assert!(text.contains(&format!("{expected} --argument")), "{text}");
        assert!(text.contains("env-check:"));
        assert!(text.contains("docker_dependency_validator.sh"));
    }
}

#[test]
fn rules_select_pack_interpreter_and_workdir_for_python_inputs() {
    let temp = fixture();
    let root = temp.path();
    pack(root, "workspace_mount='/project'");
    fs::create_dir(root.join("inputs")).unwrap();
    fs::write(root.join("inputs/consumer.py"), "# consumer input\n").unwrap();
    fs::write(root.join("rules.toml"),"[[rule]]\ndockerfile='docker/Dockerfile'\nmatch_roots=['inputs/']\npack='docker/packs/default.toml'\npython_bin='python-custom'\nworkdir='/jobs'\n").unwrap();
    let result = cli(
        root,
        "run-repo-program",
        &[
            "--rules",
            "rules.toml",
            "--print-only",
            "--skip-env-check",
            "inputs/consumer.py",
            "--",
            "--one",
        ],
    );
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let text = String::from_utf8(result.stdout).unwrap();
    assert!(
        text.contains("-w /jobs fixture:stable python-custom /project/inputs/consumer.py --one"),
        "{text}"
    );
}

#[test]
fn explicit_workspace_build_overrides_and_disposable_run_keep_argument_boundaries() {
    let temp = fixture();
    let root = temp.path();
    let pack_path = pack(root, "env=['KEEP=one','REPLACE=old']");
    let pack = ContainerPack::load(root, pack_path.to_str()).unwrap();
    let options = RunOptions {
        env: vec!["REPLACE=new".into(), "FINAL=a b".into()],
        ports: vec!["8888:8888".into()],
        user: Some("1000:1000".into()),
        tty: true,
        ..Default::default()
    };
    let command = run_command(
        &pack,
        root,
        "podman",
        &["printf".into(), "a b".into()],
        &options,
    )
    .unwrap();
    assert_eq!(&command[..5], ["podman", "run", "--rm", "-i", "-t"]);
    assert_eq!(&command[command.len() - 2..], ["printf", "a b"]);
    assert!(command.windows(2).any(|pair| pair == ["-e", "REPLACE=new"]));
    assert!(!command.iter().any(|value| value == "REPLACE=old"));
    assert!(command.windows(2).any(|pair| pair == ["-p", "8888:8888"]));
    let build = pack.build_command(root, "podman", true, true).unwrap();
    assert!(build.contains(&"--pull".into()) && build.contains(&"--no-cache".into()));
    assert_eq!(build.last().unwrap(), &root.display().to_string());
}

#[test]
fn malformed_pack_and_removed_keep_image_option_fail_before_execution() {
    let temp = fixture();
    let root = temp.path();
    for runtime in [
        "mounts=['/a:/b']",
        "optional_mount_profiles=['unknown']",
        "optional_mount_profiles=['host-git','host-git']",
        "optional_mount_profiles=['linked-data-roots']",
        "env=[1]",
    ] {
        let path = pack(root, runtime);
        assert!(
            ContainerPack::load(root, path.to_str()).is_err(),
            "{runtime}"
        );
    }
    let result = cli(root, "run-in-repo-container", &["--keep-image"]);
    assert_eq!(result.status.code(), Some(2));
}

#[cfg(unix)]
#[test]
fn linked_worktree_mounts_only_common_git_metadata_and_rejects_overrides() {
    let temp = fixture();
    let parent = temp.path().join("parent");
    let worktree = temp.path().join("topic");
    fs::create_dir(&parent).unwrap();
    for args in [
        vec!["init", "-q"],
        vec![
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "fixture",
        ],
    ] {
        assert!(Command::new("git")
            .arg("-C")
            .arg(&parent)
            .args(args)
            .status()
            .unwrap()
            .success());
    }
    assert!(Command::new("git")
        .arg("-C")
        .arg(&parent)
        .args(["worktree", "add", "-q", "-b", "topic"])
        .arg(&worktree)
        .status()
        .unwrap()
        .success());
    let pack = ContainerPack::load(&worktree, None).unwrap();
    let command = run_command(
        &pack,
        &worktree,
        "docker",
        &["true".into()],
        &RunOptions::default(),
    )
    .unwrap();
    let common = parent.join(".git").canonicalize().unwrap();
    assert!(command.contains(&format!("{0}:{0}:ro", common.display())));
    assert!(!command.contains(&format!("{0}:{0}", parent.display())));
    for target in [common.clone(), parent.clone(), common.join("objects")] {
        assert!(run_command(
            &pack,
            &worktree,
            "docker",
            &[],
            &RunOptions {
                mounts: vec![format!("/override:{}", target.display())],
                ..Default::default()
            }
        )
        .is_err());
    }
}

#[cfg(unix)]
#[test]
fn linked_roots_require_a_real_exact_declared_directory_and_protect_mounts() {
    use std::os::unix::fs::symlink;
    let temp = fixture();
    let root = temp.path();
    let target = root.join("data");
    fs::create_dir(&target).unwrap();
    fs::create_dir(root.join("links")).unwrap();
    symlink(&target, root.join("links/data")).unwrap();
    let path=pack(root,"optional_mount_profiles=['linked-data-roots']\nlinked_data_roots=[{link='links/data',target='/mnt/l/data'}]");
    let mut pack = ContainerPack::load(root, path.to_str()).unwrap();
    assert!(run_command(&pack, root, "docker", &[], &RunOptions::default()).is_err());
    // Filesystem setup supplies an actual target; the public run API checks resolution and collisions.
    pack.linked_roots[0].1 = target.display().to_string();
    assert!(
        run_command(&pack, root, "docker", &[], &RunOptions::default())
            .unwrap()
            .contains(&format!("{0}:{0}", target.display()))
    );
    for mount in [
        format!("/override:{}", target.display()),
        format!("type=bind,src=/override,dst={}", target.display()),
        format!("/override:{}", root.display()),
    ] {
        assert!(run_command(
            &pack,
            root,
            "docker",
            &[],
            &RunOptions {
                mounts: vec![mount],
                ..Default::default()
            }
        )
        .is_err());
    }
}

#[cfg(unix)]
#[test]
fn actual_builder_calls_keep_stable_tags_skip_existing_images_and_propagate_exit() {
    use std::os::unix::fs::PermissionsExt;
    let temp = fixture();
    let root = temp.path();
    let bin = root.join("bin");
    fs::create_dir(&bin).unwrap();
    let program = bin.join("docker");
    let log = root.join("calls");
    fs::write(&program,"#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$CALL_LOG\"\ncase \"$1\" in info) exit 0;; image) if [ \"$IMAGE_PRESENT\" = yes ]; then printf 'sha256:fixture\\n'; exit 0; else exit 1; fi;; build) exit \"${BUILD_EXIT:-0}\";; run) exit \"${RUN_EXIT:-0}\";; esac\nexit 9\n").unwrap();
    fs::set_permissions(&program, fs::Permissions::from_mode(0o755)).unwrap();
    let path = std::env::join_paths(std::iter::once(bin).chain(std::env::split_paths(
        &std::env::var_os("PATH").unwrap_or_default(),
    )))
    .unwrap();
    for (present, build_exit, run_exit, expected, build_count, run_count) in [
        ("yes", "0", "7", 7, 0, 1),
        ("no", "5", "0", 5, 1, 0),
        ("no", "0", "0", 0, 1, 1),
    ] {
        let _ = fs::remove_file(&log);
        let output = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
            .args(["run-in-repo-container", "--builder", "docker", "--", "true"])
            .current_dir(root)
            .env("PATH", &path)
            .env("CALL_LOG", &log)
            .env("IMAGE_PRESENT", present)
            .env("BUILD_EXIT", build_exit)
            .env("RUN_EXIT", run_exit)
            .env_remove("AGENT_CANON_OPTIONAL_MOUNTS")
            .output()
            .unwrap();
        assert_eq!(
            output.status.code(),
            Some(expected),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        let calls = fs::read_to_string(&log).unwrap();
        assert_eq!(
            calls
                .lines()
                .filter(|line| line.starts_with("build "))
                .count(),
            build_count,
            "{calls}"
        );
        assert_eq!(
            calls
                .lines()
                .filter(|line| line.starts_with("run "))
                .count(),
            run_count,
            "{calls}"
        );
        assert!(
            !calls.contains("image rm") && !calls.contains("network") && !calls.contains("volume")
        );
        assert!(calls.contains("image inspect --format {{.Id}}"));
    }
    let _ = fs::remove_file(&log);
    let output = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args([
            "run-in-repo-container",
            "--builder",
            "docker",
            "--print-only",
            "--",
            "true",
        ])
        .current_dir(root)
        .env("PATH", &path)
        .env("CALL_LOG", &log)
        .env_remove("AGENT_CANON_OPTIONAL_MOUNTS")
        .output()
        .unwrap();
    assert!(output.status.success());
    assert!(!log.exists());
}
