# Runtime debugging

<!--
@dependency-start
contract design
responsibility Selects standard system and Python diagnostics without creating another execution route.
upstream design ../../ROOT_AGENTS.md fixed execution and evidence boundaries
upstream design ../../CONTAINER_OPERATIONS.md shared image and product environment boundary
downstream design cpp-debugging.md selected native stack and memory diagnostics
downstream design ../../agents/skills/python-review.md conditional Python diagnostic reader
downstream design ../../agents/skills/user-guided-debugging.md conditional parent-executed diagnostic reader
downstream implementation ../../bootstrap/container/image/Dockerfile native utility provisioning
downstream implementation ../../tests/tools/test_cpp_debug_tools.py existing provisioning regression
@dependency-end
-->

## Tool selection

観測された症状に対応する節だけ読み、次の判断に必要な診断だけ選びます。全ツールの
起動や全文読取りを通常編集の前提にしません。

| 症状・必要な観測 | 選択する標準機能 |
| --- | --- |
| process / thread の状態、待機位置 | [System observation](#system-observation) の `ps` |
| 開いている file descriptor、socket | 同節の `lsof` |
| file / network / child-process の syscall と失敗理由 | 同節の `strace` |
| Python の停止位置、frame、変数、fatal signal の traceback | [Python debugging](#python-debugging) の `pdb` / `faulthandler` |
| C / C++ の crash、memory corruption、未初期化値、data race | [既存 C++ debugging](cpp-debugging.md) の GDB / Memcheck / sanitizer |

## Provisioning and execution boundary

既存 Dockerfile の単一 apt transaction で `strace`、`lsof`、`procps` を明示導入します。
既存 GDB / Valgrind と同じ image-owned utility とし、通常の Ubuntu package resolution
を使います。Python は導入済み interpreter の標準ライブラリを再利用します。独自 wrapper、
parser、公開 tool ID、第二 installer、追加の version / SHA pin は作りません。

共有イメージへの提供と製品環境への導入・実利用は別です。以下の例は、対象 owner の
規定 runner が扱う環境内の native command であり、host 直実行や entrypoint 差替えの
許可ではありません。元の image、interpreter、入力・引数、resource / rerun 制限を保ちます。
規定経路が診断を扱えない場合は、必要な操作と不足する機能をその owner に返します。
共有 resident の任意 dispatch、製品実行、別環境への切替を追加しません。

通常は規定経路を既定値で実行し、失敗後に関係する診断を選びます。明示された診断依頼は
その範囲で扱い、成功時の追加 preflight は不要です。cap-drop、seccomp、read-only root、
network 制限は維持し、ptrace 拒否を `--privileged`、`SYS_PTRACE`、
`seccomp=unconfined` の自動追加で回避しません。

## System observation

`PID` は同じ実行環境・PID namespace で確認した担当対象です。全ホストの無制限走査や
別 session の process への attach はしません。対象終了、PID 再利用、権限・namespace に
よる不可視を区別し、取得できない情報を「異常なし」と扱いません。

thread 状態を調べる場合は、procps の snapshot を使います。

```bash
ps -L -p "$PID" -o pid,tid,stat,wchan:32,comm
```

file descriptor を調べる場合は次を使います。`-nP` は名前・port 名の解決を省きます。

```bash
lsof -nP -p "$PID"
```

同じ PID の TCP socket だけ必要なら `lsof -nP -a -p "$PID" -iTCP` とします。
`-a` なしでは選択条件が OR になり得るため、別 process の socket を混ぜません。

syscall の調査が必要で attach が許可されている場合の file-operation 例です。
`TRACE` は既存 task storage owner が選んだ書込可能な出力先で、新しい設定項目ではありません。

```bash
strace -f -tt -T -e trace=%file -o "$TRACE" -p "$PID"
```

network は `%network`、process lifecycle は `%process`、futex wait は `futex` など、
対象症状に合わせて filter を選びます。`-f` は対象 thread と子 process も追跡します。
必要な観測が得られたら既存の時間・出力上限内で detach します。この attach 形式では
strace の Ctrl-C で対象を終了せず離脱できますが、起動形式の signal 動作と混同しません。
ptrace や計測負荷で timing が変わるため、非再現を解消証明や通常性能値にはしません。

## Python debugging

`PYTHON` は対象 runner の既存 interpreter、`MODULE` は実際の対象 module です。
元が script 起動なら `-m "$MODULE"` の代わりに元の script path を維持します。
例中の引数を元の値に置き換え、診断目的で別 Python や独立 runner を作りません。

停止位置や変数を対話調査するときは標準 pdb を使います。

```bash
"$PYTHON" -m pdb -m "$MODULE" <元のプログラム引数>
```

`where`、`up` / `down`、`break`、`next` / `step`、`p <変数>` で必要な frame を調べます。
pdb は終了後に再開可能な状態へ戻るため、追加実行が許可されていなければ `quit` で終了し、
そのまま `continue` して再実行しません。式評価や `.pdbrc` も実行を伴い得ます。

fatal signal 時の Python traceback が必要な許可済み実行では、標準機能を有効にします。

```bash
"$PYTHON" -X faulthandler -m "$MODULE" <元のプログラム引数>
```

この設定だけでは通常の hang に timeout dump は発生しません。hang の traceback は
対象が既に提供する `dump_traceback_later` / 登録済み signal handler などの診断機能を
使い、未登録 signal を送信しません。必要な機能がなければ対象 owner に不足を返します。
ユーザー主導 debugging の親直接実行と修正後検証の明示指示条件は、呼出元 skill に残します。

## Evidence and validation

実装上の根拠は既存 Dockerfile の apt transaction、既存 Python、既存 C++ 診断文書です。
静的 source review では syscall、FD、thread state、実行時 Python frame を観測できないため、
これらの標準機能を追加・接続します。標準出力形式で足りるので新しい診断 framework は不要です。
package の提供は ptrace 可否や対象プロセスの可視性を保証しません。

既存 `tests/tools/test_cpp_debug_tools.py` が package 宣言と隔離設定を検査します。
その owner の規定経路で `python3 -m unittest discover -s tests/tools -p test_cpp_debug_tools.py -v`
を実行します。実 image の検証では `dpkg-query -W strace lsof procps`、`strace -V`、
`lsof -v`、`ps --version` と、許可された対象での必要な診断結果を別に記録します。
静的テスト、package install、native 動作確認、製品修正後の回帰検証を同一視しません。

command、入力、実行環境、対象の signal / exit、stack / syscall / FD の根拠と未取得範囲を
既存 Issue / PR に残します。ツールの成功は対象の正常終了を意味しません。trace、locals、
path、引数には秘密情報が含まれ得るため、原本は既存 storage owner で扱い、公開は必要な
秘匿済み抜粋だけにします。稼働 image や対象環境で未実施の診断は未検証と明示します。

## References

- [strace](https://strace.io/) / [Ubuntu strace manual](https://manpages.ubuntu.com/manpages/noble/man1/strace.1.html)
- [lsof manual](https://man7.org/linux/man-pages/man8/lsof.8.html)
- [procps ps manual](https://man7.org/linux/man-pages/man1/ps.1.html)
- [Python 3.12 pdb](https://docs.python.org/3.12/library/pdb.html)
- [Python 3.12 faulthandler](https://docs.python.org/3.12/library/faulthandler.html)
