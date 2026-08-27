#!/usr/bin/env python3
"""Minimal stateful Docker executable used by bootstrap behavioural tests."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def load() -> dict:
    """Load fake daemon state from the test-owned file."""
    path = Path(os.environ["FAKE_DOCKER_STATE"])
    if not path.exists():
        return {"images": {}, "containers": {}, "next": 1}
    return json.loads(path.read_text(encoding="utf-8"))


def save(state: dict) -> None:
    """Persist fake daemon state."""
    Path(os.environ["FAKE_DOCKER_STATE"]).write_text(
        json.dumps(state, sort_keys=True), encoding="utf-8"
    )


def labels(argv: list[str]) -> dict[str, str]:
    """Extract Docker label arguments."""
    result = {}
    for index, item in enumerate(argv):
        if item == "--label" and index + 1 < len(argv):
            key, _, value = argv[index + 1].partition("=")
            result[key] = value
    return result


def find(state: dict, identifier: str) -> tuple[str, dict] | None:
    """Find an image or container by tag, name, or ID."""
    if identifier in state["images"]:
        return "image", state["images"][identifier]
    for record in state["images"].values():
        if record["Id"] == identifier:
            return "image", record
    for name, record in state["containers"].items():
        if name == identifier or record["Id"] == identifier:
            return "container", record
    return None


def _formatted_image(record: dict, fmt: str) -> str | None:
    """Return the scalar image fields used by the host shell adapter."""
    if fmt == "{{.Id}}":
        return str(record["Id"])
    return None


def _formatted_container(record: dict, fmt: str) -> str | None:
    """Return the scalar/container-list fields used by bootstrap readback."""
    if fmt == "{{.Id}}":
        return str(record["Id"])
    if fmt == "{{.Config.Image}}":
        return str(record.get("Config", {}).get("Image", ""))
    if fmt == '{{index .Config.Labels "io.agent-canon.runtime"}}':
        return str(record.get("Config", {}).get("Labels", {}).get("io.agent-canon.runtime", ""))
    if fmt == '{{index .Config.Labels "io.agent-canon.control-root-digest"}}':
        return str(record.get("Config", {}).get("Labels", {}).get("io.agent-canon.control-root-digest", ""))
    if fmt == "{{.State.Running}}":
        return "true" if record.get("State", {}).get("Running") else "false"
    if fmt == "{{if .State.Health}}{{.State.Health.Status}}{{else}}starting{{end}}":
        health = record.get("State", {}).get("Health")
        return str(health.get("Status", "starting")) if health else "starting"
    host = record.get("HostConfig", {})
    if fmt == "{{.HostConfig.NetworkMode}}":
        return str(host.get("NetworkMode", ""))
    if fmt == "{{.HostConfig.ReadonlyRootfs}}":
        return "true" if host.get("ReadonlyRootfs") else "false"
    if fmt == '{{join .HostConfig.CapDrop ","}}':
        return ",".join(host.get("CapDrop", []))
    if fmt == '{{join .HostConfig.SecurityOpt ","}}':
        return ",".join(host.get("SecurityOpt", []))
    if fmt == "{{.HostConfig.NanoCpus}}":
        return str(host.get("NanoCpus", 0))
    if fmt == "{{.HostConfig.Memory}}":
        return str(host.get("Memory", 0))
    if fmt == "{{.HostConfig.PidsLimit}}":
        return str(host.get("PidsLimit", 0))
    if fmt == "{{range .Mounts}}{{printf \"%s\\t%s\\t%t\\n\" .Source .Destination .RW}}{{end}}":
        return "".join(
            f"{mount['Source']}\t{mount['Destination']}\t"
            f"{'true' if mount.get('RW') else 'false'}\n"
            for mount in record.get("Mounts", [])
        )
    return None


def _materialize_skill_exchange(state: dict, container: dict) -> None:
    """Model resident materializer output in the writable runtime exchange."""
    runtime_mount = next(
        (
            mount
            for mount in container.get("Mounts", [])
            if mount["Destination"] == "/var/lib/agent-canon/runtime"
        ),
        None,
    )
    if runtime_mount is None:
        return
    image_ref = container.get("Config", {}).get("Image", "")
    image = find(state, image_ref)
    if image is None or image[0] != "image":
        return
    source_root = Path(str(image[1].get("SourceRoot", "")))
    source = source_root / ".codex/personal/skills"
    if not source.is_dir():
        source = Path(__file__).resolve().parents[2] / ".codex/personal/skills"
    if not source.is_dir():
        return
    stage = Path(runtime_mount["Source"]) / "container-runtime/skill-projection/.codex/personal/skills"
    stage.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, stage, dirs_exist_ok=True)


def _memory_bytes(value: str) -> int:
    """Parse the small Docker memory notation used by the shell adapter."""
    if value.endswith("g"):
        return int(value[:-1]) * 1024**3
    if value.endswith("m"):
        return int(value[:-1]) * 1024**2
    return int(value)


def main(argv: list[str]) -> int:
    """Implement the small Docker command subset used by tests."""
    call_log = os.environ.get("FAKE_DOCKER_CALLS")
    if call_log:
        with Path(call_log).open("a", encoding="utf-8") as handle:
            handle.write("\t".join(argv) + "\n")
    event_log = os.environ.get("FAKE_DOCKER_EVENTS")
    if event_log:
        with Path(event_log).open("a", encoding="utf-8") as handle:
            handle.write("docker\n")
    state = load()
    if argv[:2] == ["image", "inspect"]:
        identifier = argv[-1]
        found = find(state, identifier)
        if not found or found[0] != "image":
            return 1
        if "--format" in argv:
            formatted = _formatted_image(found[1], argv[argv.index("--format") + 1])
            if formatted is None:
                return 2
            print(formatted)
            return 0
        print(json.dumps([found[1]]))
        return 0
    if argv[:2] == ["image", "ls"]:
        if os.environ.get("FAKE_DOCKER_FAIL_IMAGE_LS") == "1":
            return 1
        print("\n".join(dict.fromkeys(record["Id"] for record in state["images"].values())))
        return 0
    if argv[:1] == ["build"]:
        tag = argv[argv.index("--tag") + 1]
        previous = state["images"].get(tag)
        if previous is not None:
            state["images"][f"untagged:{previous['Id']}"] = {
                **previous,
                "RepoTags": [],
            }
        image_number = int(state.get("next_image", 1))
        state["next_image"] = image_number + 1
        image_id = (
            f"sha256:{image_number:064x}"
            if os.environ.get("FAKE_DOCKER_VALID_IMAGE_IDS") == "1"
            else f"sha256:fake-image-{image_number}"
        )
        record = {
            "Id": image_id,
            "RepoTags": [tag],
            "Config": {"Labels": labels(argv)},
            "SourceRoot": argv[-1],
        }
        state["images"][tag] = record
        save(state)
        return 0
    if argv[:2] == ["container", "inspect"]:
        identifier = argv[-1]
        found = find(state, identifier)
        if not found or found[0] != "container":
            return 1
        health = found[1].get("State", {}).get("Health", {})
        if (
            found[1].get("State", {}).get("Running")
            and health.get("Status") == "starting"
        ):
            polls = int(os.environ.get("FAKE_DOCKER_HEALTH_POLLS", "0"))
            found[1]["health_polls"] = int(found[1].get("health_polls", 0)) + 1
            if found[1]["health_polls"] > polls:
                health["Status"] = "healthy"
                drift = os.environ.get("FAKE_DOCKER_DRIFT_ON_HEALTH")
                if drift and not found[1].get("drift_applied"):
                    if drift == "network":
                        found[1]["HostConfig"]["NetworkMode"] = "bridge"
                    elif drift == "labels":
                        found[1]["Config"]["Labels"][
                            "io.agent-canon.control-root-digest"
                        ] = "foreign-control-root"
                    found[1]["drift_applied"] = True
            save(state)
        if "--format" in argv:
            formatted = _formatted_container(found[1], argv[argv.index("--format") + 1])
            if formatted is None:
                return 2
            print(formatted, end="" if formatted.endswith("\n") else "\n")
            return 0
        print(json.dumps([found[1]]))
        return 0
    if argv[:2] == ["container", "ls"]:
        print("\n".join(record["Id"] for record in state["containers"].values()))
        return 0
    if argv[:1] == ["create"]:
        name = argv[argv.index("--name") + 1]
        parsed_mounts = []
        mount_snapshots = {}
        for index, item in enumerate(argv):
            if item != "--mount":
                continue
            values = dict(
                part.split("=", 1) for part in argv[index + 1].split(",") if "=" in part
            )
            source = values["src"]
            if os.environ.get("FAKE_DOCKER_CANONICALIZE_MOUNTS") == "1":
                source = str(Path(source).resolve())
            parsed_mounts.append(
                {
                    "Type": "bind",
                    "Source": source,
                    "Destination": values["dst"],
                    "RW": "readonly" not in argv[index + 1],
                    "Mode": "ro" if "readonly" in argv[index + 1] else "rw",
                }
            )
            if values["dst"] == "/var/lib/agent-canon/mount-registry.toml":
                mount_snapshots[values["dst"]] = Path(source).read_text(
                    encoding="utf-8"
                )
        cid = f"container-{state['next']}"
        state["next"] += 1
        value = {
            "Id": cid,
            "Name": "/" + name,
            "Config": {
                "Image": next(
                    (item for item in reversed(argv) if item and not item.startswith("--")),
                    "",
                ),
                "Labels": labels(argv),
            },
            "State": {"Running": False, "Health": {"Status": "starting"}},
            "HostConfig": {
                "ReadonlyRootfs": "--read-only" in argv,
                "NetworkMode": argv[argv.index("--network") + 1],
                "Memory": _memory_bytes(argv[argv.index("--memory") + 1]),
                "PidsLimit": int(argv[argv.index("--pids-limit") + 1]),
                "NanoCpus": int(float(argv[argv.index("--cpus") + 1]) * 1_000_000_000),
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges"],
                "Tmpfs": {"/tmp": ""},
            },
            "Mounts": parsed_mounts,
            "MountSnapshots": mount_snapshots,
        }
        state["containers"][name] = value
        save(state)
        print(cid)
        return 0
    if argv[:1] == ["tag"] and len(argv) == 3:
        found = find(state, argv[1])
        if not found or found[0] != "image":
            return 1
        state["images"][argv[2]] = {**found[1], "RepoTags": [argv[2]]}
        save(state)
        return 0
    if argv[:1] == ["start"]:
        found = find(state, argv[1])
        if not found:
            return 1
        found[1]["State"] = {"Running": True, "Health": {"Status": "starting"}}
        save(state)
        print(argv[1])
        return 0
    if argv[:1] == ["stop"]:
        found = find(state, argv[-1])
        if not found:
            return 1
        found[1]["State"]["Running"] = False
        save(state)
        return 0
    if argv[:1] == ["rm"]:
        found = find(state, argv[1])
        if not found:
            return 1
        name = next(
            name
            for name, record in state["containers"].items()
            if record["Id"] == found[1]["Id"]
        )
        del state["containers"][name]
        save(state)
        return 0
    if argv[:2] == ["image", "rm"] and len(argv) == 3:
        found = find(state, argv[2])
        if not found or found[0] != "image":
            return 1
        key = next(
            key
            for key, record in state["images"].items()
            if record["Id"] == found[1]["Id"] or key == argv[2]
        )
        del state["images"][key]
        save(state)
        return 0
    if argv[:1] == ["cp"] and len(argv) == 3:
        identifier, _, container_source = argv[1].partition(":")
        found = find(state, identifier)
        if not found or not container_source:
            return 1
        runtime_mount = next(
            (
                mount
                for mount in found[1]["Mounts"]
                if mount["Destination"] == "/var/lib/agent-canon/runtime"
            ),
            None,
        )
        if runtime_mount is None:
            return 1
        clean_source = container_source.removesuffix("/.")
        try:
            relative = Path(clean_source).relative_to("/var/lib/agent-canon/runtime")
        except ValueError:
            return 1
        source = Path(runtime_mount["Source"]) / relative
        destination = Path(argv[2])
        if not source.is_dir():
            return 1
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination, dirs_exist_ok=True)
        return 0
    if argv[:1] == ["exec"]:
        index = argv.index("--workdir") + 2
        exec_environment = {}
        while index < len(argv) and argv[index] == "--env":
            key, _, value = argv[index + 1].partition("=")
            exec_environment[key] = value
            index += 2
        identifier = argv[index]
        command = argv[index + 1 :]
        found = find(state, identifier)
        if not found:
            return 0
        if command[:2] == [
            "python3",
            "/usr/local/share/agent-canon/runtime/tools/agent_tools/bootstrap_runtime.py",
        ]:
            if "target" in command[2:] and "add" in command[2:]:
                runtime_mount = next(
                    (
                        mount
                        for mount in found[1]["Mounts"]
                        if mount["Destination"] == "/var/lib/agent-canon/runtime"
                    ),
                    None,
                )
                digest = exec_environment.get("AGENT_CANON_TARGET_DIGEST", "")
                host_root = exec_environment.get("AGENT_CANON_TARGET_HOST_ROOT", "")
                container_root = exec_environment.get(
                    "AGENT_CANON_TARGET_CONTAINER_ROOT", f"/targets/{digest}"
                )
                if runtime_mount is None or not digest or not host_root:
                    return 1
                runtime_root = Path(runtime_mount["Source"])
                state_path = runtime_root / "state.json"
                if state_path.is_file():
                    lifecycle = json.loads(state_path.read_text(encoding="utf-8"))
                else:
                    lifecycle = {"targets": {}, "state": "ready"}
                target = {
                    "root": container_root,
                    "host_root": host_root,
                    "mode": "read-only",
                    "digest": digest,
                }
                lifecycle.setdefault("targets", {})[digest] = target
                state_path.write_text(json.dumps(lifecycle), encoding="utf-8")
                (runtime_root / "mounts.tsv").write_text(
                    f"target\t{digest}\t{host_root}\t/targets/{digest}\tread-only\n",
                    encoding="utf-8",
                )
                (runtime_root / "mounts.toml").write_text(
                    "[targets.{}]\nroot = \"{}\"\nmode = \"read-only\"\ndigest = \"{}\"\n".format(
                        digest, container_root, digest
                    ),
                    encoding="utf-8",
                )
                print(
                    json.dumps(
                        {
                            "schema": "agent-canon.bootstrap-receipt.v2",
                            "status": "ok",
                            "operation": "target_add",
                            "code": "target_registered",
                        }
                    )
                )
                return 0
            if "agent-canon" in command and "--version" in command:
                print("agent-canon 0.1.0")
                return 0
            operations = {"install", "update", "start", "stop", "uninstall"}
            operation = next((item for item in command[2:] if item in operations), "")
            if operation in {"install", "update"} or (
                "codex" in command[2:] and "prepare" in command[2:]
            ):
                _materialize_skill_exchange(state, found[1])
            if operation:
                print(
                    json.dumps(
                        {
                            "schema": "agent-canon.bootstrap-receipt.v2",
                            "status": "ok",
                            "operation": operation,
                            "code": {
                                "install": "installed",
                                "update": "updated",
                                "start": "ready",
                                "stop": "stopped",
                                "uninstall": "owned_resources_released",
                            }[operation],
                        }
                    )
                )
            return 0
        if command == ["agent-canon", "--version"]:
            print("agent-canon 0.1.0")
            return 0
        if command[:3] == ["agent-canon-tool", "tool", "run"]:
            print("route output: " + " ".join(command[3:]))
            return 0
        if command[:2] == [
            "python3",
            "/usr/local/share/agent-canon/runtime/tools/agent_tools/run_accumulated_agent_evals.py",
        ]:
            runtime_arg = command[command.index("--runtime-root") + 1]
            run_id = command[command.index("--run-id") + 1]
            target = next(
                mount
                for mount in found[1]["Mounts"]
                if mount["Destination"] == "/var/lib/agent-canon/runtime"
            )
            relative = Path(runtime_arg).relative_to("/var/lib/agent-canon/runtime")
            exchange = Path(target["Source"]) / relative
            eval_failed = os.environ.get("FAKE_EVAL_FAIL") == "1"
            (exchange / "eval-results").mkdir(parents=True, exist_ok=True)
            families = {
                "skill-workflow-prompt": (
                    "skill-eval-20260101T000000000000Z-0123456789-pass-bootstrap.md",
                    f"EVAL_RUN_ID=skill-{run_id}\n",
                ),
                "workflow-selection": (
                    "workflow-selection-eval-20260101T000000000000Z-0123456789-pass.md",
                    f"WORKFLOW_SELECTION_EVAL_RUN_ID=workflow-{run_id}\n",
                ),
                "report-quality": (
                    "report-quality-eval-20260101T000000000000Z-0123456789-pass.md",
                    f"REPORT_QUALITY_EVAL_RUN_ID=quality-{run_id}\n",
                ),
                "codex-agent-role": (
                    "codex-agent-role-eval-20260101T000000000000Z-0123456789-pass.md",
                    f"CODEX_AGENT_ROLE_EVAL_RUN_ID=role-{run_id}\n",
                ),
            }
            for family, (filename, content) in families.items():
                if eval_failed:
                    continue
                destination = exchange / "eval-results" / family / filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8")
            log_dir = exchange / "tasks" / run_id / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "01-codex-agent-role.stdout.txt").write_text(
                "producer=codex-agent-role\n", encoding="utf-8"
            )
            producer_status = "fail" if eval_failed else "pass"
            print(
                f"ACCUMULATED_AGENT_EVAL_PRODUCER=codex-agent-role:{producer_status}:"
                f"stdout=tasks/{run_id}/logs/01-codex-agent-role.stdout.txt:"
                f"stderr=tasks/{run_id}/logs/01-codex-agent-role.stderr.txt"
            )
            for name in ("skill-workflow-prompt", "workflow-selection", "report-quality"):
                print(
                    "ACCUMULATED_AGENT_EVAL_PRODUCER="
                    f"{name}:{producer_status}:"
                    f"stdout=tasks/{run_id}/logs/{name}.stdout.txt:"
                    f"stderr=tasks/{run_id}/logs/{name}.stderr.txt"
                )
            print("ACCUMULATED_AGENT_EVAL_PRODUCERS=4")
            print(
                "ACCUMULATED_AGENT_EVAL_FAILED="
                + (
                    "codex-agent-role,skill-workflow-prompt,workflow-selection,report-quality"
                    if eval_failed
                    else "-"
                )
            )
            print(f"ACCUMULATED_AGENT_EVAL={'fail' if eval_failed else 'pass'}")
            return 1 if eval_failed else 0
        if command == [
            "python3",
            "/usr/local/share/agent-canon/runtime/tools/agent_tools/runtime_exchange_cleanup.py",
        ]:
            runtime_mount = next(
                mount
                for mount in found[1]["Mounts"]
                if mount["Destination"] == "/var/lib/agent-canon/runtime"
            )
            runtime_root = Path(runtime_mount["Source"])
            for child in runtime_root.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            print("AGENT_CANON_RUNTIME_EXCHANGE_REMOVED=fixture")
            return 0
        if command == ["agent-canon", "fail"]:
            print(
                "failure output token=canary " + ("x" * 700) + " terminal-diagnostic",
                file=sys.stderr,
            )
            return 7
        if command[:1] != ["cat"]:
            return 0
        content = found[1].get("MountSnapshots", {}).get(command[1])
        if content is None:
            return 1
        print(content, end="")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
