<!--
@dependency-start
contract design
responsibility Documents the jax_util algorithm module contract and its single AgentCanon checker route.
upstream design ../algorithm-implementation-boundary.md algorithm boundary policy
upstream design ../../conventions/coding-conventions-python.md Python implementation policy
downstream implementation ../../../tools/agent_tools/check_algorithm_config_partition.py checks config ownership
downstream implementation ../../../rust/agent-canon/src/python_algorithm_contract.rs owns the single algorithm contract checker
downstream implementation ../../../tools/catalog.yaml records the canonical checker and capability surface
downstream implementation ../../../tools/ci/run_all_checks.sh invokes the canonical checker in CI
@dependency-end
-->

# JAX Util Algorithm Module Contract

この文書は `algorithm_module_protocol` を使う Python algorithm module の契約と、
その契約を検査する AgentCanon の単一 route の設計正本です。対象は
public surface、callable `Algorithm`、nested ownership、`Info` の concrete schema、
診断 artifact、CI route です。config の初期化時／実行時 ownership は
`check_algorithm_config_partition.py` の責務として、この統合の対象外にします。

## 設計構造契約

- audience: Rust checker の実装者、CI/catalog owner、Python algorithm module の保守者。
- decision_context: 二つの Python checker を退役させ、Rust owner へ一度だけ移行しても、既存の supported finding と CLI/artifact capability を失わないことを決める。
- first_artifact: parity matrix。
- first_artifact_question: 現行二つの Python route と Rust route のどの観測可能な差を、単一 Rust route が吸収する必要があるか。
- visual_plan: table。各 checker の finding、status、diagnostic、syntax behavior の対応を一つの行で比較でき、別の flowchart は情報を重複させる。
- document_unit: owner は本ファイル、reader は上記の実装者と route owner、source map は parity matrix の各行から指定 path へ張る、validation は Rust tests・fixture readback・docs check、update cadence は algorithm contract または checker surface の変更時、canonical parent は `documents/design/README.md`、downstream consumers は Rust owner・catalog・CI・tool docs。
- document_split_decision: keep。同じ owner、reader、validation route、source map、update cadence を共有し、別の責務単位を新設しない。
- ordered_structure: target decision → parity matrix → canonical output contract → Rust gaps → retired surfaces → migration order → readback and acceptance.
- invalid_interpretations: Python wrapper を残す二重 route、旧 CLI の alias、finding prefix の二重出力、`Info` の run-log summary だけを child ownership の代替とみなすこと。
- validation_gate: Rust unit/integration tests、fixture matrix の CLI readback、catalog/dependency/static checks、`tools/bin/agent-canon docs check`。

## 現行契約と証拠

algorithm module は次の標準 public name を持つ。

`InitializeConfig`、`SolveConfig`、`Problem`、`State`、`Answer`、`Info`、
`Algorithm`、`initialize`。

`InitializeConfig` は setup-time input と logging/output sink、`SolveConfig` は
runtime numerical control と stopping policy を所有する。親 algorithm が child
algorithm を包む場合は、child の ownership を親の contract field として露出する。
`Info` は親の summary でよく、child の詳細を run-log に出す設計は許可する。ただし
`Info` 自体は protocol の再 export ではなく、対象 module 内の concrete class とする。

根拠は最終 tree の次の source に固定する。

- `rust/agent-canon/src/python_algorithm_contract.rs` が単一の Rust owner として AST
  JSON を一度抽出し、standard surface、callable `Algorithm`、nested `Info` を含む
  contract、legacy stopping policy の finding を一つの report にまとめる。退役した
  Python checker は互換 wrapper や別 route として残さない。
- `tools/catalog.yaml`、`documents/tools/README.md`、`tools/ci/run_all_checks.sh`
  は `python-algorithm-contract-check` の単一 capability、CLI、CI wiring を final
  tree の source として参照する。旧 Python implementation/test path は retire set
  と parity matrix の履歴 evidence にだけ残り、active route の根拠にはしない。
- `tests/fixtures/python_algorithm_contract/` の `.py.fixture` と
  `rust/agent-canon/tests/python_algorithm_contract_cli.rs` が、CLI artifact の
  file/module/finding/parse-error readback を固定する canonical fixture/test surface
  である。

## Parity matrix

