# C++ debugging

<!--
@dependency-start
contract design
responsibility Defines native C++ debugging tool choice, image provisioning, and evidence boundaries.
upstream design ../../CONTAINER_OPERATIONS.md shared image and project execution boundary
upstream design ../experiments/host-build-admission.md existing compiler execution safety
upstream design ../conventions/coding-conventions-cpp.md C++ implementation conventions
downstream implementation ../../bootstrap/container/image/Dockerfile installs native diagnostic utilities
downstream design ../../agents/skills/cpp-review.md selects debugging evidence when relevant
downstream implementation ../../tests/tools/test_cpp_debug_tools.py verifies image additions and unchanged isolation
@dependency-end
-->

## 必要性と配置

C++ の crash、停止、寿命違反、未初期化値は、source review や clangd の静的診断だけでは
実行時の原因を特定できません。GDB の stack / variable / core 解析と Valgrind Memcheck
のメモリ診断を既存 C++ reviewer が使えるようにします。compiler が提供する sanitizer
も組み合わせますが、独自 debugger、出力 parser、公開 API、診断用 wrapper は作りません。

`bootstrap/container/image/Dockerfile` の既存 apt transaction に `gdb` と `valgrind` を
追加します。compiler support と同じ image-owned native utility とし、Ubuntu の通常の
package resolution を使います。新しい version / SHA pin や第二 installer は加えません。
依存 manifest が既に所有する package と既存 lock / integrity check は変更しません。

この変更は共有イメージへの提供であり、全 consumer の開発イメージへの一括導入では
ありません。反映は既存 `bootstrap.sh` の install / update が所有し、通常編集のたびに
再構築しません。実際に解決された package version は image 検証時に記録します。

## 実行境界と選択

製品 binary の再実行、live debugging、sanitizer build は、その製品の既存 runner / image
が所有します。共有 resident を製品 test runner に変えず、追加 package の存在を理由に
未登録の `tool run` ID や任意実行経路を増やしません。既存プロジェクトで必要な package
が欠ける場合も、無断の host install や別 image への切替ではなく、その環境 owner に
導入箇所を返します。共有イメージの提供と製品環境での利用確認は別の成果です。

crash / hang には GDB、再コンパイルできるメモリ破壊には ASan、言語上の未定義動作には
UBSan、未初期化値の由来や非 sanitizer binary のメモリ診断には Memcheck を使います。
並行処理の data race が問題なら TSan を別 build で使います。全ツールを一律に起動せず、
観測された問題または明示された調査に必要なものだけを選びます。

既存の実行許可、resource limit、再実行禁止を守ります。共有 resident の cap-drop、
seccomp、read-only root、network 制限は変更しません。ptrace が拒否された場合に
`--privileged`、`SYS_PTRACE`、`seccomp=unconfined` を自動追加しません。
対応する core が既にあれば再実行なしの解析を使えますが、core の取得を普遍要件に
しません。未実施の診断は未検証と記し、無関係な編集や既存の検証を止めません。

## GDB: 停止位置、変数、core

以下は対象プロジェクトの既存実行環境内で使う native command です。`BINARY` は実際の
対象実行ファイル、`CORE` はその実行で得た core を表します。新しい設定項目ではありません。
対象 binary と対応する debug symbols / shared libraries を使い、元の引数と入力を保ちます。
最適化依存の不具合を Debug build へ置き換えて「再現しないので解消」と扱いません。

```bash
gdb --nx --args "$BINARY" <元のプログラム引数>
```

```text
(gdb) run
(gdb) thread apply all bt full
(gdb) frame 0
(gdb) info locals
```

hang の調査では許可された実行を interrupt して thread stack を確認します。必要な
breakpoint、`next`、`step`、`print` は GDB の標準 command を直接使います。
既存 core の非対話解析は次です。

```bash
gdb --nx --batch -ex 'thread apply all bt full' "$BINARY" "$CORE"
```

GDB 自身の終了コードと対象 program の終了 / signal は別です。GDB が成功しただけで
対象が正常終了したと判定せず、stop reason と stack を調査結果へ残します。

## Memcheck: 不正アクセス、未初期化値、leak

sanitizer を重ねていない対象 binary を、同じ入力で実行します。

```bash
valgrind --tool=memcheck --leak-check=full --show-leak-kinds=all \
  --track-origins=yes --error-exitcode=1 "$BINARY" <元のプログラム引数>
```

`--track-origins=yes` は未初期化値の由来を追い、`--error-exitcode=1` は検出エラーを
正常終了と混同しないための指定です。全 leak kind を表示しても、全 kind が exit code
のエラー対象になるわけではありません。native summary の分類をそのまま読みます。
計測負荷を通常実行の性能値と比較せず、既存の上限を緩和して通しません。

## Sanitizer: 既存 build への計測追加

既存 compiler と project-owned diagnostic target / build 設定を使います。ASan / UBSan
の例では、対象の compile と最終 link の両方に `-fsanitize=address,undefined` を渡し、
compile に `-g -O1 -fno-omit-frame-pointer -fno-sanitize-recover=undefined` を加えます。
既存 target の依存関係に沿って計測し、無関係な全 target へ global flag を注入しません。
必要な runtime library は対象 compiler の環境 owner が提供します。

UBSan は既定で診断後に継続する検査があるため、診断を test failure にする実行では
non-recovering 設定を使います。既存 program の原本出力を破棄する理由にはしません。
TSan は compile / link に `-fsanitize=thread` を使う別 build とし、ASan と同じ binary に
混在させません。Memcheck と sanitizer も別実行にします。

## 検証と結果

イメージ変更の静的回帰テストは次です。

```bash
python3 -m unittest discover -s tests/tools -p test_cpp_debug_tools.py -v
```

これは apt 導入定義と resident の隔離設定の確認であり、package install や native debugger
の実動作確認ではありません。

実イメージの導入確認では `gdb --version`、`valgrind --version` と解決 package を記録します。
利用確認では、許可された既存 C++ test の正常ケースと対象不具合を使い、停止位置や診断が
意図した source に対応するか確認します。対象環境で実行できない場合は、行った静的検証と
未実施の build / native smoke を分離して Issue / PR に残します。

command、入力、signal / exit status、関係する stack / diagnostic、修正後の回帰結果は既存
Issue / PR の記録へ載せます。core や locals は秘密情報を含み得るため、そのまま公開せず
必要な箇所を秘匿処理します。診断ゼロは実行した経路の観測であり、全入力での正しさや
数値計算の妥当性の証明ではありません。

## 一次資料

- [GDB manual](https://sourceware.org/gdb/current/onlinedocs/gdb/)
- [Valgrind Memcheck manual](https://valgrind.org/docs/manual/mc-manual.html)
- [Valgrind core options](https://valgrind.org/docs/manual/manual-core.html)
- [Clang AddressSanitizer](https://clang.llvm.org/docs/AddressSanitizer.html)
- [Clang UndefinedBehaviorSanitizer](https://clang.llvm.org/docs/UndefinedBehaviorSanitizer.html)
- [Clang ThreadSanitizer](https://clang.llvm.org/docs/ThreadSanitizer.html)
