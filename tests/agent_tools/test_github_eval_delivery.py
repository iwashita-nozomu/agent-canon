"""Main Eval transport contracts, with the remote API replaced at its boundary."""

# @dependency-start
# contract test
# responsibility Verifies trusted main Eval artifact input, resource bounds, replay and existing publisher handoff.
# upstream implementation ../../tools/runtime/archive/github_eval_delivery.py host transport
# upstream implementation ../../tools/runtime/archive/runtime_log_archive_git.py canonical archive publisher
# @dependency-end

from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from tools.runtime.archive import github_eval_delivery as delivery


@pytest.fixture
def service(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(
        delivery, "source_remote", lambda root: "git@github.com:test/canon.git"
    )
    artifacts = []
    runs = {}
    archives = {}
    downloaded = []
    pages = {}

    def add(number=11, attempt=1, head="a" * 40, **overrides):
        run_id = f"main-{head}-{number}-{attempt}"
        collection = {
            "schema": "agent_canon.eval_collection.v1",
            "run_id": run_id,
            "status": "collected",
            "source_tree_unchanged": True,
            "source_head_before": head,
            "source_head_after": head,
            "agent_canon_commit": head,
            "source_git_status_before": "",
            "source_git_status_after": "",
            "source_tree_digest_before": "b" * 64,
            "source_tree_digest_after": "b" * 64,
            "family_status": {"codex-agent-role": "pass", "workflow-selection": "pass"},
            "producer_matrix": [
                {"name": "codex-agent-role", "status": "pass", "exit": 0},
                {"name": "workflow-selection", "status": "pass", "exit": 0},
            ],
            "exported_files": {"eval_results": 2, "producer_logs": 4},
            **overrides,
        }
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as bundle:
            bundle.writestr("collection.json", json.dumps(collection))
            bundle.writestr("eval-results/codex-agent-role/role.md", "role=pass\n")
            bundle.writestr(
                "eval-results/workflow-selection/workflow.md", "workflow=pass\n"
            )
            for name in ("role", "workflow"):
                bundle.writestr(f"producer-logs/{name}.stdout.txt", "pass\n")
                bundle.writestr(f"producer-logs/{name}.stderr.txt", "")
        data = output.getvalue()
        artifact_id = number * 10 + attempt
        artifact = {
            "id": artifact_id,
            "name": f"agent-canon-main-eval-{number}-{attempt}",
            "expired": False,
            "size_in_bytes": len(data),
            "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
            "workflow_run": {
                "id": number,
                "head_sha": head,
                "head_branch": "main",
                "repository_id": 1,
                "head_repository_id": 1,
            },
        }
        artifacts.append(artifact)
        runs[(number, attempt)] = {
            "id": number,
            "run_attempt": attempt,
            "event": "push",
            "status": "completed",
            "head_branch": "main",
            "head_sha": head,
            "path": delivery.WORKFLOW_PATH,
            "workflow_id": 2,
            "repository": {"id": 1},
            "head_repository": {"id": 1},
        }
        archives[artifact_id] = data
        return run_id, artifact

    def api(endpoint, root):
        assert root == source
        if endpoint == "repos/test/canon":
            return {"id": 1}
        if endpoint.endswith("actions/workflows/agent-canon-static-gates.yml"):
            return {"id": 2, "path": delivery.WORKFLOW_PATH}
        if "actions/artifacts?" in endpoint:
            page = int(endpoint.rsplit("=", 1)[1])
            return {"artifacts": pages.get(page, artifacts if page == 1 else [])}
        parts = endpoint.split("/")
        return runs[(int(parts[-3]), int(parts[-1]))]

    def download(endpoint, destination, root, max_bytes):
        assert root == source
        number = int(endpoint.split("/")[-2])
        downloaded.append(number)
        assert len(archives[number]) <= max_bytes
        destination.write_bytes(archives[number])

    limits = delivery.EvalArtifactLimits(2_000_000, 1_000_000, 5_000_000, 16)

    def run(publish, published=None, selected_limits=None):
        return delivery.deliver_main_evals(
            source_root=source,
            runtime_root=tmp_path / "runtime",
            published_run_ids=published if published is not None else set(),
            limits=selected_limits if selected_limits is not None else limits,
            publish=publish,
            api=api,
            download=download,
        )

    return {
        "add": add,
        "run": run,
        "runs": runs,
        "archives": archives,
        "artifacts": artifacts,
        "downloaded": downloaded,
        "pages": pages,
        "runtime": tmp_path / "runtime",
        "limits": limits,
    }


def test_each_main_commit_and_attempt_publishes_its_original_bytes(service):
    first, _ = service["add"]()
    second, _ = service["add"](number=11, attempt=2)
    third, _ = service["add"](number=12, head="c" * 40)
    published = set()
    observed = []

    def publish(spool, run_id):
        collection = json.loads((spool / "collection.json").read_text())
        assert collection["run_id"] == run_id
        assert collection["source_head_before"] in {"a" * 40, "c" * 40}
        assert (
            spool / "eval-results/workflow-selection/workflow.md"
        ).read_bytes() == b"workflow=pass\n"
        assert len(list((spool / "producer-logs").glob("*.txt"))) == 4
        observed.append(run_id)

    assert service["run"](publish, published) == 3
    assert observed == [first, second, third]
    assert published == {first, second, third}
    assert service["run"](publish, published) == 0
    assert len(service["downloaded"]) == 3


@pytest.mark.parametrize(
    "override",
    [
        {"status": "failed"},
        {"source_tree_unchanged": False},
        {"source_head_after": "d" * 40},
        {"agent_canon_commit": "d" * 40},
        {"source_git_status_before": "?? unknown.py\n"},
        {"source_git_status_after": " M file.py\n"},
        {"family_status": {"codex-agent-role": "pass", "workflow-selection": "fail"}},
        {"producer_matrix": []},
        {"exported_files": {"eval_results": 3, "producer_logs": 4}},
    ],
)
def test_failed_dirty_or_revision_mismatched_evidence_is_not_promoted(
    service, override
):
    service["add"](**override)
    published = []
    with pytest.raises(delivery.GitHubEvalDeliveryError, match="delivery_pending"):
        service["run"](lambda spool, run_id: published.append(run_id))
    assert not published
    assert list(service["runtime"].rglob("artifact.zip"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("event", "pull_request"),
        ("head_branch", "topic"),
        ("path", ".github/workflows/other.yml"),
        ("workflow_id", 3),
        ("head_repository", {"id": 3}),
        ("repository", {"id": 3}),
        ("status", "in_progress"),
    ],
)
def test_only_the_completed_same_repo_main_push_workflow_is_selected(
    service, field, value
):
    service["add"]()
    service["runs"][(11, 1)][field] = value
    assert service["run"](lambda *_: pytest.fail("unselected run was published")) == 0
    assert not service["downloaded"]


@pytest.mark.parametrize(
    "field,value", [("head_sha", "c" * 40), ("id", 12), ("run_attempt", 2)]
)
def test_run_identity_mismatch_is_not_acknowledged(service, field, value):
    service["add"]()
    service["runs"][(11, 1)][field] = value
    with pytest.raises(delivery.GitHubEvalDeliveryError, match="run_mismatch"):
        service["run"](lambda *_: pytest.fail("mismatched run was published"))


def test_failed_publication_retries_retained_bytes_after_artifact_expiry(service):
    run_id, artifact = service["add"]()
    acknowledged = set()

    def unavailable(*_):
        raise delivery.GitHubEvalDeliveryError("fixture_push_unavailable")

    with pytest.raises(delivery.GitHubEvalDeliveryError):
        service["run"](unavailable, acknowledged)
    assert not acknowledged
    retained = {
        path.relative_to(service["runtime"]): path.read_bytes()
        for path in service["runtime"].rglob("*")
        if path.is_file()
    }
    artifact["expired"] = True
    with pytest.raises(delivery.GitHubEvalDeliveryError):
        service["run"](unavailable, acknowledged)
    assert retained == {
        path.relative_to(service["runtime"]): path.read_bytes()
        for path in service["runtime"].rglob("*")
        if path.is_file()
    }
    observed = []
    assert service["run"](lambda spool, item: observed.append(item), acknowledged) == 1
    assert observed == [run_id] and acknowledged == {run_id}
    assert len(service["downloaded"]) == 1


def test_remote_ack_retries_cleanup_even_when_artifact_is_no_longer_listed(
    service, monkeypatch
):
    run_id, _ = service["add"]()
    acknowledged = set()
    observed = []
    original = delivery.shutil.rmtree
    cleanups = []

    def flaky(path):
        cleanups.append(path)
        if len(cleanups) == 1:
            raise OSError("fixture cleanup unavailable")
        original(path)

    monkeypatch.setattr(delivery.shutil, "rmtree", flaky)
    assert service["run"](lambda spool, item: observed.append(item), acknowledged) == 1
    assert acknowledged == {run_id} and cleanups[0].exists()
    service["artifacts"].clear()
    assert (
        service["run"](
            lambda *_: pytest.fail("acknowledged data republished"), acknowledged
        )
        == 0
    )
    assert len(cleanups) == 2 and not cleanups[0].exists()
    assert observed == [run_id] and len(service["downloaded"]) == 1


def test_declared_download_size_is_checked_before_acquisition(service):
    _, artifact = service["add"]()
    artifact["size_in_bytes"] = service["limits"].artifact_bytes + 1
    with pytest.raises(delivery.GitHubEvalDeliveryError, match="archive_quota"):
        service["run"](lambda *_: pytest.fail("oversized data was published"))
    assert not service["downloaded"]


@pytest.mark.parametrize("kind", ["members", "entry", "runtime"])
def test_artifact_limits_prevent_unbounded_staging(service, kind):
    service["add"](**({"extra": "x" * 4096} if kind == "entry" else {}))
    current = service["limits"]
    limits = replace(
        current,
        entry_bytes=1024 if kind == "entry" else current.entry_bytes,
        runtime_bytes=service["artifacts"][-1]["size_in_bytes"] + 1
        if kind == "runtime"
        else current.runtime_bytes,
        members=6 if kind == "members" else current.members,
    )
    with pytest.raises(
        delivery.GitHubEvalDeliveryError,
        match=kind + "_quota" if kind != "members" else "member_quota",
    ):
        service["run"](
            lambda *_: pytest.fail("over-budget data was published"),
            selected_limits=limits,
        )
    assert not list(service["runtime"].rglob("collection.json"))
    if kind == "runtime":
        assert len(service["downloaded"]) == 1


@pytest.mark.parametrize("phase", ["download", "expand"])
def test_runtime_budget_includes_existing_data_outside_transport_stage(service, phase):
    _, artifact = service["add"]()
    unrelated = service["runtime"] / "tasks" / "other-owner.bin"
    unrelated.parent.mkdir(parents=True)
    original = b"x" * 100_000
    unrelated.write_bytes(original)
    limit = len(original) + artifact["size_in_bytes"] + (1 if phase == "expand" else -1)
    selected = replace(service["limits"], runtime_bytes=limit)
    with pytest.raises(delivery.GitHubEvalDeliveryError, match="runtime_quota"):
        service["run"](
            lambda *_: pytest.fail("over-budget bundle published"),
            selected_limits=selected,
        )
    assert unrelated.read_bytes() == original
    assert len(service["downloaded"]) == (1 if phase == "expand" else 0)


def test_expanded_size_is_checked_from_metadata_before_writing(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    artifact = runtime / "artifact.zip"
    artifact.write_bytes(b"fixture")
    infos = [zipfile.ZipInfo("eval-results/a.md"), zipfile.ZipInfo("eval-results/b.md")]
    for info in infos:
        info.file_size = 80

    class Bundle:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def infolist(self):
            return infos

    monkeypatch.setattr(delivery.zipfile, "ZipFile", lambda _: Bundle())
    boundary = delivery.runtime_spool_boundary(source, runtime)
    destination = runtime / "spool"
    limits = delivery.EvalArtifactLimits(100, 90, 10_000, 4)
    with pytest.raises(delivery.GitHubEvalDeliveryError, match="expansion_quota"):
        delivery._extract(artifact, destination, limits, boundary)
    assert not destination.exists()


def test_metadata_reader_bounds_parser_allocation(tmp_path):
    path = tmp_path / "metadata"
    path.write_bytes(b"x" * 64)
    with io.FileIO(path, "r") as raw, delivery._MetadataReader(raw, 8) as reader:
        assert reader.read(6) == b"x" * 6
        with pytest.raises(delivery.GitHubEvalDeliveryError, match="metadata_quota"):
            reader.read(3)
        reader.payload_reads(8)
        reader.seek(60)
        assert reader.read() == b"x" * 4
    assert raw.closed


def test_download_stream_stops_before_writing_past_its_budget(tmp_path, monkeypatch):
    class Process:
        stdout = io.BytesIO(b"x" * 9)
        status = None

        def poll(self):
            return self.status

        def kill(self):
            self.status = -9

        def wait(self):
            if self.status is None:
                self.status = 0
            return self.status

    process = Process()
    monkeypatch.setattr(delivery.subprocess, "Popen", lambda *args, **kwargs: process)
    destination = tmp_path / "download.part"
    with pytest.raises(delivery.GitHubEvalDeliveryError, match="download_quota"):
        delivery._download("fixture", destination, tmp_path, 8)
    assert destination.stat().st_size <= 8
    assert process.status == -9 and process.stdout.closed


def test_one_failure_does_not_suppress_another_main_commit(service):
    _, broken = service["add"]()
    valid, _ = service["add"](number=12, head="c" * 40)
    broken["digest"] = "sha256:" + "0" * 64
    observed = []
    with pytest.raises(delivery.GitHubEvalDeliveryError, match="digest_mismatch"):
        service["run"](lambda spool, run_id: observed.append(run_id))
    assert observed == [valid]


def test_artifact_pages_are_drained_without_a_latest_commit_shortcut(service):
    first, artifact = service["add"]()
    second, later = service["add"](number=12, head="c" * 40)
    service["pages"][1] = [artifact] + [{"name": "unrelated"}] * 99
    service["pages"][2] = [later]
    observed = []
    assert service["run"](lambda spool, run_id: observed.append(run_id)) == 2
    assert observed == [first, second]


@pytest.mark.parametrize(
    "name", ["../outside", "/absolute", "eval-results/../../outside", "other/file"]
)
def test_untrusted_member_names_are_rejected_before_writing(name):
    with pytest.raises(delivery.GitHubEvalDeliveryError, match="path_invalid"):
        delivery._member_path(name)


@pytest.mark.parametrize("publish_fails", [False, True])
def test_existing_archive_owner_supplies_ack_and_publishes_the_bundle(
    tmp_path,
    monkeypatch,
    publish_fails,
):
    from tools.runtime.archive import runtime_log_archive_git as archive

    manifest = tmp_path / "source/bootstrap/host/manifest.toml"
    manifest.parent.mkdir(parents=True)
    shutil.copyfile(
        Path(__file__).resolve().parents[2] / "bootstrap/host/manifest.toml", manifest
    )

    context = archive.ArchiveContext(
        source_root=tmp_path / "source",
        canon_root=tmp_path / "source",
        archive_root=tmp_path / "archive",
        repo_key="key",
        env_key="env",
        branch_key="key",
        branch="logs/key",
        remote="fixture",
        runtime_root=tmp_path / "runtime",
    )
    receipt = archive.ArchivePublicationReceipt(
        status="committed",
        commit_created=False,
        pushed=True,
        archive_commit_oid="a" * 40,
        archive_tree_oid="b" * 40,
        dedup_index_sha256="",
        cursor_sha256="",
    )
    calls = []
    spool = tmp_path / "incoming"

    def git(root, args):
        assert root == context.archive_root and receipt.archive_commit_oid in args
        return subprocess.CompletedProcess(
            [], 0, "eval-results/collections/main-old.json\n", ""
        )

    def verify(active, acknowledged, paths):
        assert active is context and acknowledged is receipt
        assert paths == (
            context.archive_root / "eval-results/collections/main-old.json",
        )
        calls.append("ack")

    def publish(active, args):
        assert (
            active is context and args.spool_root == spool and args.run_id == "main-new"
        )
        calls.append("publish")
        assert args.no_pull is True
        if publish_fails:
            raise archive.ArchiveGitError("fixture push failed")
        return 0

    def drain(**kwargs):
        assert kwargs["published_run_ids"] == {"main-old"}
        assert calls == ["ack"]
        kwargs["publish"](spool, "main-new")
        return 1

    monkeypatch.setattr(archive, "git", git)
    monkeypatch.setattr(archive, "_verify_remote_archive_readback", verify)
    monkeypatch.setattr(archive, "command_archive_eval", publish)
    monkeypatch.setattr(delivery, "deliver_main_evals", drain)
    if publish_fails:
        with pytest.raises(archive.ArchiveGitError, match="publication_failed"):
            archive._deliver_main_evals(context, receipt, no_pull=True)
    else:
        archive._deliver_main_evals(context, receipt, no_pull=True)
    assert calls == ["ack", "publish"]


def test_main_delivery_does_not_override_an_explicit_no_push(tmp_path, monkeypatch):
    from tools.runtime.archive import runtime_log_archive_git as archive

    root = Path(__file__).resolve().parents[2]
    key = archive.repo_log_key(root)
    context = archive.ArchiveContext(
        source_root=root,
        canon_root=root,
        archive_root=tmp_path / "archive",
        repo_key=key,
        env_key="fixture",
        branch_key=key,
        branch="logs/" + key,
        remote=str(tmp_path / "remote.git"),
        runtime_root=tmp_path / "runtime",
    )
    args = archive.build_parser().parse_args(
        ["sync", "--include-main-evals", "--no-push"]
    )
    monkeypatch.setattr(
        archive,
        "prepare_archive_transaction",
        lambda *a, **kw: pytest.fail(
            "publication started before conflicting modes were rejected"
        ),
    )
    with pytest.raises(archive.ArchiveGitError, match="main_evals_require_publication"):
        archive.command_sync(context, args)