| 観点 | Python public surface checker | Python nested checker | Rust owner の現状 | 単一 route の target contract |
| --- | --- | --- | --- | --- |
| Public API set | protocol import module を選び、8 名を `__all__` と top-level definition の両方で要求する。literal 以外の `__all__`、extra name、extra public definition、allowlist 外の protocol-only import を finding にする。`STATUS_` は許可する。 | 標準面そのものは判定しないが、同じ AST candidate 判定を使う。 | 8 名の不足だけを検出し、`__all__`、extra definition、protocol-only import は失う。 | 8 名、literal `__all__`、`STATUS_` exception、extra/missing `__all__`、extra/missing definition、protocol-only import を Rust finding として一つに出す。path-relative な旧 finding kind の意味を保持し、`missing_algorithm_public_surface` は `missing_public_definition` へ正規化する。 |
| Callable `Algorithm` | 判定しない。 | 判定しない。 | `Algorithm.__call__` の有無を判定する。signature の詳細までは判定しない。 | 現行 Rust の capability と finding (`algorithm_not_callable` / `missing_algorithm_function_object`) を保持する。signature/return type の新しい意味はこの wave で追加しない。 |
| Nested ownership | 判定しない。 | annotation の `child.InitializeConfig`、`child.SolveConfig`、`child.Info`、`child.Algorithm` と `child.initialize(...)` を AST から検出する。annotation は対応する親 contract class を要求する。`initialize` は `Algorithm` を要求し、第一引数が parent `config.<field>` の場合だけ `InitializeConfig` を要求する。`child.InitializeConfig(...)` の局所構築、`Problem` のみ、child usage が無い summary `Info` は exempt。 | discovered algorithm alias の usage と annotation を検出するが、現状は `initialize` usage を `InitializeConfig`、`SolveConfig`、`Info`、`Algorithm` の一括要求へ展開するため、局所 child-config call-site を過剰報告し得る。legacy stopping findings も持つ。 | call-site と owned annotation を別の evidence として扱う。`child.X` annotation は対応する親 contract class を要求し、`child.initialize(...)` は親 `Algorithm` を要求する。第一引数が `child.InitializeConfig(...)` なら親 `InitializeConfig` を要求しない。第一引数が `config.<field>` を読むなら親 `InitializeConfig` を要求する。`Problem` のみと child usage が無い summary `Info` は exempt。finding は dependency alias、contract class、owning class、line を構造化する。 |
| Protocol-only import | protocol を import し、8 名の public surface を持たない non-allowlisted production file は `non_algorithm_protocol_import` を一件だけ出す。line は 1、detail は `define-standard-public-surface-or-remove-import`。allowlisted path は無視する。 | module candidate にはなるが、この one-finding contract は独自には出さない。 | non-allowlisted protocol-only file を通常の algorithm module として扱い、missing public surface/callable findings を複数出し得る。allowlist はある。 | non-allowlisted file は `non_algorithm_protocol_import` 一件だけに正規化し、missing public/Info/Algorithm の追加 finding を出さない。`path`、`line=1`、`kind`、`subject=algorithm_module_protocol`、`detail=define-standard-public-surface-or-remove-import` を固定する。`python/jax_util/base`、`python/jax_util/canon`、`python/tests`、`tests` とその配下は finding も module record も持たない。 |
| Concrete `Info` schema | `Info` の存在を public definition として数えるだけで、class か alias かは区別しない。child `Info` は annotation があるときだけ確認する。 | summary `Info` が child `Info` を全て持つことは要求しない。 | public definition と nested child `Info` は見るが、`Info = amp.Info` のような alias を concrete schema として拒否しない。 | top-level `class Info` を必須にする。zero-field summary class は有効、child `Info` field は実際の annotation/strict `initialize` ownership に応じて要求する。alias/re-export/assignment は `info_not_concrete` とし、Info field の型 annotation line を artifact に残す。 |
| Failure status | pass は exit 0、finding は exit 1。 | pass は exit 0、finding は exit 1。 | finding または parse error は exit 1、argument/AST tool error は exit 2。 | 0/1/2 を Rust CLI の canonical status として保持する。JSON の `summary.status` は `pass`/`fail`、contract finding と parse error の件数を分離し、片方でも存在すれば exit 1。 |
| Path/line diagnostics | root-relative path。`__all__` finding は `__all__` line、definition finding は定義 line、nested missing field は owning class line、missing class は line 1。 | root-relative path。missing field は owning class line、missing class は line 1。 | class/field/import line は保持するが、public surface の `__all__` と extra definition、parse error の line schema が不足する。 | JSON の finding は `{path,line,kind,subject,detail}`、parse error は `{path,line,kind=syntax_error,detail=parseable}`。root-relative POSIX path と 1-based line を固定し、既存 Python line semantics を移植する。 |
| Malformed syntax | 全対象 file を AST parse し、SyntaxError なら line 付き `syntax_error` finding を一件出す。detail は `parseable`、status は fail。 | 同じく一件の syntax finding。detail は `parseable`。 | Python AST extractor は parse error を集めて exit 1 にするが、JSON は opaque string、text は明示 line field ではない。 | extractor が `path,line,kind=syntax_error,detail=parseable` を返し、Rust report が `parse_errors` として構造化する。対象 file の contract analysis は続けず、他 file の findings は保持する。JSON/text とも parser 原文を出さず detail を exact `parseable` に固定する。text は `PY_ALGORITHM_CONTRACT_PARSE_ERROR=<path>:<line>:parseable` とする。 |
| `--exclude` discovery | non-glob は exact/path-prefix/path-part、glob は `fnmatch` で判定する。repeatable option は union。 | 同じ discovery contract。 | non-glob は扱うが、`*`、`?`、`[]` の fnmatch glob を literal path として扱い、Python parity を失う。 | POSIX root-relative path を正規化し、glob pattern は `fnmatch.fnmatchcase` 相当、non-glob は既存の exact/prefix/part semantics、repeatable option は union とする。default exclude と explicit exclude は同じ判定器を通し、fixture の file/module/count readback を固定する。 |

