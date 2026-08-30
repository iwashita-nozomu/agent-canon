#!/usr/bin/env python3
"""Minimal stateful Docker executable used by bootstrap behavioural tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def load() -> dict:
    """Load fake daemon state from the test-owned file."""
    path = Path(os.environ["FAKE_DOCKER_STATE"])
    if not path.exists():
        return {"images": {}, "containers": {}, "volumes": {}, "next": 1}
    return json.loads(path.read_text(encoding="utf-8"))


def save(state: dict) -> None:
    """Persist fake daemon state."""
    Path(os.environ["FAKE_DOCKER_STATE"]).write_text(
        json.dumps(state, sort_keys=True), encoding="utf-8"
    )


def volume_path(name: str) -> Path:
    """Return the fake daemon's private backing directory for one volume."""
    return Path(os.environ["FAKE_DOCKER_STATE"]).parent / f".fake-volume-{name}"


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


def _label_filters(argv: list[str]) -> dict[str, str]:
    """Extract exact label filters used by host resource reconciliation."""
    result = {}
    for index, item in enumerate(argv):
        if item != "--filter" or index + 1 >= len(argv):
            continue
        value = argv[index + 1]
        if value.startswith("label="):
            key, _, label_value = value[6:].partition("=")
            result[key] = label_value
    return result


def _matches_labels(record: dict, filters: dict[str, str]) -> bool:
    """Match Docker's conjunction of exact label filters."""
    record_labels = record.get("Config", {}).get("Labels", {})
    return all(record_labels.get(key) == value for key, value in filters.items())


def _formatted_container(record: dict, fmt: str) -> str | None:
    """Return the scalar/container-list fields used by bootstrap readback."""
    if fmt == "{{.Id}}":
        return str(record["Id"])
    if fmt == "{{.Config.Image}}":
        return str(record.get("Config", {}).get("Image", ""))
    if fmt == "{{.Config.User}}":
        return str(record.get("Config", {}).get("User", ""))
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
    if fmt == '{{range .Mounts}}{{if eq .Type "volume"}}{{printf "volume:%s\\t%s\\t%t\\n" .Name .Destination .RW}}{{else}}{{printf "%s\\t%s\\t%t\\n" .Source .Destination .RW}}{{end}}{{end}}':
        return "".join(
            (
                f"volume:{mount['Name']}\t{mount['Destination']}\t"
                f"{'true' if mount.get('RW') else 'false'}\n"
                if mount.get("Type") == "volume"
                else f"{mount['Source']}\t{mount['Destination']}\t"
                f"{'true' if mount.get('RW') else 'false'}\n"
            )
            for mount in record.get("Mounts", [])
        )
    if fmt == "{{range .Mounts}}{{printf \"%s\\t%s\\t%t\\n\" .Source .Destination .RW}}{{end}}":
        return "".join(
            f"{mount['Source']}\t{mount['Destination']}\t"
            f"{'true' if mount.get('RW') else 'false'}\n"
            for mount in record.get("Mounts", [])
        )
    return None


