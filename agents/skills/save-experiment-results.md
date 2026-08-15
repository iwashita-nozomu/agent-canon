# save-experiment-results

<!--
@dependency-start
contract skill
responsibility Documents deterministic git-annex retention for one experiment result.
upstream design ../canonical/skills.md skill canon registry
upstream design experiment-lifecycle.md experiment lifecycle workflow
upstream design result-artifact-writeout.md durable raw/result/report artifact writeout
upstream design ../../documents/experiments/result-log-retention-and-visualization.md experiment result retention policy
downstream implementation ../../tools/experiments/save_experiment_result_annex.py saves one archive
@dependency-end
-->

## Reader Map

- Purpose: retain one existing experiment result as one reproducible git-annex archive.
- Use when: one `experiments/<topic>/result/<run_name>/` tree and its optional report
  need append-only external retention.
- Boundary: this skill retains result artifacts. Experiment execution belongs to
  `experiment-lifecycle`; report interpretation belongs to `report-writing`.

## Purpose

実験結果を source checkout に混ぜず、同じ run の raw files と optional report を
一つの deterministic `tar.gz` として git-annex worktree に保存します。source は
読み取り専用であり、保存先の衝突、symlink、special file、Git-LFS pointer、途中の
commit 失敗による部分状態を許しません。

## Required Contract

1. Start from exactly one existing `experiments/<topic>/result/<run_name>/` directory.
   A result directory with no regular result file is rejected; a report alone is not
   a result.
1. Invoke the public route with only these inputs:

   ```bash
   python3 tools/experiments/save_experiment_result_annex.py \
     --result-dir experiments/<topic>/result/<run_name> \
     --annex-repo /path/to/git-annex-worktree \
     [--source-repo-root /path/to/source]
   ```

   `--annex-repo` may be supplied by `EXPERIMENT_RESULT_ANNEX_REPO`. There is no
   report-path, publication target, push, remote, overwrite, batch, all-run, or
   migration option.
1. The source tree is archived under its repository-relative paths. The optional
   `experiments/report/<run_name>.md` is included when present. The external target is
   exactly `experiments/<topic>/result/<run_name>.tar.gz` in the annex worktree.
1. The archive contains directory entries, all regular result files, the optional
   report, and `experiments/<topic>/result/<run_name>/annex_retention_manifest.json`.
   The manifest records schema, run identity, source branch/commit/dirty paths,
   `run_manifest.json` SHA256 when present, nullable report path and presence, archive
   configuration/path, `append_only`, sorted directories, and every source file's
   path, size, SHA256, and normalized executable mode.
1. Archive bytes use stdlib gzip (`filename=''`, mtime `0`, level `9`) and sorted PAX
   tar entries. All uid/gid/name and mtime fields are normalized; regular files use
   normalized executable or non-executable modes. JSON is sorted, compact, UTF-8, and
   ends with one final newline.
1. Reject symlink or special source entries, Git-LFS pointer files, reserved manifest
   collisions, source/annex root equality or containment, existing target collisions,
   and any archive worktree path outside `.gitattributes` and the archive layout.

## Annex Transaction

1. Require an existing clean, non-bare git-annex worktree on a normal branch, with a
   clean index/worktree and no legacy result-retention refs. Source and annex are
   distinct non-containing roots; the source is never modified. The temporary archive
   is created beside its final annex path so no-replace installation stays on one
   filesystem.
1. Build in a temp file beside the final target, fsync it, reread and verify every
   archive member, then publish with atomic no-replace `os.link(temp, final)` and
   unlink the temp name. A collision or race fails without replacing the existing
   target.
1. Run `git annex add --backend=SHA256E -- <archive>`, verify staged/worktree paths,
   run full `git annex fsck -- <archive>` before commit, verify the SHA256E lookup key
   and real contentlocation size/SHA256, then make exactly one normal-branch commit.
   Run full fsck and a complete archive reread after commit, and require clean status.
1. Before commit, rollback is limited to this task's archive/index entries,
   operation-owned `.gitattributes`, and task-created empty directories. Use bounded
   `git update-index --force-remove`; unreferenced annex objects may remain. After a
   commit, never rewind it: return the retained commit SHA with an unverified error.

## Closeout Tokens

The successful command emits:

```text
EXPERIMENT_RESULT_STATUS=complete
EXPERIMENT_RESULT_ARCHIVE_PATH=<path>
EXPERIMENT_RESULT_COMMIT=<sha>
EXPERIMENT_RESULT_ANNEX_KEY=SHA256E-...
EXPERIMENT_RESULT_ARCHIVE_SIZE=<bytes>
EXPERIMENT_RESULT_ARCHIVE_SHA256=<sha256>
```

Record these tokens with the source result path, source provenance, report presence,
manifest path, and append-only collision policy. A failed postcommit verification
records the retained commit and does not claim completion.

## Runtime Contract Clauses

1. Read this canonical owner before applying the runtime shim.
1. Preserve raw result files before deriving any reader-facing interpretation.
1. Keep failed, skipped, blocked, and partial runs in their source result directory;
   this route records only existing artifacts and never invents missing output.
1. Use a new run name for a new result; an existing archive is never overwritten.