### Local child-config exemption oracle

`InitializeConfig` の ownership は、annotation と call-site を同じ evidence として
扱わない。target checker は次の順で requirement を作る。

| fixture shape | dependency evidence | parent requirement | expected result |
| --- | --- | --- | --- |
| `child_initialize: child.InitializeConfig` | owned annotation | `InitializeConfig` | field が無ければ `missing_nested_field`, subject=`child.InitializeConfig` |
| `child.initialize(config.child_initialize)` | call-site が parent `config.<field>` を読む | `InitializeConfig` と `Algorithm` | `InitializeConfig` field と `Algorithm` field が無ければそれぞれ一件ずつ |
| `child.initialize(child.InitializeConfig())` | call-site の local constructor | `Algorithm` のみ | 親 `InitializeConfig` field が無くても pass。親 `Algorithm` field が無ければ `child.Algorithm` 一件 |
| `child.initialize(make_child_config(config))` | call-site が `config` を読むが direct child constructor ではない | `InitializeConfig` と `Algorithm` | parent config ownership を要求 |
| `child.Problem` だけ | Problem-only reference | none | nested finding なし、dependency record は contract class 空 |

`child.initialize(child.InitializeConfig())` の fixture は、親に
`child_initialize` field を追加した版と削除した版を同じ CLI fixture row で比較する。
後者の唯一の失敗は親 `Algorithm` ownershipであり、親 `InitializeConfig` 不足を出しては
ならない。逆に `config.child_initialize` 版は親 `InitializeConfig` 不足を必ず出す。
この oracle は Python checker の `is_dependency_initialize_config_construction` と
`uses_parent_config_field` の意味を Rust AST extractor/analysis に移したものであり、
Rust 現状の `initialize`→4 class 一括展開による過剰 finding を許可しない。

### Protocol-only import fixture oracle

non-allowlisted `helper.py` が protocol だけを import して public surface を定義しない
場合の canonical output は次の一件に固定する。

```text
PY_ALGORITHM_CONTRACT_FINDING=helper.py:1:non_algorithm_protocol_import:algorithm_module_protocol:define-standard-public-surface-or-remove-import
PY_ALGORITHM_CONTRACT_FILES=1
PY_ALGORITHM_CONTRACT_MODULES=0
PY_ALGORITHM_CONTRACT_FINDINGS=1
PY_ALGORITHM_CONTRACT_PARSE_ERRORS=0
PY_ALGORITHM_CONTRACT=fail
```

同じ source を `tests/helper.py`、`python/tests/helper.py`、
`python/jax_util/base/helper.py`、`python/jax_util/canon/helper.py` の各 allowlisted
path に置いた fixture は、finding 0、module 0、exit 0 とする。non-allowlisted fixture
では missing public names、callable、`Info`、nested findingを追加せず、上の一件だけを
出す。

### Exclude glob fixture oracle

CLI fixture tree は保存時には `pkg/keep.py.fixture`、`pkg/generated/a.py.fixture`、
`pkg/a_generated.py.fixture` とし、fixture loader が一時 tree にそれぞれ `.py` として
materialize する。各 file は同じ valid algorithm source から作る。
解析対象と期待値は次で固定する。

