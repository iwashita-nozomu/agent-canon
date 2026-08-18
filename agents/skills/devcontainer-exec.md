# devcontainer-exec
<!--
@dependency-start
contract skill
responsibility Executes targeted commands inside an already-running Dev Container.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../CONTAINER_OPERATIONS.md container and devcontainer ownership boundary
upstream design ./environment-maintenance.md canonical image-build and full-test acceptance owner
downstream implementation ../../tools/agent_tools/skill_shim_materializer.py runtime discovery shim
downstream implementation ../../tools/agent_tools/route.py prompt route
downstream implementation ../../tests/agent_tools/test_environment_skill_expected_structure.py acceptance-boundary contract
@dependency-end
-->

## Reader Map

- Purpose: 既存の Dev Container 内で、指定 workspace に対する一時的な実行・検証を行います。
- Use When: 起動済み container で `devcontainer exec` を使い、zsh または caller-selected test を実行するときに使います。
- Boundary: Dockerfile、dependency、devcontainer の起動・build・設定変更は
  `environment-maintenance` または `dependency-design` に渡します。GPU profile の意味は
  `gpu-execution` の owner に残します。既存containerの実行結果はenvironment acceptanceではなく、
  canonical imageのbuildと`docker run`による標準テスト一式を置き換えません。

## Workflow

1. 実行する repository root を解決し、既存の running container に対応する exact workspace
   selector を固定します。通常は次を使います。

   ```bash
   devcontainer exec --workspace-folder <root> zsh -lc '<command>'
   ```

   人が一時的に shell に入る場合は
   `devcontainer exec --workspace-folder <root> zsh -l` を使います。
   `zsh -lc` は非対話起動であり `.zshrc` の sourcing を証明しません。interactive startup
   または `.zshrc` の意味を検証する明示要求がある場合だけ `zsh -lic` を使います。

2. `devcontainer exec --workspace-folder <root> [--config <selector>] id` と `pwd` を
   同じ workspace/config selector で読み、続けて caller の exact command を実行します。
   stdout、stderr、command の exit status を加工せず保持します。実行記録には workspace、
   optional config selector、container 内 identity、container 内 pwd、command、exit status
   を記録します。

3. discovery で一致する running container がない場合は
   `container_not_running` を typed evidence として返し、そこで停止します。`devcontainer up`、
   `docker exec`、rebuild、host sudo、host group mutation、未要求の別 selector は行いません。

4. GPU admission など opt-in profile を caller が指定した場合は、起動時と同じ exact
   `--config <selector>` を `devcontainer exec` に渡します。default container へ暗黙に
   fallback しません。temporary write probe は caller が明示した exact target だけに行い、
   必ず cleanup して、未知の user/other-agent state を保存します。

5. caller が指定した targeted test だけを実行し、検証範囲を広げません。startup/build request
   や Dockerfile/dependency/config change はこの skill の owner ではありません。
   repository environmentの完成判定を求められた場合は`environment-maintenance`へ渡し、
   clean buildしたcanonical imageを`docker run`して標準テスト一式を実行します。

## Completion And Failure Semantics

各操作を `operation -> resulting state -> completion evidence` で閉じます。

- workspace/config discovery -> exact existing container selector state -> resolved workspace と
  selector の readback。
- identity/pwd/command execution -> requested in-container command state -> preserved stdout/stderr、
  in-container identity/pwd、exact command、exit status の receipt。
- missing running container -> `container_not_running` blocked state -> typed evidence と停止記録。
- temporary write probe -> caller-authorized target の一時状態 -> cleanup 成功と元の unknown state
  保持の evidence。

exit status が非ゼロの場合は成功へ変換せず、元の status と出力をそのまま報告します。
profile selector、workspace、target、または container identity の不一致は fail-closed とし、
default fallback や別の実行経路で補いません。

このskillの成功はrequested commandの成功だけを示します。image constructionやrepositoryの
標準テスト一式の成功を示すものではありません。
