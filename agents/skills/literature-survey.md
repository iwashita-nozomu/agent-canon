# literature-survey
<!--
@dependency-start
contract skill
responsibility Documents literature-survey for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design prose-reasoning-graph.md prose graph claim and evidence handoff overlay
@dependency-end
-->


## Reader Map

- Purpose: structures paper search, prior-art mapping, contradictory-source
  hunting, and reusable bibliography output.
- Use When: a task needs external research, literature comparison, source
  reliability checks, or citation-ready survey evidence.
- Section path: Purpose, Use When, and Core References set scope; Mandatory
  Checklist and Canonical Flow are operational rules; Deliverable Shape and
  Boundary define output limits.
- Boundary: do not turn search notes into accepted claims without source
  evaluation and contradiction handling.

## Purpose

文献調査、先行研究整理、関連資料比較を、検索、選定、反証候補の抽出まで含めて扱います。

## Use When

- 研究や設計の前提になる外部資料を集めたい
- survey、代表論文、比較論文、仕様資料を整理したい
- ある主張を支える資料と弱める資料の両方を見たい
- baseline、評価指標、failure mode の根拠を文献ベースで決めたい
- `references/` や `documents/notes/` に残す索引を作りたい

## Core References

- [agents/skills/research-workflow.md](research-workflow.md)
- [agents/workflows/workflow-references.md](../workflows/workflow-references.md)
- [references/README.md](../../references/README.md)
- 必要なら対象 topic の既存 `documents/notes/themes/*.md`
- 必要なら対象 topic の既存 `documents/notes/experiments/*.md`

## Mandatory Checklist

- 外部検索、PDF取得、citation lookup の前に、同じ source / claim が既存の
  `references/`、`documents/notes/`、`documents/`、topic report にないか確認します。
  既存 note がある場合は更新または参照し、並行する正本を増やしません。
- 問いに合う source mix を選び、使える場合は primary / official sources を優先します。
  source type（peer-reviewed paper、preprint、vendor doc、blog など）と関連性を確かめます。
  claim の位置づけに影響する制限・反証資料も探し、source の直接の記述と解釈を分けます。
  複数資料の一致を根拠にするときは、claimごとに転載・共通原典・同じdataや実験への依存を確認します。
  同じ根拠の再掲を独立した裏付けに数えず、結論に影響する依存関係と未確認の範囲を
  既存source noteに残します。
- 回答、report、design に使う source は tracked note / packet に残し、URL / DOI、
  access date、利用した claim、limitation、保存 artifact の場所を記録します。
  重要な claim は [原文位置](../../references/README.md#source-passages) へ結び付けます。
  query、探索日、採否理由は、探索範囲や除外判断を再現するのに
  必要な場合に残します。
- `prose-reasoning-graph` handoff がある場合は、その unsupported-claim や
  citation/evidence gaps を検索・採否判断の候補として使います。

## Canonical Flow

問いと必要な範囲を決め、既存 source record を調べてから検索します。資料の
信頼性・problem/data/hardware setting・主張への適用可能性を比較し、採用する claim と
それを弱める条件を区別します。必要なら `Known` / `Contested` / `Open` に整理し、
使った source を追跡できる形で記録します。query pack、除外一覧、全 source の要約は、
検索規模や依頼に必要な場合だけ作ります。

用語や探索先が未確定なら、問いに必要な資料へ探索を広げます。用語・人・venues・引用経路から原文へ
たどる必要がある場合は、[Imozuru handoff](README.md#installed-external-skill-handoffs) を source discovery に
使います。返された locator と原文はここで評価・記録し、結論を変え得る代替説明も確認します。
終了時には、必要な根拠が揃った、重要な未確認点が残る、追加探索で新しい資料が
得られなくなった、のどれが判断の根拠かを示します。未探索・アクセス不能・探索した
範囲で見つからなかった状態を区別します。

引用・翻訳・要約・自分の解釈を区別し、引用の文字照合に加えて前後文脈・適用条件・
反証を評価します。ユーザーが求めた要約や結論を返し、探索資料を求められた場合は
未解決点と読む箇所を示します。

DOI が既知の source では、host shell から
[Crossref CSL lookup](../../tools/analysis/documents/literature_metadata.sh) を使って書誌
metadata を取得できます。bare DOI を渡し、stdout の raw CSL JSON と stderr の
provenance block を別々に保存します。provider、DOI、source URL、取得時刻、および raw
artifact の場所は既存の [reference note guidance](../../references/README.md)
に従って記録します。metadata は source identity の手掛かりであり、claim の根拠や採否を
自動で決めるものではありません。source の確認、contrary evidence、adoption/exclusion は
この Skill が引き続き扱います。

## Deliverable Shape

選んだ source と結論を読める最小の形で示します。`Question`、`Scope`、
`Adopted Source Claims`、`Known` / `Contested` / `Open` などは有用な例であり、
使っていない資料区分や主張のために空欄を作りません。検索・除外の詳細は、採否判断に
影響する場合だけ添えます。

## Boundary

- 研究全体の outer loop は `research-workflow` を使います
- 実験結果の批判的評価は critical review を使います
- reader-facing な report の確認は report review を使います
- repo-wide な workflow や review policy の外部根拠索引は [agents/workflows/workflow-references.md](../workflows/workflow-references.md) に残します。
  この索引は source bibliography であり、検索手順の正本ではありません。