| CLI invocation | excluded files | `summary.files` delta | `algorithm_modules` delta |
| --- | --- | ---: | ---: |
| no explicit exclude | none | 0 | 0 |
| `--exclude 'pkg/generated/*.py'` | `pkg/generated/a.py` | -1 | -1 |
| `--exclude '*_generated.py'` | `pkg/a_generated.py` | -1 | -1 |
| `--exclude '*/generated'` | none; `pkg/generated/a.py` remains discovered | 0 | 0 |
| both options repeated | both generated files | -2 | -2 |

The implementation test must invoke the public CLI, not only a private predicate, and must
assert that `pkg/keep.py` remains in `modules` in every row. A non-glob `--exclude pkg` row
must retain the existing path-prefix/path-part behavior. The same fixture is run through the
Rust route after the Python checker retirement; no Python compatibility command is used for
the target oracle. Directory traversal is retained for all rows, and the exclude predicate is
applied only to discovered `.py` file paths; a directory-shaped glob therefore does not prune
the directory before its Python files are discovered.

### Legacy stopping fixture oracle

`stopping/legacy_policy.py.fixture` is materialized as `legacy_policy.py` by the same loader.
Its `SolveConfig.criterion: ResidualNormConvergenceCriterion` field preserves the existing Rust
finding `legacy_stopping_policy_field` with `line=7`, `subject=criterion`, and detail
`use imported stopping.SolveConfig so the nested algorithm contract is inferred`; the CLI
readback is one algorithm module, one finding, zero parse errors, and exit 1.

この matrix は「旧 prefix を同時に出す」互換層を意味しない。意味と診断 field を
一つの canonical report に写し、旧 Python command、旧 catalog id、旧 CI invocation
は cutover と同時に削除する。

## Target single route

実装後の唯一の public entrypoint は次です。

```text
tools/bin/agent-canon python-algorithm-contract-check --root <repo-root> [paths...] [--exclude <pattern>] [--format text|json]
```

Rust の `python_algorithm_contract.rs` が file discovery、Python AST JSON extraction、
module classification、contract analysis、report rendering を所有する。`main.rs` の
既存 command dispatch と上記 flags は保持する。`--exclude` は path、path prefix、path
part、glob を受け、旧 Python checker と Rust の default exclusion を union した default
set を使う。positional path が無い場合は root 全体、指定時はその path のみを解析する。

### Canonical finding and artifact schema

JSON は次の shape を固定する。

```json
{
  "summary": {
    "files": 0,
    "algorithm_modules": 0,
    "findings": 0,
    "parse_errors": 0,
    "status": "pass"
  },
  "algorithm_modules": [],
  "modules": [],
  "parse_errors": [],
  "findings": []
}
```

record と array の mapping は次で固定する。

- `summary.files`: discovery 後の全 Python file 数。exclude 後、syntax error file も含む。
- `summary.algorithm_modules`: `algorithm_modules` array の件数。
- `summary.findings`: `findings` array の件数。`parse_errors` は別 count とする。
- `summary.parse_errors`: `parse_errors` array の件数。
- `algorithm_modules`: algorithm module の root-relative POSIX path を lexicographic order
  で並べた array。`modules[].path` と完全一致する。
- `modules`: algorithm module 一件につき一 record、`path` の lexicographic order。
  各 record の fields は `path`、`public_names`、`all_names`、`dependencies` の順で
  projection する。`public_names` は top-level public definition の lexicographic order、
  `all_names` は literal `__all__` の source order（missing/dynamic は空 array）とする。
- `modules[].dependencies`: Problem-only を除く owned/used child dependency の record array。
  `alias`、normalized root-relative `module`、required `contract_classes`、evidence
  `sources` の順で持ち、record は `alias`、`module` の順、classes/sources はそれぞれ
  lexicographic order とする。`sources` の値は `annotation`、`initialize_call`、
  `initialize_parent_config` のいずれか。local `child.InitializeConfig()` は
  `initialize_call` と `Algorithm` だけを記録し、`InitializeConfig` を記録しない。
  relative import を解決できない場合の `module` は normalized import spelling を使い、
  `alias` と `module` の組を stable identity とする。
- `parse_errors`: `{path,line,kind,detail}` record を `path`、`line`、`kind`、`detail` の
  順で持つ。`kind` は常に `syntax_error`、`detail` は parser 原文ではなく exact
  `parseable` とし、path/line order で並べる。
- `findings`: `{path,line,kind,subject,detail}` record をその順で持ち、
  `path`、`line`、`kind`、`subject`、`detail` の tuple order で並べる。