def _materialize_skill_exchange(state: dict, container: dict) -> None:
    """Model resident materializer output in the writable runtime exchange."""
    exchange_mount = next(
        (
            mount
            for mount in container.get("Mounts", [])
            if mount["Destination"] == "/var/lib/agent-canon/exchange"
        ),
        None,
    )
    if exchange_mount is None:
        return
    image_ref = container.get("Config", {}).get("Image", "")
    image = find(state, image_ref)
    if image is None or image[0] != "image":
        return
    source_root = Path(str(image[1].get("SourceRoot", "")))
    # The fake daemon is itself the resident boundary.  Use the canonical
    # owner shipped with this test checkout while reading all canonical inputs
    # from the image's source snapshot, including older source snapshots used
    # by stale-resident fixtures.
    materializer = Path(__file__).resolve().parents[2] / "tools/agent/skills/skill_shim_materializer.py"
    if not materializer.is_file():
        return
    staging_root = Path(exchange_mount["Source"]) / "skill-projection"
    staged_skill = staging_root / ".codex/personal/skills/agent-orchestration/SKILL.md"
    if staged_skill.is_file():
        return
    staging_root.mkdir(parents=True, exist_ok=True)
    materialized = subprocess.run(
        [
            sys.executable,
            str(materializer),
            "materialize",
            "--root",
            str(source_root),
            "--output-root",
            str(staging_root),
            "--image-build",
            "--all",
        ],
        cwd=source_root,
        env={**os.environ, "AGENT_CANON_IMAGE_BUILD": "1"},
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if materialized.returncode != 0:
        return


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
    state.setdefault("volumes", {})
    if argv[:2] == ["volume", "inspect"]:
        name = argv[-1]
        record = state["volumes"].get(name)
        if record is None:
            return 1
        if "--format" in argv:
            fmt = argv[argv.index("--format") + 1]
            if fmt == "{{.Name}}":
                print(name)
                return 0
            if fmt == '{{index .Labels "io.agent-canon.runtime"}}':
                print(record.get("Labels", {}).get("io.agent-canon.runtime", ""))
                return 0
            if fmt == '{{index .Labels "io.agent-canon.control-root-digest"}}':
                print(record.get("Labels", {}).get("io.agent-canon.control-root-digest", ""))
                return 0
            return 2
        print(json.dumps([record]))
        return 0
    if argv[:2] == ["volume", "create"]:
        name = argv[-1]
        if name in state["volumes"]:
            print(name)
            return 0
        record = {
            "Name": name,
            "Labels": labels(argv),
            "Mountpoint": str(volume_path(name)),
            "UID": None,
            "GID": None,
            "Mode": "0755",
        }
        volume_path(name).mkdir(parents=True, exist_ok=True)
        state["volumes"][name] = record
        save(state)
        print(name)
        return 0
    if argv[:2] == ["volume", "ls"]:
        filters = _label_filters(argv)
        names = [
            name for name, record in state["volumes"].items()
            if all(record.get("Labels", {}).get(key) == value for key, value in filters.items())
        ]
        print("\n".join(names))
        return 0
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
        filters = _label_filters(argv)
        if "--format" not in argv:
            print(
                "\n".join(
                    dict.fromkeys(
                        record["Id"]
                        for record in state["images"].values()
                        if _matches_labels(record, filters)
                    )
                )
            )
            return 0
        image_format = argv[argv.index("--format") + 1]
        if image_format != r"{{.ID}}\t{{.Repository}}\t{{.Tag}}":
            return 2
        rows = []
        for key, record in state["images"].items():
            if not _matches_labels(record, filters):
                continue
            if key.startswith("untagged:"):
                repository, tag = "<none>", "<none>"
            elif ":" in key:
                repository, tag = key.rsplit(":", 1)
            else:
                repository, tag = key, "<none>"
            rows.append(f"{record['Id']}\t{repository}\t{tag}")
        print("\n".join(rows))
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
        filters = _label_filters(argv)
        if "--format" not in argv:
            print(
                "\n".join(
                    record["Id"]
                    for record in state["containers"].values()
                    if _matches_labels(record, filters)
                )
            )
            return 0
        container_format = argv[argv.index("--format") + 1]
        if container_format != r"{{.ID}}\t{{.Names}}":
            return 2
        print(
            "\n".join(
                f"{record['Id']}\t{name}"
                for name, record in state["containers"].items()
                if _matches_labels(record, filters)
            )
        )
        return 0
    if argv[:1] == ["create"]:
        name = argv[argv.index("--name") + 1]
        user = argv[argv.index("--user") + 1] if "--user" in argv else ""
        parsed_mounts = []
        mount_snapshots = {}
        for index, item in enumerate(argv):
            if item != "--mount":
                continue
            values = dict(
                part.split("=", 1) for part in argv[index + 1].split(",") if "=" in part
            )
            mount_type = values.get("type", "bind")
            source = values.get("src", "")
            name_value = source
            if mount_type == "volume":
                volume_path(source).mkdir(parents=True, exist_ok=True)
                state["volumes"].setdefault(
                    source,
                    {
                        "Name": source,
                        "Labels": {},
                        "Mountpoint": str(volume_path(source)),
                        "UID": None,
                        "GID": None,
                        "Mode": "0755",
                    },
                )
                source = str(volume_path(source))
            if os.environ.get("FAKE_DOCKER_CANONICALIZE_MOUNTS") == "1":
                source = str(Path(source).resolve())
            parsed_mounts.append(
                {
                    "Type": mount_type,
                    "Source": source,
                    "Name": name_value,
                    "Destination": values["dst"],
                    "RW": "readonly" not in argv[index + 1],
                    "Mode": "ro" if "readonly" in argv[index + 1] else "rw",
                }
            )
            if values["dst"] == "/var/lib/agent-canon/mount-registry.toml":
                mount_snapshots[values["dst"]] = (
                    Path(source).read_text(encoding="utf-8")
                    if Path(source).is_file()
                    else ""
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
                "User": user,
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
    if argv[:1] == ["run"]:
        # The real initializer is a short-lived container that prepares the
        # named controller-state volume.  Model its one-time legacy copy and
        # return without retaining a task container.
        if "--mount" not in argv:
            return 2
        volume_name = ""
        legacy_source = ""
        for index, item in enumerate(argv):
            if item != "--mount" or index + 1 >= len(argv):
                continue
            values = dict(
                part.split("=", 1)
                for part in argv[index + 1].split(",")
                if "=" in part
            )
            if values.get("type") == "volume" and values.get("dst") == "/var/lib/agent-canon/runtime":
                volume_name = values.get("src", "")
            if values.get("type") == "bind" and values.get("dst") == "/var/lib/agent-canon/legacy-state":
                legacy_source = values.get("src", "")
        if not volume_name:
            return 2
        backing = volume_path(volume_name)
        backing.mkdir(parents=True, exist_ok=True)
        legacy = Path(legacy_source) if legacy_source else None
        marker = backing / ".agent-canon-controller-volume-v1"
        digest = next(
            (
                item.split("=", 1)[1]
                for item in argv
                if item.startswith("AGENT_CANON_VOLUME_DIGEST=")
            ),
            "",
        )

        def same_tree(source: Path, destination: Path) -> bool:
            source_files = sorted(
                item.relative_to(source).as_posix()
                for item in source.rglob("*")
                if not item.is_dir()
            )
            destination_files = sorted(
                item.relative_to(destination).as_posix()
                for item in destination.rglob("*")
                if not item.is_dir()
            )
            if source_files != destination_files:
                return False
            return all(
                (source / relative).is_file()
                and not (source / relative).is_symlink()
                and (destination / relative).is_file()
                and not (destination / relative).is_symlink()
                and (source / relative).read_bytes() == (destination / relative).read_bytes()
                for relative in source_files
            )

        def migrate_file(source: Path, destination: Path) -> bool:
            if destination.exists():
                return destination.is_file() and not destination.is_symlink() and source.read_bytes() == destination.read_bytes()
            shutil.copy2(source, destination)
            return True

        def migrate_tree(source: Path, destination: Path) -> bool:
            if destination.exists():
                return destination.is_dir() and not destination.is_symlink() and same_tree(source, destination)
            shutil.copytree(source, destination)
            return True

        if marker.is_symlink() or (marker.exists() and marker.read_text(encoding="utf-8") != f"agent-canon-controller-volume/v1\n{digest}\n"):
            return 1
        if not marker.exists() and legacy is not None and legacy.is_dir():
            for name in ("state.json", "owner.json"):
                source = legacy / name
                if source.exists() and (not source.is_file() or source.is_symlink() or not migrate_file(source, backing / name)):
                    return 1
            for name in ("receipts", "generations", "tasks"):
                source = legacy / name
                destination = backing / name
                if source.exists() and (not source.is_dir() or source.is_symlink() or not migrate_tree(source, destination)):
                    return 1
            marker.write_text(f"agent-canon-controller-volume/v1\n{digest}\n", encoding="utf-8")
        if marker.read_text(encoding="utf-8") != f"agent-canon-controller-volume/v1\n{digest}\n":
            return 1
        if legacy is not None and legacy.is_dir():
            for name in ("state.json", "owner.json"):
                source = legacy / name
                if source.exists() and (not (backing / name).is_file() or source.read_bytes() != (backing / name).read_bytes()):
                    return 1
            for name in ("receipts", "generations", "tasks"):
                source = legacy / name
                if source.exists() and (not (backing / name).is_dir() or not same_tree(source, backing / name)):
                    return 1
        state["volumes"][volume_name]["UID"] = int(next(item.split("=", 1)[1] for item in argv if item.startswith("AGENT_CANON_VOLUME_UID=")))
        state["volumes"][volume_name]["GID"] = int(next(item.split("=", 1)[1] for item in argv if item.startswith("AGENT_CANON_VOLUME_GID=")))
        state["volumes"][volume_name]["Mode"] = "0700"
        print(f"marker\t{digest}\ncontent\tok")
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
        identifier = argv[-1]
        found = find(state, identifier)
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
        # Docker removes the requested tag when a tag is supplied.  Resolving
        # the tag to its image ID first would remove an earlier alias instead,
        # which can silently delete the active image from this fake daemon.
        if argv[2] in state["images"]:
            del state["images"][argv[2]]
            save(state)
            return 0
        found = find(state, argv[2])
        if not found or found[0] != "image":
            return 1
        keys = [
            key for key, record in state["images"].items() if record["Id"] == found[1]["Id"]
        ]
        for key in keys:
            del state["images"][key]
        save(state)
        return 0
    if argv[:2] == ["volume", "rm"] and len(argv) == 3:
        name = argv[2]
        if name not in state["volumes"]:
            return 1
        del state["volumes"][name]
        backing = volume_path(name)
        if backing.is_dir():
            shutil.rmtree(backing)
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
        runtime_mount = next(
            (
                mount
                for mount in found[1].get("Mounts", [])
                if mount["Destination"] == "/var/lib/agent-canon/runtime"
                and mount.get("Type") == "volume"
            ),
            None,
        )
        if runtime_mount is not None:
            volume = state["volumes"].get(runtime_mount.get("Name", ""), {})
            user = str(found[1].get("Config", {}).get("User", ""))
            uid, _, gid = user.partition(":")
            if (
                volume.get("UID") != int(uid or -1)
                or volume.get("GID") != int(gid or -1)
                or volume.get("Mode") != "0700"
            ):
                return 1
            probe = Path(runtime_mount["Source"]) / ".fake-resident-write-read"
            probe.write_text("resident\n", encoding="utf-8")
            if probe.read_text(encoding="utf-8") != "resident\n":
                return 1
            probe.unlink()
            volume["ResidentWriteReadback"] = True
            save(state)
        if command[:2] == [
            "python3",
            "/usr/local/share/agent-canon/runtime/tools/runtime/container/bootstrap_runtime.py",
        ]:
            failed_operation = os.environ.get("FAKE_DOCKER_FAIL_CONTROLLER_OPERATION", "")
            if failed_operation and failed_operation in command[2:]:
                return int(os.environ.get("FAKE_DOCKER_FAIL_CONTROLLER_RC", "41"))
            if command[-1:] == ["gc"] or command[-2:] == ["gc", "--dry-run"]:
                print(
                    json.dumps(
                        {
                            "schema": "agent-canon.bootstrap-receipt.v2",
                            "status": "ok",
                            "operation": "gc",
                            "code": "state_gc_complete",
                            "details": {"docker_resources": "host-owned"},
                        },
                        separators=(",", ":"),
                    )
                )
                return 0
            if "target" in command[2:] and "add" in command[2:]:
                runtime_mount = next(
                    (
                        mount
                        for mount in found[1]["Mounts"]
                        if mount["Destination"] == "/var/lib/agent-canon/runtime"
                    ),
                    None,
                )
                exchange_mount = next(
                    (
                        mount
                        for mount in found[1]["Mounts"]
                        if mount["Destination"] == "/var/lib/agent-canon/exchange"
                    ),
                    None,
                )
                digest = exec_environment.get("AGENT_CANON_TARGET_DIGEST", "")
                host_root = exec_environment.get("AGENT_CANON_TARGET_HOST_ROOT", "")
                container_root = exec_environment.get(
                    "AGENT_CANON_TARGET_CONTAINER_ROOT", f"/targets/{digest}"
                )
                if runtime_mount is None or exchange_mount is None or not digest or not host_root:
                    return 1
                runtime_root = Path(runtime_mount["Source"])
                exchange_root = Path(exchange_mount["Source"])
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
                (exchange_root / "mounts.tsv").write_text(
                    f"target\t{digest}\t{host_root}\t/targets/{digest}\tread-only\n",
                    encoding="utf-8",
                )
                (exchange_root / "mounts.toml").write_text(
                    "schema = \"agent-canon.mount-registry.v2\"\n\n[targets.{}]\nroot = \"{}\"\nmode = \"read-only\"\ndigest = \"{}\"\n".format(
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
            if "rollback" in command[2:]:
                runtime_mount = next(
                    (
                        mount
                        for mount in found[1]["Mounts"]
                        if mount["Destination"] == "/var/lib/agent-canon/runtime"
                    ),
                    None,
                )
                current_id = exec_environment.get("AGENT_CANON_CURRENT_IMAGE_ID", "")
                current_ref = exec_environment.get("AGENT_CANON_CURRENT_IMAGE_REF", "")
                if runtime_mount is None or not current_id or not current_ref:
                    return 1
                runtime_root = Path(runtime_mount["Source"])
                private_log = exec_environment.get("AGENT_CANON_PRIVATE_LOG_ROOT", "")
                source_sync_mount = next(
                    mount
                    for mount in found[1]["Mounts"]
                    if mount["Destination"] == "/var/lib/agent-canon/source-sync.json"
                )
                registry_mount = next(
                    mount
                    for mount in found[1]["Mounts"]
                    if mount["Destination"] == "/var/lib/agent-canon/mount-registry.toml"
                )
                exchange_mount = next(
                    (
                        mount
                        for mount in found[1]["Mounts"]
                        if mount["Destination"] == "/var/lib/agent-canon/exchange"
                    ),
                    None,
                )
                plan = (
                    Path(exchange_mount["Source"]) / "rollback-plan.tsv"
                    if exchange_mount is not None
                    else runtime_root / "rollback-plan.tsv"
                )
                plan_lines = [
                    "schema\tagent-canon.rollback-plan.v1",
                    f"image-id\t{current_id}",
                    f"image-ref\t{current_ref}",
                    f"mount\tmount\t{runtime_root}\t/var/lib/agent-canon/runtime\tfalse",
                    f"mount\tmount\t{source_sync_mount['Source']}\t/var/lib/agent-canon/source-sync.json\ttrue",
                    f"mount\tmount\t{private_log}\t/var/lib/agent-canon/private-log\ttrue",
                    f"mount\tmount\t{registry_mount['Source']}\t/var/lib/agent-canon/mount-registry.toml\ttrue",
                ]
                mounts_path = (
                    Path(exchange_mount["Source"]) / "mounts.tsv"
                    if exchange_mount is not None
                    else runtime_root / "mounts.tsv"
                )
                if mounts_path.is_file():
                    for line in mounts_path.read_text(encoding="utf-8").splitlines():
                        fields = line.split("\t")
                        if len(fields) == 5 and fields[0] == "target":
                            plan_lines.append(
                                f"mount\tmount\t{fields[2]}\t{fields[3]}\ttrue"
                            )
                plan.write_text("\n".join(plan_lines) + "\n", encoding="utf-8")
                print(
                    json.dumps(
                        {
                            "schema": "agent-canon.bootstrap-receipt.v2",
                            "status": "ok",
                            "operation": "rollback",
                            "code": "previous_generation_restored",
                        }
                    )
                )
                return 0
            operations = {"install", "update", "start", "stop", "uninstall"}
            operation = next((item for item in command[2:] if item in operations), "")
            if operation == "install" and runtime_mount is not None:
                state_path = Path(runtime_mount["Source"]) / "state.json"
                if state_path.is_file():
                    lifecycle = json.loads(state_path.read_text(encoding="utf-8"))
                    lifecycle.update(
                        {
                            "targets": {},
                            "generations": {},
                            "current_generation": None,
                            "rollback_generation": None,
                            "generation_counter": 0,
                            "active_task_count": 0,
                            "tasks": {},
                        }
                    )
                    state_path.write_text(json.dumps(lifecycle), encoding="utf-8")
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
            "/usr/local/share/agent-canon/runtime/eval/producers/run_accumulated_agent_evals.py",
        ]:
            runtime_arg = command[command.index("--runtime-root") + 1]
            run_id = command[command.index("--run-id") + 1]
            target = next(
                mount
                for mount in found[1]["Mounts"]
                if mount["Destination"] == "/var/lib/agent-canon/exchange"
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
            "/usr/local/share/agent-canon/runtime/tools/runtime/archive/runtime_exchange_cleanup.py",
        ]:
            runtime_mount = next(
                mount
                for mount in found[1]["Mounts"]
                if mount["Destination"] == "/var/lib/agent-canon/exchange"
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
