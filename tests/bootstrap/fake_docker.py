#!/usr/bin/env python3
"""Minimal stateful Docker executable used by bootstrap behavioural tests."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
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


def operational_root(backing: Path) -> Path:
    """Use the post-#989 runtime layout, with a legacy fixture fallback."""
    runtime = backing / "runtime"
    return runtime if runtime.is_dir() else backing


def tree_digest(root: Path) -> str:
    """Hash regular-file content with stable relative names."""
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            continue
        if path.is_file():
            if path.name == ".agent-canon-private-log-v1":
                continue
            entries.append(
                f"{hashlib.sha256(path.read_bytes()).hexdigest()}  ./"
                f"{path.relative_to(root).as_posix()}\n"
            )
    return hashlib.sha256("".join(sorted(entries)).encode("utf-8")).hexdigest()


def projection_digest(root: Path) -> str:
    """Hash the fixed controller projection file set, including absence."""
    entries = []
    for name in ("mounts.toml", "mounts.tsv", "rollback-plan.tsv", "rollback-mounts.tsv"):
        path = root / name
        if path.is_file() and not path.is_symlink():
            value = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            value = "absent"
        entries.append(f"{name}\t{value}\n")
    return hashlib.sha256("".join(entries).encode("utf-8")).hexdigest()