旧 Python の public report (`path`、`public_names`、`all_names`) と nested report
(`path`、alias tuple) は、この mapping へ merge する。旧 Rust JSON は
`summary`、`algorithm_modules`、string array の `parse_errors`、`findings` だけを持つため、
current artifact としては `modules` 不在、parse error の line/type 不足を明示的 gap とする。

### Nested dependency → subject/detail mapping

`dependency_alias` と `contract_class` は別の opaque prose field にせず、canonical
finding の `subject` に `<dependency_alias>.<contract_class>` として固定する。

| contract class | subject | missing contract class detail | missing nested field detail |
| --- | --- | --- | --- |
| `InitializeConfig` | `child.InitializeConfig` | `define InitializeConfig` | `add-field-annotated-child.InitializeConfig` |
| `SolveConfig` | `child.SolveConfig` | `define SolveConfig` | `add-field-annotated-child.SolveConfig` |
| `Info` | `child.Info` | `define Info` | `add-field-annotated-child.Info` |
| `Algorithm` | `child.Algorithm` | `define Algorithm` | `add-field-annotated-child.Algorithm` |

When an existing field name hints at the dependency but is `Any`, `amp.<class>`, or an
alias-expanded equivalent, `detail` is instead the exact typed repair form
`field-<field_name>-uses-<annotation>; annotate as child.<contract_class>`. Thus the
dependency/class to subject/detail mapping is deterministic and does not depend on the
checker invocation route.

`findings` の最小 schema は `path`、`line`、`kind`、`subject`、`detail` とし、旧 Python
findings の意味に加えて Rust 固有の `algorithm_not_callable`、
`missing_algorithm_function_object`、`legacy_stopping_policy_field`、
`stopping_primitive_direct_call`、新規の `info_not_concrete` を許可する。

### Exact current/target output

現行 Rust の pass text は次の順序で出る。

```text
PY_ALGORITHM_CONTRACT_FILES=<n>
PY_ALGORITHM_CONTRACT_MODULES=<n>
PY_ALGORITHM_CONTRACT_FINDINGS=<n>
PY_ALGORITHM_CONTRACT=pass
```

現行 Rust の JSON は、pretty JSON の top-level projection 順を
`summary` → `algorithm_modules` → `parse_errors` → `findings` とし、
`parse_errors` は `"<path>:<python-error-string>"` の string array である。現行 finding
record は `{path,line,kind,subject,detail}` である。target はこの既存 field を保持し、
typed `parse_errors` を `{path,line,kind,detail}`（`kind=syntax_error`、
`detail=parseable`）として出力する。target の top-level projection 順は
`summary` → `algorithm_modules` → `modules` → `parse_errors` → `findings` とする。
次の exact projection にする。

```json
{
  "summary": {"files": 2, "algorithm_modules": 2, "findings": 0, "parse_errors": 0, "status": "pass"},
  "algorithm_modules": ["pkg/child.py", "pkg/parent.py"],
  "modules": [
    {
      "path": "pkg/child.py",
      "public_names": ["Algorithm", "Answer", "Info", "InitializeConfig", "Problem", "SolveConfig", "State", "initialize"],
      "all_names": ["InitializeConfig", "SolveConfig", "Problem", "State", "Answer", "Info", "Algorithm", "initialize"],
      "dependencies": []
    },
    {
      "path": "pkg/parent.py",
      "public_names": ["Algorithm", "Answer", "Info", "InitializeConfig", "Problem", "SolveConfig", "State", "initialize"],
      "all_names": ["InitializeConfig", "SolveConfig", "Problem", "State", "Answer", "Info", "Algorithm", "initialize"],
      "dependencies": [
        {"alias": "child", "module": "pkg.child", "contract_classes": ["Algorithm", "InitializeConfig"], "sources": ["annotation", "initialize_call"]}
      ]
    }
  ],
  "parse_errors": [],
  "findings": []
}
```

Failure projection keeps the same top-level order, sorts all arrays as above, emits typed
`parse_errors`, and emits one `PY_ALGORITHM_CONTRACT_FINDING` per finding. A local config
fixture with only `child.initialize(child.InitializeConfig())` therefore has a dependency
record with `contract_classes=["Algorithm"]`, and a missing parent algorithm field has exactly
`subject=child.Algorithm` and `detail=add-field-annotated-child.Algorithm`; it never adds a
parent `child.InitializeConfig` finding solely from that constructor.

