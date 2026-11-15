# Role viewの期待値

[role生成テスト](../../agent_tools/test_evaluate_codex_agent_roles.py) は37roleの集合と
metadata、live assignmentのSHA256、保存済みconsumer-static TOML全体のSHA256を確認します。
live assignmentは空行とコメントを除いた行を改行で結び、末尾へ改行を1つ付けた内容です。
metadata fixtureは比較対象の設定を保持し、developer instructions全体はSHA256で照合します。
既存のCI Evalユニットがこの比較を実行し、role定義・生成器・fixtureの変更を既存の
path selectorがそのユニットへ振り分けます。

独立期待値はRust移行時のcommit `f906c7e12` で採取されました。その後、commit
`f473d57c0` ([PR #1843](https://github.com/iwashita-nozomu/agent-canon/pull/1843)) が
worker、spark_worker、integration_executorからwriter-targetと専用spawn経路の2文を
削除しました。[Issue #1887](https://github.com/iwashita-nozomu/agent-canon/issues/1887) の修正は
この3roleのlive/static期待値へ同じ削除を反映しています。

更新時は、現行live assignmentへ廃止済みの2文を戻すと旧fixtureのSHA256に一致すること、
旧static TOMLから同じ2文を削除すると現行ファイル全体に一致することを確認しました。
他の34roleの期待値とモデル設定は保持しています。今後の変更でも、合意した差分と
独立期待値の関係を確認して期待値を更新します。
