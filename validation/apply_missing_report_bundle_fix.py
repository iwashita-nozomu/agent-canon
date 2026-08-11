#!/usr/bin/env python3
"""Apply the focused missing report-bundle parent attestation fix."""

from pathlib import Path
from textwrap import dedent, indent


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    """Replace one exact source block or stop without partial changes."""
    source = path.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    path.write_text(source.replace(old, new), encoding="utf-8")


def main() -> None:
    """Authenticate an existing Git ancestor before resolving a future bundle."""
    workspace_scope = Path("tools/agent_tools/workspace_scope.py")
    replace_once(
        workspace_scope,
        '''        attestation = attest_parent_root(
            ParentRootAttestationRequest(
                cwd=report_root, explicit_root=None, purpose="report-artifact"
            )
        )
''',
        '''        configured_parent = os.environ.get("AGENT_CANON_PARENT_ROOT", "").strip()
        if configured_parent:
            attestation_root = Path(configured_parent).resolve()
            attestation = attest_parent_root(
                ParentRootAttestationRequest(
                    cwd=attestation_root,
                    explicit_root=attestation_root,
                    purpose="report-artifact",
                )
            )
        else:
            attestation_cwd = report_root
            while not attestation_cwd.exists():
                parent = attestation_cwd.parent
                if parent == attestation_cwd:
                    break
                attestation_cwd = parent
            attestation = attest_parent_root(
                ParentRootAttestationRequest(
                    cwd=attestation_cwd,
                    explicit_root=None,
                    purpose="report-artifact",
                )
            )
''',
        "future report bundle attestation",
    )

    tests = Path("tests/agent_tools/test_check_agent_runtime_alignment.py")
    replace_once(
        tests,
        "from team_config import TaskCatalog, load_team_config, resolve_role  # noqa: E402\n",
        "from team_config import TaskCatalog, load_team_config, resolve_role  # noqa: E402\n"
        "from workspace_scope import resolve_report_bundle_artifact_path  # noqa: E402\n",
        "workspace scope regression import",
    )
    anchor = "    def test_alignment_script_passes(self) -> None:\n"
    regression = indent(
        dedent(
            '''
            def test_missing_report_bundle_path_uses_existing_git_parent(self) -> None:
                """A future report bundle is checked without being created."""
                with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir:
                    report_dir = Path(tmp_dir) / "reports" / "agents" / "future-run"

                    resolved = resolve_report_bundle_artifact_path(
                        report_dir,
                        "intent_brief.md",
                    )

                    self.assertEqual(resolved, report_dir / "intent_brief.md")
                    self.assertFalse(report_dir.exists())

            '''
        ).lstrip("\n"),
        "    ",
    )
    source = tests.read_text(encoding="utf-8")
    if source.count(anchor) != 1:
        raise SystemExit("runtime alignment regression anchor changed")
    tests.write_text(source.replace(anchor, regression + anchor), encoding="utf-8")


if __name__ == "__main__":
    main()