Malformed/valid mixed fixture は、parse error の path、line、detail、ordering と、valid
module の readback を同時に固定する。repository に保存する fixture directory には
`00_malformed.py.fixture`（2 行目が syntax error）と `10_valid.py.fixture`（complete
algorithm module）を置き、CLI integration test の単一 fixture loader が一時 tree へそれぞれ `00_malformed.py` と
`10_valid.py` として materialize して public CLI を実行する。この実行時の target JSON は
次の exact projection とする。

```json
{
  "summary": {"files": 2, "algorithm_modules": 1, "findings": 0, "parse_errors": 1, "status": "fail"},
  "algorithm_modules": ["10_valid.py"],
  "modules": [
    {
      "path": "10_valid.py",
      "public_names": ["Algorithm", "Answer", "Info", "InitializeConfig", "Problem", "SolveConfig", "State", "initialize"],
      "all_names": ["InitializeConfig", "SolveConfig", "Problem", "State", "Answer", "Info", "Algorithm", "initialize"],
      "dependencies": []
    }
  ],
  "parse_errors": [{"path": "00_malformed.py", "line": 2, "kind": "syntax_error", "detail": "parseable"}],
  "findings": []
}
```

The corresponding text must be ordered as follows; no parser exception text is permitted:

```text
PY_ALGORITHM_CONTRACT_PARSE_ERROR=00_malformed.py:2:parseable
PY_ALGORITHM_CONTRACT_FILES=2
PY_ALGORITHM_CONTRACT_MODULES=1
PY_ALGORITHM_CONTRACT_FINDINGS=0
PY_ALGORITHM_CONTRACT_PARSE_ERRORS=1
PY_ALGORITHM_CONTRACT=fail
```

The single fixture loader must materialize the stored `00_malformed.py.fixture` as
`00_malformed.py`, invoke the public CLI on that temporary tree, and assert both files are
discovered, `00_malformed.py` is sorted before `10_valid.py` in diagnostics, the valid module
remains in `algorithm_modules`/`modules`, and the JSON/text path, 1-based line, exact
`parseable` detail, and ordering agree. All tracked fixture source files use the same non-`.py`
`.py.fixture` storage boundary; this keeps intentionally malformed and valid source out of
repository-wide Python source scanners without changing the CLI contract or fixture content.

text artifact は canonical prefix だけを出す。

```text
PY_ALGORITHM_CONTRACT_FINDING=<path>:<line>:<kind>:<subject>:<detail>
PY_ALGORITHM_CONTRACT_PARSE_ERROR=<path>:<line>:parseable
PY_ALGORITHM_CONTRACT_FILES=<n>
PY_ALGORITHM_CONTRACT_MODULES=<n>
PY_ALGORITHM_CONTRACT_FINDINGS=<n>
PY_ALGORITHM_CONTRACT_PARSE_ERRORS=<n>
PY_ALGORITHM_CONTRACT=pass|fail
```

contract finding または parse error が一つでもあれば `PY_ALGORITHM_CONTRACT=fail`
かつ exit 1、CLI 引数不正または AST extractor の内部失敗は exit 2 とする。成功時の
artifact は空 arrays を含み、下流が text の exit status だけに依存しないようにする。

## Rust owner に実装する gaps

1. AST extractor に `__all__` の literal sequence、dynamic/missing state、top-level
   assignment、SyntaxError の line、class kind を追加し、public checker の finding
   を `ModuleAst` から再現する。
2. Rust の public analysis を 8 名の不足だけから、matrix の `__all__`、extra public
   definition、`STATUS_` exception、protocol-only import、allowlist と line semantics
   まで拡張する。
3. nested alias resolution を旧 Python annotation/initialize cases と Rust の discovered
   module resolution の和集合にし、annotation/owned dependency と call-site evidence を
   分離する。`child.InitializeConfig()` は parent `InitializeConfig` requirement を作らず、
   `config.<field>` を読む call-site だけがその requirement を作る。依存 module を一部
   path だけ指定したときも AST usage が明示する ownership を落とさない。finding の重複は
   `(path, line, kind, subject, detail)` で deduplicate する。
4. `Info` の top-level `ClassDef` を concrete schema の境界とし、assignment/import/re-export
   を `info_not_concrete` にする。zero-field class は許可し、child summary を強制し過ぎない。
5. protocol-only import classification を Rust module candidate 判定より前に行い、
   non-allowlisted file は `non_algorithm_protocol_import` 一件だけ、allowlisted file は
   zero finding/zero module とする。kind、line、subject、detail を fixture oracle と
   一致させる。
6. discovery の exclude predicate を `fnmatch` glob parity へ拡張する。POSIX relative
   path、glob/non-glob、repeatable union、default exclude の各組合せを CLI fixture で
   readback し、Rust の literal-only pattern handling を残さない。