def codex_digest(root: Path) -> str:
    """Hash Codex regular files/modes and managed link path/targets."""
    entries = []
    regular = sorted(path for path in root.rglob("*") if path.is_file() and not path.is_symlink())
    links = sorted(path for path in root.rglob("*") if path.is_symlink())
    for path in regular:
        entries.append(
            f"file\t./{path.relative_to(root).as_posix()}\t"
            f"{path.stat(follow_symlinks=False).st_mode & 0o777}\t"
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}\n"
        )
    for path in links:
        entries.append(
            f"link\t./{path.relative_to(root).as_posix()}\t{os.readlink(path)}\n"
        )
    return hashlib.sha256("".join(entries).encode("utf-8")).hexdigest()


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
    if fmt == '{{index .Config.Labels "io.agent-canon.projection-layout"}}':
        return str(
            record.get("Config", {})
            .get("Labels", {})
            .get("io.agent-canon.projection-layout", "")
        )
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
    volume_mount = next(
        (
            mount
            for mount in container.get("Mounts", [])
            if mount["Destination"] == "/var/lib/agent-canon"
        ),
        None,
    )
    if volume_mount is None:
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
    staging_root = operational_root(Path(volume_mount["Source"])) / "container-runtime" / "skill-projection"
    staged_skill = staging_root / ".codex/personal/skills/agent-orchestration/SKILL.md"
    if staged_skill.is_file():
        return
    staging_root.mkdir(parents=True, exist_ok=True)
    state_root = Path(os.environ["FAKE_DOCKER_STATE"]).parent
    with tempfile.TemporaryDirectory(
        prefix=".fake-image-schema-tools-", dir=state_root
    ) as schema_bin_raw:
        schema_bin = Path(schema_bin_raw)
        schema_receipt = schema_bin / "receipt.tsv"
        schema_tool = """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

root = Path(os.environ["FAKE_SCHEMA_SOURCE_ROOT"]).resolve()
receipt = Path(os.environ["FAKE_SCHEMA_TOOL_RECEIPT"])
sys.path.insert(0, os.environ["FAKE_SCHEMA_OWNER_ROOT"])
from tools.runtime.container import stdlib_yaml

config = root / "schemas/agent-canon/yamllint.yaml"
documents = (
    root / "agents/skills/catalog.yaml",
    root / "agents/skills/skill-dependencies.yaml",
    root / "tools/catalog.yaml",
)
schemas = (
    root / "schemas/agent-canon/skill-catalog.schema.json",
    root / "schemas/agent-canon/skill-dependencies.schema.json",
    root / "schemas/agent-canon/tool-catalog.schema.json",
)

def regular(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()

tool = Path(sys.argv[0]).name
arguments = sys.argv[1:]
if tool == "yamllint":
    expected = ["--strict", "--config-file", str(config), *(str(path) for path in documents)]
    if arguments != expected or not all(regular(path) for path in (config, *documents)):
        raise SystemExit(91)
    try:
        for path in (config, *documents):
            stdlib_yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SystemExit(92)
    record = "yamllint"
elif tool == "check-jsonschema":
    expected_pairs = tuple(zip(schemas, documents))
    try:
        pair_index = next(
            index
            for index, (schema, document) in enumerate(expected_pairs)
            if arguments == ["--schemafile", str(schema), str(document)]
        )
    except StopIteration:
        raise SystemExit(93)
    schema, document = expected_pairs[pair_index]
    if not regular(schema) or not regular(document):
        raise SystemExit(94)
    try:
        json.loads(schema.read_text(encoding="utf-8"))
        stdlib_yaml.safe_load(document.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        raise SystemExit(95)
    record = f"check-jsonschema\\t{pair_index}"
else:
    raise SystemExit(96)
with receipt.open("a", encoding="utf-8") as stream:
    stream.write(record + "\\n")
"""
        for name in ("yamllint", "check-jsonschema"):
            executable = schema_bin / name
            executable.write_text(schema_tool, encoding="utf-8")
            executable.chmod(0o755)
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
            env={
                **os.environ,
                "AGENT_CANON_IMAGE_BUILD": "1",
                "FAKE_SCHEMA_OWNER_ROOT": str(materializer.parents[3]),
                "FAKE_SCHEMA_SOURCE_ROOT": str(source_root),
                "FAKE_SCHEMA_TOOL_RECEIPT": str(schema_receipt),
                "PATH": f"{schema_bin}{os.pathsep}{os.environ.get('PATH', '')}",
            },
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        expected_receipt = [
            "yamllint",
            "check-jsonschema\t0",
            "check-jsonschema\t1",
            "check-jsonschema\t2",
        ]
        if (
            materialized.returncode != 0
            or not schema_receipt.is_file()
            or schema_receipt.read_text(encoding="utf-8").splitlines()
            != expected_receipt
        ):
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
                if os.environ.get("FAKE_DOCKER_FAIL_VOLUME_NAME_READBACK_ONCE") == "1" and not state.get(
                    "_volume_name_readback_failed_once"
                ):
                    state["_volume_name_readback_failed_once"] = True
                    save(state)
                    return 1
                print(name)
                return 0
            if fmt == '{{index .Labels "io.agent-canon.runtime"}}':
                if os.environ.get("FAKE_DOCKER_FAIL_VOLUME_LABEL_READBACK_ONCE") == "io.agent-canon.runtime" and not state.get(
                    "_volume_label_readback_failed_once"
                ):
                    state["_volume_label_readback_failed_once"] = True
                    save(state)
                    return 1
                print(record.get("Labels", {}).get("io.agent-canon.runtime", ""))
                return 0
            if fmt == '{{index .Labels "io.agent-canon.control-root-digest"}}':
                print(record.get("Labels", {}).get("io.agent-canon.control-root-digest", ""))
                return 0
            if fmt == '{{index .Labels "io.agent-canon.state"}}':
                print(record.get("Labels", {}).get("io.agent-canon.state", ""))
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
        if (
            os.environ.get("FAKE_DOCKER_REPLACE_CONTAINER_ON_ID_READ") == identifier
            and not state.get("_container_replaced_on_id_read")
        ):
            original_id = found[1]["Id"]
            original_name = next(
                name for name, record in state["containers"].items() if record is found[1]
            )
            foreign = json.loads(json.dumps(found[1]))
            foreign["Id"] = "container-foreign-replacement"
            foreign["Config"]["Image"] = "foreign-image"
            foreign["Config"]["Labels"] = {
                "io.agent-canon.runtime": "foreign-v1",
                "io.agent-canon.control-root-digest": "foreign-control-root",
            }
            state["containers"][original_name] = foreign
            state["_container_replaced_on_id_read"] = True
            save(state)
            print(original_id)
            return 0
        health = found[1].get("State", {}).get("Health", {})
        if (
            found[1].get("State", {}).get("Running")
            and health.get("Status") == "starting"
        ):
            polls = int(os.environ.get("FAKE_DOCKER_HEALTH_POLLS", "0"))
            found[1]["health_polls"] = int(found[1].get("health_polls", 0)) + 1
            if (
                os.environ.get("FAKE_DOCKER_HEALTH_NEVER") != "1"
                and found[1]["health_polls"] > polls
            ):
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
        copy_environment = {}
        for index, item in enumerate(argv):
            if item == "--env" and index + 1 < len(argv) and "=" in argv[index + 1]:
                key, value = argv[index + 1].split("=", 1)
                copy_environment[key] = value
        copy_direction = copy_environment.get("AGENT_CANON_COPY_DIRECTION", "")
        transaction_action = copy_environment.get("AGENT_CANON_VOLUME_TRANSACTION_ACTION", "")
        if transaction_action:
            volume_name = ""
            for index, item in enumerate(argv):
                if item != "--mount" or index + 1 >= len(argv):
                    continue
                values = dict(
                    part.split("=", 1)
                    for part in argv[index + 1].split(",")
                    if "=" in part
                )
                if values.get("type") == "volume" and values.get("dst") == "/var/lib/agent-canon":
                    volume_name = values.get("src", "")
            if not volume_name or volume_name not in state["volumes"]:
                return 1
            backing = volume_path(volume_name)
            volume_record = state["volumes"][volume_name]
            expected_digest = next(
                (
                    item.split("=", 1)[1]
                    for item in argv
                    if item.startswith("AGENT_CANON_VOLUME_DIGEST=")
                ),
                "",
            )
            if not expected_digest:
                marker = backing / ".agent-canon-controller-volume-v1"
                if marker.is_file() and not marker.is_symlink():
                    marker_lines = marker.read_text(encoding="utf-8").splitlines()
                    if len(marker_lines) == 2:
                        expected_digest = marker_lines[1]
            if (
                volume_record.get("Name") != volume_name
                or volume_record.get("Labels", {}).get("io.agent-canon.runtime")
                != "shared-v1"
                or volume_record.get("Labels", {}).get("io.agent-canon.control-root-digest")
                != expected_digest
                or volume_record.get("Labels", {}).get("io.agent-canon.state")
                != "controller-v1"
            ):
                return 1
            runtime = operational_root(backing)
            transaction = backing / ".agent-canon-bootstrap-transaction-v1"
            manifest = transaction / "manifest.tsv"
            logical_paths = (
                "state.json",
                "owner.json",
                "mounts.toml",
                "mounts.tsv",
                "rollback-plan.tsv",
                "rollback-mounts.tsv",
                "previous-image-id",
                "generations",
                "tasks",
                "container-runtime",
            )
            def snapshot_failure() -> int:
                if transaction.is_dir() and not transaction.is_symlink():
                    shutil.rmtree(transaction)
                return 1

            if transaction_action == "snapshot":
                marker = backing / ".agent-canon-controller-volume-v1"
                if (
                    not backing.is_dir()
                    or backing.is_symlink()
                    or not runtime.is_dir()
                    or runtime.is_symlink()
                    or not marker.is_file()
                    or marker.is_symlink()
                    or transaction.exists()
                    or transaction.is_symlink()
                ):
                    return 1
                transaction.mkdir(mode=0o700)
                manifest.write_text(
                    "schema\tagent-canon.volume-transaction.v1\n", encoding="utf-8"
                )
                for relative in logical_paths:
                    source = runtime / relative
                    if source.exists() or source.is_symlink():
                        if source.is_symlink() or not (source.is_file() or source.is_dir()):
                            return snapshot_failure()
                        if source.is_dir():
                            if any(
                                path.is_symlink()
                                or (not path.is_dir() and not path.is_file())
                                or (path.is_file() and path.stat().st_nlink > 1)
                                for path in source.rglob("*")
                            ):
                                return snapshot_failure()
                        elif source.stat().st_nlink > 1:
                            return snapshot_failure()
                        with manifest.open("a", encoding="utf-8") as handle:
                            handle.write(f"present\t{relative}\n")
                        if source.is_dir():
                            shutil.copytree(source, transaction / relative, symlinks=True)
                        else:
                            shutil.copy2(source, transaction / relative)
                    else:
                        with manifest.open("a", encoding="utf-8") as handle:
                            handle.write(f"absent\t{relative}\n")
                return 0
            if transaction_action == "restore":
                if (
                    not backing.is_dir()
                    or backing.is_symlink()
                    or not runtime.is_dir()
                    or runtime.is_symlink()
                    or not transaction.is_dir()
                    or transaction.is_symlink()
                    or not manifest.is_file()
                    or manifest.is_symlink()
                ):
                    return 1
                lines = manifest.read_text(encoding="utf-8").splitlines()
                if not lines or lines[0] != "schema\tagent-canon.volume-transaction.v1":
                    return 1
                entries = [line.split("\t", 1) for line in lines[1:]]
                if [entry[1] for entry in entries] != list(logical_paths):
                    return 1
                for status, relative in entries:
                    source = transaction / relative
                    if status == "present" and (not source.exists() or source.is_symlink()):
                        return 1
                    if status == "absent" and source.exists():
                        return 1
                restore_stage = transaction / ".restore-stage" / "runtime"
                restore_old = transaction / ".restore-old" / "runtime"
                restore_stage.mkdir(parents=True)
                restore_old.mkdir(parents=True)
                touched: list[str] = []
                try:
                    for status, relative in entries:
                        if status != "present":
                            continue
                        source = transaction / relative
                        if source.is_dir():
                            if any(
                                path.is_symlink()
                                or (not path.is_dir() and not path.is_file())
                                or (path.is_file() and path.stat().st_nlink > 1)
                                for path in source.rglob("*")
                            ):
                                raise OSError("invalid restore tree")
                        elif source.stat().st_nlink > 1:
                            raise OSError("invalid restore file")
                        destination = restore_stage / relative
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        if source.is_dir():
                            shutil.copytree(source, destination, symlinks=True)
                        else:
                            shutil.copy2(source, destination)
                    for status, relative in entries:
                        destination = runtime / relative
                        old = restore_old / relative
                        staged = restore_stage / relative
                        if destination.exists() or destination.is_symlink():
                            old.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(destination), str(old))
                            touched.append(relative)
                        if status == "present":
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            if os.environ.get("FAKE_DOCKER_VOLUME_RESTORE_FAIL_AFTER") == relative:
                                raise OSError("injected restore failure")
                            shutil.move(str(staged), str(destination))
                            if relative not in touched:
                                touched.append(relative)
                except (OSError, shutil.Error):
                    for relative in reversed(touched):
                        destination = runtime / relative
                        old = restore_old / relative
                        if destination.is_dir() and not destination.is_symlink():
                            shutil.rmtree(destination)
                        elif destination.exists() or destination.is_symlink():
                            destination.unlink()
                        if old.exists() or old.is_symlink():
                            old.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(old), str(destination))
                    shutil.rmtree(transaction / ".restore-stage", ignore_errors=True)
                    shutil.rmtree(transaction / ".restore-old", ignore_errors=True)
                    return 1
                shutil.rmtree(transaction / ".restore-stage")
                shutil.rmtree(transaction / ".restore-old")
                return 0
            if transaction_action == "clear":
                if transaction.is_symlink() or (transaction.exists() and not transaction.is_dir()):
                    return 1
                if transaction.is_dir():
                    shutil.rmtree(transaction)
                return 0
            return 1
        if copy_environment.get("AGENT_CANON_VOLUME_PROBE") == "1":
            user = argv[argv.index("--user") + 1] if "--user" in argv else ""
            user_parts = user.split(":")
            exact_numeric_user = (
                len(user_parts) == 2
                and all(part.isdigit() for part in user_parts)
            )
            allow_legacy = copy_environment.get(
                "AGENT_CANON_VOLUME_ALLOW_LEGACY", "0"
            )
            if allow_legacy not in {"0", "1"}:
                return 1
            network = (
                argv[argv.index("--network") + 1]
                if "--network" in argv and argv.index("--network") + 1 < len(argv)
                else ""
            )
            tmpfs = (
                argv[argv.index("--tmpfs") + 1]
                if "--tmpfs" in argv and argv.index("--tmpfs") + 1 < len(argv)
                else ""
            )
            volume_name = ""
            volume_nocopy = False
            for index, item in enumerate(argv):
                if item != "--mount" or index + 1 >= len(argv):
                    continue
                values = dict(
                    part.split("=", 1)
                    for part in argv[index + 1].split(",")
                    if "=" in part
                )
                if values.get("type") == "volume" and values.get("dst") == "/var/lib/agent-canon":
                    volume_name = values.get("src", "")
                    volume_nocopy = "volume-nocopy" in argv[index + 1].split(",")
            record = state["volumes"].get(volume_name)
            if record is None:
                return 1
            backing = volume_path(volume_name)
            marker = backing / ".agent-canon-controller-volume-v1"
            expected_marker = (
                f"agent-canon-controller-volume/v1\n"
                f"{copy_environment.get('AGENT_CANON_VOLUME_DIGEST', '')}\n"
            )
            if (
                user != f"{record.get('UID')}:{record.get('GID')}"
                or user
                != f"{copy_environment.get('AGENT_CANON_VOLUME_UID', '')}:"
                f"{copy_environment.get('AGENT_CANON_VOLUME_GID', '')}"
                or not exact_numeric_user
                or "--read-only" not in argv
                or network != "none"
                or tmpfs != "/tmp"
                or not volume_nocopy
                or "--entrypoint" not in argv
                or argv[argv.index("--entrypoint") + 1] != "/bin/sh"
                or record.get("Mode") != "0700"
                or not backing.is_dir()
                or not marker.is_file()
                or marker.read_text(encoding="utf-8") != expected_marker
            ):
                return 1
            root_contract = (
                record.get("RootMode") == "0711"
                and record.get("RootUID") == 0
                and record.get("RootGID") == 0
                and backing.stat().st_mode & 0o777 == 0o711
                and record.get("MarkerMode", "0444") == "0444"
                and record.get("MarkerUID", 0) == 0
                and record.get("MarkerGID", 0) == 0
                and marker.stat().st_mode & 0o777 == 0o444
            )
            legacy_contract = (
                record.get("RootMode") == "0700"
                and record.get("RootUID") == int(user_parts[0])
                and record.get("RootGID") == int(user_parts[1])
                and backing.stat().st_mode & 0o777 == 0o700
                and record.get("MarkerMode") == "0600"
                and record.get("MarkerUID") == int(user_parts[0])
                and record.get("MarkerGID") == int(user_parts[1])
                and marker.stat().st_mode & 0o777 == 0o600
            )
            if not root_contract and not (
                allow_legacy == "1" and legacy_contract
            ):
                return 1
            private_log = backing / "private-log"
            if not private_log.is_dir() or private_log.is_symlink():
                return 1
            private_log_mode = record.get(
                "PrivateLogMode", format(private_log.stat().st_mode & 0o777, "04o")
            )
            private_log_uid = record.get("PrivateLogUID", private_log.stat().st_uid)
            private_log_gid = record.get("PrivateLogGID", private_log.stat().st_gid)
            if private_log_mode == "0555" and private_log_uid == 0 and private_log_gid == 0:
                if private_log.stat().st_mode & 0o777 != 0o555 or any(
                    path.is_symlink()
                    or (not path.is_dir() and not path.is_file())
                    or path.stat().st_mode & 0o777
                    != (0o555 if path.is_dir() else 0o444)
                    for path in private_log.rglob("*")
                ):
                    return 1
            elif not (
                allow_legacy == "1"
                and private_log_mode == "0700"
                and private_log_uid == int(user_parts[0])
                and private_log_gid == int(user_parts[1])
                and private_log.stat().st_mode & 0o777 == 0o700
                and not any(
                    path.is_symlink()
                    or (not path.is_dir() and not path.is_file())
                    for path in private_log.rglob("*")
                )
            ):
                return 1
            probe = backing / ".fake-resident-write-read"
            probe.write_text("probe\n", encoding="utf-8")
            if probe.read_text(encoding="utf-8") != "probe\n":
                return 1
            probe.rename(backing / ".fake-resident-write-read-renamed")
            (backing / ".fake-resident-write-read-renamed").unlink()
            return 0
        if copy_direction:
            volume_name = ""
            input_source = ""
            for index, item in enumerate(argv):
                if item != "--mount" or index + 1 >= len(argv):
                    continue
                values = dict(
                    part.split("=", 1)
                    for part in argv[index + 1].split(",")
                    if "=" in part
                )
                if values.get("type") == "volume" and values.get("dst") == "/var/lib/agent-canon":
                    volume_name = values.get("src", "")
                elif values.get("type") == "bind" and values.get("dst") == "/agent-canon-copy-input":
                    input_source = values.get("src", "")
            if not volume_name:
                return 2
            backing = volume_path(volume_name)
            backing.mkdir(parents=True, exist_ok=True)
            runtime_root = operational_root(backing)
            kind = copy_environment.get("AGENT_CANON_COPY_KIND", "")
            relative = copy_environment.get("AGENT_CANON_COPY_RELATIVE", "")
            expected_digest = copy_environment.get("AGENT_CANON_COPY_DIGEST", "")
            install_root = Path(copy_environment.get("AGENT_CANON_COPY_INSTALL_ROOT", ""))
            projection_layout = copy_environment.get(
                "AGENT_CANON_PROJECTION_LAYOUT", "container-runtime-v1"
            )
            if projection_layout not in {"legacy-runtime-v1", "container-runtime-v1"}:
                return 1

            def valid_codex_links(root: Path) -> bool:
                allowed = install_root / ".codex"
                if not allowed.is_dir() or allowed.is_symlink():
                    return False
                for link in root.rglob("*"):
                    if not link.is_symlink():
                        continue
                    relative_link = link.relative_to(root).as_posix()
                    if not (
                        relative_link == "config.toml"
                        or relative_link.startswith(("agents/", "hooks/", "skills/"))
                    ):
                        return False
                    target = link.resolve(strict=False)
                    try:
                        target.relative_to(allowed)
                    except ValueError:
                        return False
                    if not target.exists():
                        return False
                return True
            source = Path(input_source) if copy_direction == "import" else None
            if copy_direction == "clear":
                if kind not in {"host-mounts", "rollback-mounts"}:
                    return 1
                target = (
                    backing / "host-mounts.tsv"
                    if kind == "host-mounts"
                    else runtime_root / "rollback-mounts.tsv"
                )
                target.unlink(missing_ok=True)
            elif copy_direction == "import":
                destinations = {
                    "source-sync": backing / "source-sync.json",
                    "mount-registry": backing / "mount-registry.toml",
                    "host-mounts": backing / "host-mounts.tsv",
                    "rollback-mounts": runtime_root / "rollback-mounts.tsv",
                    "private-log": backing / "private-log",
                    "codex-home": runtime_root / "codex-home",
                }
                destination = destinations.get(kind)
                if source is None or destination is None or not source.exists() or source.is_symlink():
                    return 1
                if kind in {
                    "source-sync",
                    "mount-registry",
                    "host-mounts",
                    "rollback-mounts",
                }:
                    if destination.is_symlink() or destination.is_file():
                        destination.unlink()
                    shutil.copy2(source, destination)
                    if not expected_digest or hashlib.sha256(destination.read_bytes()).hexdigest() != expected_digest:
                        return 1
                    destination.chmod(0o444)
                    print(f"volume-copy-digest\t{expected_digest}")
                else:
                    if not source.is_dir():
                        return 1
                    if kind == "codex-home" and not valid_codex_links(source):
                        return 1
                    if kind == "private-log" and any(
                        path.is_symlink()
                        or (not path.is_dir() and not path.is_file())
                        for path in source.rglob("*")
                    ):
                        return 1
                    skip_copy = False
                    # Match production: content equality alone cannot skip the
                    # private-log transaction because a legacy tree may still
                    # require atomic ownership and mode normalization.
                    if kind == "private-log" and not skip_copy:
                        temporary = destination.with_name(destination.name + ".tmp.fake")
                        backup = destination.with_name(destination.name + ".backup.fake")

                        def remove_private_log_tree(path: Path) -> None:
                            if not path.is_dir() or path.is_symlink():
                                if path.exists() or path.is_symlink():
                                    path.unlink()
                                return
                            for member in path.rglob("*"):
                                if member.is_dir() and not member.is_symlink():
                                    member.chmod(0o700)
                                elif not member.is_symlink():
                                    member.chmod(0o600)
                            path.chmod(0o700)
                            shutil.rmtree(path)

                        for path in (temporary, backup):
                            remove_private_log_tree(path)
                        shutil.copytree(source, temporary)
                        if not expected_digest or tree_digest(temporary) != expected_digest:
                            shutil.rmtree(temporary)
                            return 1
                        (temporary / ".agent-canon-private-log-v1").write_text(
                            f"agent-canon-private-log/v1\n{expected_digest}\n",
                            encoding="utf-8",
                        )
                        for path in temporary.rglob("*"):
                            if path.is_dir():
                                path.chmod(0o555)
                            elif path.is_file():
                                path.chmod(0o444)
                        temporary.chmod(0o555)
                        had_backup = destination.is_dir() and not destination.is_symlink()
                        if destination.exists() or destination.is_symlink():
                            if not had_backup:
                                shutil.rmtree(temporary)
                                return 1
                            shutil.move(str(destination), str(backup))
                        try:
                            shutil.move(str(temporary), str(destination))
                            if os.environ.get(
                                "FAKE_DOCKER_FAIL_PRIVATE_LOG_IMPORT_AFTER_PUBLISH"
                            ) == "1":
                                raise OSError("injected private-log import failure")
                            if (
                                tree_digest(destination) != expected_digest
                                or destination.stat().st_mode & 0o777 != 0o555
                            ):
                                raise OSError("private-log import readback failed")
                        except (OSError, shutil.Error):
                            if destination.is_dir() and not destination.is_symlink():
                                remove_private_log_tree(destination)
                            if had_backup:
                                shutil.move(str(backup), str(destination))
                            return 1
                        if backup.is_dir():
                            remove_private_log_tree(backup)
                    elif not skip_copy:
                        if destination.exists() or destination.is_symlink():
                            if destination.is_symlink() or not destination.is_dir():
                                return 1
                            shutil.rmtree(destination)
                        shutil.copytree(source, destination, symlinks=kind == "codex-home")
                    digest_value = (
                        codex_digest(destination)
                        if kind == "codex-home"
                        else tree_digest(destination)
                    )
                    if not expected_digest or digest_value != expected_digest:
                        return 1
                    if kind == "private-log":
                        for path in destination.rglob("*"):
                            if path.is_dir() and not path.is_symlink():
                                path.chmod(0o555)
                            elif path.is_file() and not path.is_symlink():
                                path.chmod(0o444)
                        destination.chmod(0o555)
                        volume_record = state["volumes"].get(volume_name)
                        if volume_record is not None:
                            volume_record["PrivateLogUID"] = 0
                            volume_record["PrivateLogGID"] = 0
                            volume_record["PrivateLogMode"] = "0555"
                    print(f"volume-copy-digest\t{expected_digest}")
            elif copy_direction == "export":
                def emit_tar(source_root: Path, members: list[tuple[Path, str]]) -> None:
                    with tarfile.open(fileobj=sys.stdout.buffer, mode="w") as archive:
                        for path, arcname in members:
                            archive.add(path, arcname=arcname, recursive=path.is_dir())

                if os.environ.get("FAKE_DOCKER_MALFORMED_TAR") == "1":
                    sys.stdout.buffer.write(b"not a tar archive\n")
                    print(f"volume-copy-digest\t{'0' * 64}", file=sys.stderr)
                    return 0
                if kind == "projection":
                    source_root = (
                        runtime_root
                        if projection_layout == "legacy-runtime-v1"
                        else runtime_root / "container-runtime"
                    )
                    if not source_root.is_dir() and (backing / "exchange").is_dir():
                        source_root = backing / "exchange"
                    if not source_root.is_dir() or source_root.is_symlink():
                        return 1
                    members = []
                    for name in ("mounts.toml", "mounts.tsv", "rollback-plan.tsv", "rollback-mounts.tsv"):
                        source_file = source_root / name
                        if source_file.exists():
                            if source_file.is_symlink() or not source_file.is_file():
                                return 1
                            members.append((source_file, name))
                    emit_tar(source_root, members)
                    readback_digest = projection_digest(source_root)
                elif kind == "skill":
                    source_root = runtime_root / "container-runtime" / "skill-projection"
                    if not source_root.is_dir() and (
                        backing / "exchange" / "skill-projection"
                    ).is_dir():
                        source_root = backing / "exchange" / "skill-projection"
                    if not source_root.is_dir() or source_root.is_symlink() or any(
                        path.is_symlink() for path in source_root.rglob("*")
                    ):
                        return 1
                    if any(
                        not path.is_dir() and not path.is_file()
                        for path in source_root.rglob("*")
                    ):
                        print("volume-export-invalid", file=sys.stderr)
                        return 1
                    emit_tar(source_root.parent, [(source_root, "skill-projection")])
                    readback_digest = tree_digest(source_root)
                elif kind == "eval":
                    source_root = runtime_root / "spool" / relative
                    if not source_root.is_dir() or source_root.is_symlink() or any(
                        path.is_symlink() for path in source_root.rglob("*")
                    ):
                        return 1
                    emit_tar(source_root.parent, [(source_root, relative)])
                    readback_digest = tree_digest(source_root)
                elif kind == "private-feedback":
                    source_root = runtime_root / "spool" / "private-feedback"
                    if not source_root.is_dir() or source_root.is_symlink() or any(
                        path.is_symlink() for path in source_root.rglob("*")
                    ):
                        return 1
                    emit_tar(source_root, [(child, child.name) for child in sorted(source_root.iterdir())])
                    readback_digest = tree_digest(source_root)
                elif kind == "codex-home":
                    source_root = runtime_root / "codex-home"
                    if not source_root.is_dir() or source_root.is_symlink() or not valid_codex_links(source_root):
                        return 1
                    emit_tar(source_root, [(child, child.name) for child in sorted(source_root.iterdir())])
                    readback_digest = codex_digest(source_root)
                else:
                    return 1
                if os.environ.get("FAKE_DOCKER_CORRUPT_COPY") == "1":
                    readback_digest = "0" * 64
                print(f"volume-copy-digest\t{readback_digest}", file=sys.stderr)
            save(state)
            return 0
        volume_name = ""
        volume_nocopy = False
        legacy_source = ""
        for index, item in enumerate(argv):
            if item != "--mount" or index + 1 >= len(argv):
                continue
            values = dict(
                part.split("=", 1)
                for part in argv[index + 1].split(",")
                if "=" in part
            )
            if values.get("type") == "volume" and values.get("dst") == "/var/lib/agent-canon":
                volume_name = values.get("src", "")
                volume_nocopy = "volume-nocopy" in argv[index + 1].split(",")
            if values.get("type") == "bind" and values.get("dst") == "/var/lib/agent-canon-legacy-state":
                legacy_source = values.get("src", "")
        if not volume_name:
            return 2
        backing = volume_path(volume_name)
        backing.mkdir(parents=True, exist_ok=True)
        runtime_backing = backing / "runtime"
        legacy = Path(legacy_source) if legacy_source else None
        marker = backing / ".agent-canon-controller-volume-v1"
        if not volume_nocopy and not marker.exists():
            runtime_backing.mkdir(parents=True, exist_ok=True)
        digest = next(
            (
                item.split("=", 1)[1]
                for item in argv
                if item.startswith("AGENT_CANON_VOLUME_DIGEST=")
            ),
            "",
        )
        created_here = next(
            (
                item.split("=", 1)[1]
                for item in argv
                if item.startswith("AGENT_CANON_VOLUME_CREATED_HERE=")
            ),
            "0",
        ) == "1"
        if os.environ.get("FAKE_DOCKER_FAIL_STATE_VOLUME_INIT_ONCE") == "1" and not state.get(
            "_state_volume_init_failed_once"
        ):
            state["_state_volume_init_failed_once"] = True
            save(state)
            return 1

        def same_tree(source: Path, destination: Path) -> bool:
            source_files = sorted(
                item.relative_to(source).as_posix()
                for item in source.rglob("*")
                if not item.is_dir() or item.is_symlink()
            )
            destination_files = sorted(
                item.relative_to(destination).as_posix()
                for item in destination.rglob("*")
                if not item.is_dir() or item.is_symlink()
            )
            if source_files != destination_files:
                return False
            for relative in source_files:
                source_path = source / relative
                destination_path = destination / relative
                if source_path.is_symlink() or destination_path.is_symlink():
                    if not (
                        source_path.is_symlink()
                        and destination_path.is_symlink()
                        and source_path.readlink() == destination_path.readlink()
                    ):
                        return False
                elif not (
                    source_path.is_file()
                    and destination_path.is_file()
                    and source_path.read_bytes() == destination_path.read_bytes()
                ):
                    return False
            return True

        def migrate_file(source: Path, destination: Path) -> bool:
            if destination.exists():
                return destination.is_file() and not destination.is_symlink() and source.read_bytes() == destination.read_bytes()
            shutil.copy2(source, destination)
            return True

        def migrate_tree(source: Path, destination: Path) -> bool:
            if destination.exists():
                return destination.is_dir() and not destination.is_symlink() and same_tree(source, destination)
            shutil.copytree(source, destination, symlinks=True)
            return True

        marked = marker.exists()
        operation_root = runtime_backing
        if marked:
            caller_uid = int(next(
                item.split("=", 1)[1]
                for item in argv
                if item.startswith("AGENT_CANON_VOLUME_UID=")
            ))
            caller_gid = int(next(
                item.split("=", 1)[1]
                for item in argv
                if item.startswith("AGENT_CANON_VOLUME_GID=")
            ))
            volume_record = state["volumes"][volume_name]
            root_stat = backing.stat()
            marker_stat = marker.stat()
            # The fake daemon records daemon-namespace ownership separately
            # from the host filesystem.  This keeps the contract deterministic
            # when the test runner cannot chown a fixture to uid 1000.
            root_uid = volume_record.get("RootUID", root_stat.st_uid)
            root_gid = volume_record.get("RootGID", root_stat.st_gid)
            root_mode = volume_record.get(
                "RootMode", format(root_stat.st_mode & 0o777, "04o")
            )
            marker_uid = volume_record.get("MarkerUID", marker_stat.st_uid)
            marker_gid = volume_record.get("MarkerGID", marker_stat.st_gid)
            marker_mode = volume_record.get(
                "MarkerMode", format(marker_stat.st_mode & 0o777, "04o")
            )
            legacy_root = (
                root_mode == "0700"
                and root_uid == caller_uid
                and root_gid == caller_gid
                and marker_mode == "0600"
                and marker_uid == caller_uid
                and marker_gid == caller_gid
            )
            normalized_root = (
                root_mode == "0711"
                and root_uid == 0
                and root_gid == 0
                and marker_mode == "0444"
                and marker_uid == 0
                and marker_gid == 0
            )
            if not (legacy_root or normalized_root):
                return 1
            legacy_names = ("exchange", "spool", "archive", "cache", "codex-home")
            legacy_paths = {
                name: backing / name
                for name in legacy_names
                if (backing / name).exists() or (backing / name).is_symlink()
            }
            private_log = backing / "private-log"
            if private_log.exists() and not private_log.is_symlink():
                private_log_stat = private_log.stat()
                private_log_uid = volume_record.get(
                    "PrivateLogUID", private_log_stat.st_uid
                )
                private_log_gid = volume_record.get(
                    "PrivateLogGID", private_log_stat.st_gid
                )
                private_log_mode = volume_record.get(
                    "PrivateLogMode",
                    format(private_log_stat.st_mode & 0o777, "04o"),
                )
                legacy_private_log = (
                    private_log_mode == "0700"
                    and private_log_uid == caller_uid
                    and private_log_gid == caller_gid
                )
                normalized_private_log = (
                    private_log_mode == "0555"
                    and private_log_uid == 0
                    and private_log_gid == 0
                )
                if not (legacy_private_log or normalized_private_log):
                    return 1
                if legacy_private_log:
                    if any(
                        path.is_symlink()
                        or (not path.is_dir() and not path.is_file())
                        for path in private_log.rglob("*")
                    ):
                        return 1
                else:
                    # UID/GID metadata represents the daemon namespace for the
                    # whole normalized tree.  Host fixture ownership is not a
                    # portable proxy when the test runner is non-root.
                    if any(
                        path.is_symlink()
                        or (not path.is_dir() and not path.is_file())
                        or path.stat().st_mode & 0o777
                        != (0o555 if path.is_dir() else 0o444)
                        for path in private_log.rglob("*")
                    ):
                        return 1
            if legacy_paths:
                transaction = backing / ".agent-canon-layout-migration-v1"
                if transaction.exists() or transaction.is_symlink():
                    return 1
                staged = transaction / "staged" / "runtime"
                old = transaction / "old"
                moved_old: list[str] = []
                moved_new: list[str] = []

                def remove_path(path: Path) -> None:
                    if path.is_dir() and not path.is_symlink():
                        shutil.rmtree(path)
                    elif path.exists() or path.is_symlink():
                        path.unlink()

                def valid_legacy_tree(source: Path, allow_links: bool) -> bool:
                    if not source.is_dir() or source.is_symlink():
                        return False
                    for path in source.rglob("*"):
                        if path.is_symlink():
                            if not allow_links:
                                return False
                            relative = path.relative_to(source).as_posix()
                            if not (
                                relative == "config.toml"
                                or relative.startswith("agents/")
                                or relative.startswith("hooks/")
                                or relative.startswith("skills/")
                            ) or ".." in relative or "//" in relative:
                                return False
                            target = os.readlink(path)
                            if not target or ".." in target:
                                return False
                        elif not path.is_dir() and not path.is_file():
                            return False
                    return True

                try:
                    staged.mkdir(parents=True)
                    old.mkdir(parents=True)
                    destinations = {
                        name: ("container-runtime" if name == "exchange" else name)
                        for name in legacy_names
                    }
                    for name, source in legacy_paths.items():
                        if not valid_legacy_tree(source, name == "codex-home"):
                            raise OSError("invalid legacy runtime tree")
                        destination = runtime_backing / destinations[name]
                        if destination.exists() or destination.is_symlink():
                            raise OSError("legacy runtime destination already exists")
                        shutil.copytree(
                            source,
                            staged / destinations[name],
                            symlinks=True,
                        )
                    for name in legacy_paths:
                        shutil.move(str(backing / name), str(old / name))
                        moved_old.append(name)
                        if os.environ.get("FAKE_DOCKER_FAIL_LAYOUT_MIGRATION_AFTER") == name:
                            raise OSError("injected layout migration failure")
                    runtime_backing.mkdir(parents=True, exist_ok=True)
                    for name in legacy_paths:
                        destination = destinations[name]
                        shutil.move(
                            str(staged / destination),
                            str(runtime_backing / destination),
                        )
                        moved_new.append(destination)
                    if (runtime_backing / "spool").is_dir():
                        (runtime_backing / "spool" / "private-feedback").mkdir()
                    for name in ("receipts", "generations", "tasks"):
                        (runtime_backing / name).mkdir(parents=True, exist_ok=True)
                    shutil.rmtree(transaction)
                except (OSError, shutil.Error):
                    for destination in moved_new:
                        remove_path(runtime_backing / destination)
                    for name in reversed(moved_old):
                        shutil.move(str(old / name), str(backing / name))
                    remove_path(transaction)
                    return 1
        if marker.is_symlink() or (marked and marker.read_text(encoding="utf-8") != f"agent-canon-controller-volume/v1\n{digest}\n"):
            return 1
        if not marked and any(backing.iterdir()):
            return 1
        if not marked and legacy is not None and legacy.is_dir():
            runtime_backing.mkdir(parents=True, exist_ok=True)
            for name in ("state.json", "owner.json"):
                source = legacy / name
                if source.exists() and (not source.is_file() or source.is_symlink() or not migrate_file(source, runtime_backing / name)):
                    return 1
            for name in ("receipts", "generations", "tasks"):
                source = legacy / name
                destination = runtime_backing / name
                if source.exists() and (not source.is_dir() or source.is_symlink() or not migrate_tree(source, destination)):
                    return 1
            for name in ("spool", "archive", "cache", "codex-home"):
                source = legacy / name
                destination = runtime_backing / name
                if source.exists() and (not source.is_dir() or source.is_symlink() or not migrate_tree(source, destination)):
                    return 1
        if not marked and legacy is not None and legacy.is_dir():
            for name in ("state.json", "owner.json"):
                source = legacy / name
                if source.exists() and (not (runtime_backing / name).is_file() or source.read_bytes() != (runtime_backing / name).read_bytes()):
                    return 1
            for name in ("receipts", "generations", "tasks"):
                source = legacy / name
                if source.exists() and (not (runtime_backing / name).is_dir() or not same_tree(source, runtime_backing / name)):
                    return 1
            for name in ("spool", "archive", "cache", "codex-home"):
                source = legacy / name
                if source.exists() and (not (runtime_backing / name).is_dir() or not same_tree(source, runtime_backing / name)):
                    return 1
        required_dirs = [
            runtime_backing,
            runtime_backing / "receipts",
            runtime_backing / "generations",
            runtime_backing / "tasks",
            operation_root / "container-runtime",
            operation_root / "spool",
            operation_root / "spool" / "private-feedback",
            operation_root / "archive",
            operation_root / "cache",
            operation_root / "codex-home",
            backing / "private-log",
        ]
        for directory in required_dirs:
            if marked and (not directory.is_dir() or directory.is_symlink()):
                return 1
            directory.mkdir(parents=True, exist_ok=True)
        caller_uid = int(next(item.split("=", 1)[1] for item in argv if item.startswith("AGENT_CANON_VOLUME_UID=")))
        caller_gid = int(next(item.split("=", 1)[1] for item in argv if item.startswith("AGENT_CANON_VOLUME_GID=")))
        for directory in required_dirs:
            if directory != backing / "private-log":
                directory.chmod(0o700)
        private_log_root = backing / "private-log"
        existing_private_log = marked and private_log_root.is_dir()
        private_log_mode = state["volumes"][volume_name].get(
            "PrivateLogMode",
            format(private_log_root.stat().st_mode & 0o777, "04o"),
        )
        private_log_uid = state["volumes"][volume_name].get(
            "PrivateLogUID", private_log_root.stat().st_uid
        )
        private_log_gid = state["volumes"][volume_name].get(
            "PrivateLogGID", private_log_root.stat().st_gid
        )
        if existing_private_log and private_log_mode == "0555" and private_log_uid == 0 and private_log_gid == 0:
            # Preserve an already-normalized private-log until the next typed
            # import; the production helper does not weaken this boundary.
            private_log_root.chmod(0o555)
            for path in private_log_root.rglob("*"):
                if path.is_dir() and not path.is_symlink():
                    path.chmod(0o555)
                elif path.is_file() and not path.is_symlink():
                    path.chmod(0o444)
            state["volumes"][volume_name]["PrivateLogUID"] = 0
            state["volumes"][volume_name]["PrivateLogGID"] = 0
            state["volumes"][volume_name]["PrivateLogMode"] = "0555"
        else:
            # The initializer keeps a legacy or fresh private-log caller-owned
            # until typed host import publishes its root-owned read-only copy.
            private_log_root.chmod(0o700)
            state["volumes"][volume_name]["PrivateLogUID"] = caller_uid
            state["volumes"][volume_name]["PrivateLogGID"] = caller_gid
            state["volumes"][volume_name]["PrivateLogMode"] = "0700"
        backing.chmod(0o711)
        state["volumes"][volume_name]["UID"] = caller_uid
        state["volumes"][volume_name]["GID"] = caller_gid
        state["volumes"][volume_name]["RootUID"] = 0
        state["volumes"][volume_name]["RootGID"] = 0
        state["volumes"][volume_name]["RootMode"] = "0711"
        state["volumes"][volume_name]["MarkerUID"] = 0
        state["volumes"][volume_name]["MarkerGID"] = 0
        state["volumes"][volume_name]["MarkerMode"] = "0444"
        state["volumes"][volume_name]["Mode"] = "0700"
        if not marked:
            marker.write_text(f"agent-canon-controller-volume/v1\n{digest}\n", encoding="utf-8")
        if marker.read_text(encoding="utf-8") != f"agent-canon-controller-volume/v1\n{digest}\n":
            return 1
        marker.chmod(0o444)
        print(f"marker\t{digest}\ncontent\tok")
        save(state)
        return 0
    if argv[:1] == ["start"]:
        found = find(state, argv[1])
        if not found:
            return 1
        if os.environ.get("FAKE_DOCKER_FAIL_START") == "1":
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
            # Docker removes a volume in the daemon namespace, even when the
            # resident deliberately made its control-plane tree root-owned
            # and read-only.  Grant the fake daemon's cleanup operation the
            # equivalent authority before removing that private backing tree.
            for path in sorted(backing.rglob("*"), key=lambda item: len(item.parts), reverse=True):
                if path.is_symlink():
                    continue
                try:
                    path.chmod(
                        (path.stat().st_mode & 0o777)
                        | (0o700 if path.is_dir() else 0o600)
                    )
                except OSError:
                    pass
            backing.chmod(0o700)
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
                if mount["Destination"] == "/var/lib/agent-canon"
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
        source = Path(runtime_mount["Source"]) / "runtime" / relative
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
                if mount["Destination"] == "/var/lib/agent-canon"
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
                or volume.get("RootMode") != "0711"
                or volume.get("RootUID") != 0
                or volume.get("RootGID") != 0
            ):
                return 1
            volume_root = Path(runtime_mount["Source"])
            for control_name in ("source-sync.json", "mount-registry.toml", "host-mounts.tsv"):
                control_path = volume_root / control_name
                if control_path.exists() and control_path.stat().st_mode & 0o777 != 0o444:
                    return 1
            private_log = volume_root / "private-log"
            if private_log.exists() and (
                private_log.stat().st_mode & 0o777 != 0o555
                or any(
                    path.stat().st_mode & 0o777
                    != (0o555 if path.is_dir() else 0o444)
                    for path in private_log.rglob("*")
                    if not path.is_symlink()
                )
            ):
                return 1
            probe = volume_root / "runtime" / ".fake-resident-write-read"
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
            image_ref = found[1].get("Config", {}).get("Image", "")
            image_found = find(state, image_ref)
            if image_found is None or image_found[0] != "image":
                return 1
            projection_layout = image_found[1].get("Config", {}).get("Labels", {}).get(
                "io.agent-canon.projection-layout", ""
            )
            if projection_layout not in {"", "container-runtime-v1"}:
                return 1
            projection_legacy = projection_layout == ""
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
                        if mount["Destination"] == "/var/lib/agent-canon"
                    ),
                    None,
                )
                exchange_mount = next(
                    (
                        mount
                        for mount in found[1]["Mounts"]
                        if mount["Destination"] == "/var/lib/agent-canon"
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
                runtime_root = Path(runtime_mount["Source"]) / "runtime"
                exchange_root = (
                    runtime_root
                    if projection_legacy
                    else operational_root(Path(exchange_mount["Source"])) / "container-runtime"
                )
                exchange_root.mkdir(parents=True, exist_ok=True)
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
                        if mount["Destination"] == "/var/lib/agent-canon"
                    ),
                    None,
                )
                current_id = exec_environment.get("AGENT_CANON_CURRENT_IMAGE_ID", "")
                current_ref = exec_environment.get("AGENT_CANON_CURRENT_IMAGE_REF", "")
                if runtime_mount is None or not current_id or not current_ref:
                    return 1
                volume_root = Path(runtime_mount["Source"])
                runtime_root = volume_root / "runtime"
                host_install = Path(exec_environment.get("AGENT_CANON_HOST_INSTALL_ROOT", ""))
                private_log = host_install.parent / "agent-canon-log"
                source_sync_source = host_install / ".runtime" / "source-sync.json"
                registry_source = host_install / ".runtime" / "container-state" / "mounts.toml"
                operational = operational_root(volume_root)
                plan_root = runtime_root if projection_legacy else operational / "container-runtime"
                plan = plan_root / "rollback-plan.tsv"
                plan_lines = [
                    "schema\tagent-canon.rollback-plan.v1",
                    f"image-id\t{current_id}",
                    f"image-ref\t{current_ref}",
                    f"mount\tmount\t{runtime_root}\t/var/lib/agent-canon/runtime\tfalse",
                    f"mount\tmount\t{source_sync_source}\t/var/lib/agent-canon/source-sync.json\ttrue",
                    f"mount\tmount\t{private_log}\t/var/lib/agent-canon/private-log\ttrue",
                    f"mount\tmount\t{registry_source}\t/var/lib/agent-canon/mount-registry.toml\ttrue",
                ]
                mounts_path = plan_root / "mounts.tsv"
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
                volume_root = Path(runtime_mount["Source"])
                runtime_root = volume_root / "runtime"
                for name in ("generations", "tasks"):
                    directory = runtime_root / name
                    if directory.is_dir():
                        for child in directory.iterdir():
                            if child.is_dir() and not child.is_symlink():
                                shutil.rmtree(child)
                            else:
                                child.unlink()
                state_path = runtime_root / "state.json"
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
                exchange_root = (
                    runtime_root
                    if projection_legacy
                    else operational_root(volume_root) / "container-runtime"
                )
                exchange_root.mkdir(parents=True, exist_ok=True)
                (exchange_root / "mounts.tsv").write_text("", encoding="utf-8")
                (exchange_root / "mounts.toml").write_text(
                    'schema = "agent-canon.mount-registry.v2"\n',
                    encoding="utf-8",
                )
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
                if mount["Destination"] == "/var/lib/agent-canon"
            )
            relative = Path(runtime_arg).relative_to("/var/lib/agent-canon/runtime/container-runtime")
            exchange = operational_root(Path(target["Source"])) / Path("container-runtime") / relative
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
                if mount["Destination"] == "/var/lib/agent-canon"
            )
            runtime_root = Path(runtime_mount["Source"]) / "exchange"
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