7. `parse_errors` を opaque string から typed record へ変え、malformed file 一件ごとの
   path/line readback を追加する。contract findings と parse errors の status/count を
   JSON/text の両方で一致させる。
8. 現行 Rust 固有の legacy stopping findings と callable `Algorithm` finding は削除せず、
   catalog の single capability に含める。`check_algorithm_config_partition.py` の config
   ownership finding は別 tool として残し、この route に再実装しない。

## Retire set と downstream closure

次の Python checker と dedicated test は削除対象であり、stub、wrapper、re-export、
旧 prefix の compatibility route は作らない。

| 種別 | retire path / route | 置換または追随 |
| --- | --- | --- |
| Python implementation | `tools/agent_tools/check_algorithm_module_public_surface.py` | `rust/agent-canon/src/python_algorithm_contract.rs` の public analysis |
| Python implementation | `tools/agent_tools/check_algorithm_module_nested_contract.py` | 同 Rust owner の nested analysis |
| Python test | `tests/agent_tools/test_check_algorithm_module_public_surface.py` | Rust unit/integration tests と CLI fixture readback |
| Python test | `tests/agent_tools/test_check_algorithm_module_nested_contract.py` | Rust unit/integration tests と CLI fixture readback |
| CI route | `tools/ci/run_all_checks.sh` の Python nested invocation と header | `${CANON_BIN} python-algorithm-contract-check --root "$WORKSPACE_ROOT" python` に置換 |
| catalog | `check-algorithm-module-public-surface` entry | 削除。Rust entry に capability を統合 |
| catalog | `check-algorithm-module-nested-contract` entry | 削除。Rust entry の `default_wiring.ci` を `true` に変更 |
| runtime mirror | `documents/runtime/shared-runtime-surfaces.toml` の retired test paths | 二つの test path を削除し、Rust test/fixture surface を登録 |
| runtime inventory | `documents/runtime/log-surface-inventory.json` | Rust owner fix 後に canonical inventory tool で再生成し、stale-path diff を閉じる。logs/log archive は保持 |
| tool docs | `documents/tools/README.md` の二つの Python bullet | canonical Rust bullet 一つへ統合 |
| tool docs | `tools/README.md` の nested checker bullet | 削除し Rust CLI entry を唯一の案内にする |
| provenance | `documents/tools/repo-local-tool-imports.md` の nested checker rows | 現行 capability から削除または retired record に明示更新 |

`tools/agent_tools/check_algorithm_config_partition.py` と
`tests/agent_tools/test_check_algorithm_config_partition.py` は retire set に含めない。
この二つは同じ design owner を参照するが、config partition の独立した public route と
finding schema を持つためである。

## Migration order / implementation trace

一つの cutover change set 内で、次の依存順を守る。

1. **Contract freeze:** この matrix と finding/artifact schema を実装 packet の入力に
   し、old Python test の全 inline fixture case と Rust embedded test case を named
   fixture row に写す。追加する fixture は pass、extra/missing public surface、
   `__all__`、protocol-only import、callable failure、child ownership、local child config、
   Problem-only、concrete Info、legacy stopping、malformed syntax、allowlisted/non-allowlisted
   protocol-only import、fnmatch glob/non-glob/repeatable `--exclude` を含む。
2. **Rust owner first:** `python_algorithm_contract.rs` と AST extractor を実装し、
   Rust unit test は each finding kind、Rust integration/CLI test は text/JSON、exit
   status、root-relative path/line、malformed syntax を readback する。fixture source は
   `tests/fixtures/python_algorithm_contract/` に `.py.fixture` で保存し、CLI integration の
   単一 loader が一時 tree に `.py` として materialize する。CLI integration は
   `rust/agent-canon/tests/python_algorithm_contract_cli.rs` を canonical test surface
   とする。
3. **Route cutover:** `run_all_checks.sh` が Rust CLI を一度だけ呼ぶようにし、catalog の
   Rust entry を CI owner にする。public と nested の二つを別々に起動する期間を作らない。
4. **Docs/catalog/mirror:** tool docs、repo-local provenance、runtime surface mirror、
   dependency headers を single owner へ更新する。Rust entry の docs/tests は design
   owner、tool docs、Rust source/test、fixture path を指す。
5. **PR #471 clean-baseline gate:** PR #471 の log-surface owner fix が統合された後、
   clean baseline から `python3 tools/agent_tools/log_surface_inventory.py --root . --check --baseline documents/runtime/log-surface-inventory.json`
   を先に実行する。この時点で既に存在する added/removed/stale record は、algorithm
   checker consolidation の差分に混ぜず、PR #471 の owner または inventory owner に
   `pre-existing log-surface drift` の別 owner blocker として識別する。baseline の再生成、
   stale record の削除、runtime logs、hook JSONL、eval report、log archive の削除・truncate・
   retention 変更は、この pre-existing drift の解決策として行わない。
6. **Retire:** parity fixture と static grep readback が pass した同じ change set で、
   二つの Python implementation/test、catalog id、Python CI call を削除する。旧
   command が見つかることを pass condition にしない。
7. **Final inventory regeneration/check:** PR #471 の clean-baseline gate が pass（または
   pre-existing drift を別 owner blocker として明示）した後、かつ Rust route cutover と
   Python implementation/test retirement が完了した後に、初めて
   `python3 tools/agent_tools/log_surface_inventory.py --root . --output /tmp/python-algorithm-contract-log-surface.current.json`
   で current inventory を生成する。algorithm route retirement の意図した差分だけを
   canonical baseline に反映するため、`python3 tools/agent_tools/log_surface_inventory.py --root . --output documents/runtime/log-surface-inventory.json`
   で再生成し、`python3 tools/agent_tools/log_surface_inventory.py --root . --check --baseline documents/runtime/log-surface-inventory.json`
   を再実行して stale-path closure を pass にする。この final inventory 操作も inventory
   projection だけを更新し、runtime logs、hook JSONL、eval report、log archive branch の
   file は削除・truncate・retention変更しない。pre-existing drift blocker が未解決なら、
   baseline を上書きせず別 owner blocker のまま停止する。
8. **Closeout:** `cargo fmt --check`、`cargo test --manifest-path rust/agent-canon/Cargo.toml`,
   CLI fixture matrix、`tools/bin/agent-canon python-algorithm-contract-check --format json`,
   catalog/dependency checks、final log-surface regeneration/check、
   `tools/bin/agent-canon docs check` を実行し、旧 path/id が source、catalog、CI、docs、
   runtime mirror に残っていないことを確認する。

## Static / fixture readback acceptance

実装 wave の acceptance は次を全て満たすこととする。

- 全 fixture row で、old Python の supported semantic finding が canonical Rust
  `kind/path/line/subject/detail` に一対一で対応し、Rust 固有の既存 finding も一つずつ
  残る。Python checker の二重実行による duplicate は出ない。
- pass fixture は exit 0、contract/syntax failure は exit 1、CLI/internal failure は
  exit 2。text と JSON の status、module count、finding count、parse error count が一致する。
- malformed syntax は malformed+valid mixed fixture で exact relative path、1-based line、
  JSON/text 共通の exact detail `parseable`、および path/line ordering を readback でき、
  他の valid module の findings を捨てない。
- `__all__`、extra public definition、callable `Algorithm`、nested ownership、concrete
  `Info`、Problem/local-config exemption の各 fixture が target rule を直接 exercise する。
- local `child.InitializeConfig()` fixture は親 `InitializeConfig` 不足を報告せず、
  `config.<field>` fixture は同じ contract class を報告する。protocol-only import は
  non-allowlisted が exact one finding、allowlisted が zero finding/zero module になる。
- `--exclude 'pkg/generated/*.py'`、`--exclude '*_generated.py'`、および directory-shaped
  `--exclude '*/generated'` などの fnmatch glob と repeatable exclude の union が、
  Python/Rust の files、modules、findings count で一致する。directory-shaped row では
  `generated/a.py` が残る。
- `git grep` による static closure で retired Python path、old catalog id、old CI invocation、
  old output prefix が production/docs/catalog/runtime mirror に残らないことを確認する。
- PR #471 owner fix 統合後の clean baseline check を先に通し、pre-existing drift は別
  owner blocker として識別する。その後、Python implementation/test retirement 後に
  `documents/runtime/log-surface-inventory.json` を final regeneration し、
  `log_surface_inventory.py --check --baseline ...` が pass する。stale inventory record
  は owner route で閉じるが、runtime logs/log archive/eval logs は一切削除しない。
- Rust formatter/test、catalog validation、dependency-header/graph validation、docs check
  の failure は downscope せず、該当 owner surface に修復を戻す。

この設計更新は実装を含まない。実装後に親 template の `vendor/agent-canon` pin/root
view を更新する作業は、AgentCanon source change が統合された後の別の
`agentcanon_structure_followup` として扱う。
