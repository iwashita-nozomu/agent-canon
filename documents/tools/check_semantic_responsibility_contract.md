<!--
@dependency-start
contract design
responsibility Documents check_semantic_responsibility_contract.py operator usage.
upstream design ../design/semantic-responsibility-contract.md semantic responsibility contract schema
upstream implementation ../../tools/agent_tools/check_semantic_responsibility_contract.py validates schema, identity, and references
downstream implementation ../../tests/agent_tools/test_check_semantic_responsibility_contract.py validates focused checker behavior
@dependency-end
-->

# check_semantic_responsibility_contract.py

この checker は、semantic responsibility contract の schema、identity、参照先を
fail-closed で検証します。template の shape と run-local task instance の必須値、
delta action、obligation の一次 owner、supporting property/role、existing-test の
contract から removal witness までの chain、hard-edge closure を確認します。

checker は schema/identity/reference validator に限定されます。責務の分割を数値評価せず、
class、module、file の形を要求せず、数値的な調整値、件数、境界条件を算出しません。
semantic judgement と owner allocation は design review と
active design packet が所有します。

## Command

```bash
python3 tools/agent_tools/check_semantic_responsibility_contract.py \
  --root . \
  --template templates/documents/semantic-responsibility-contract.template.toml \
  --instance reports/agents/<run-id>/semantic_responsibility_contract.toml \
  --artifact-root reports/agents/<run-id>
```

template fixture と task fixture を同時に確認する場合は `--template` と `--instance`
を追加します。参照は repository-relative `repo:` または artifact-root-relative
`artifact:` locator だけを受け付け、絶対 path、traversal、symlink を拒否します。

## Evidence boundary

- `documents/design/semantic-responsibility-contract.md` が policy の正本です。
- `templates/documents/semantic-responsibility-contract.template.toml` は空の再利用可能な
  instance shape です。
- populated instance は current run bundle にだけ置き、active design packet の
  `source_refs` から参照します。
- property の妥当性、設計上の grouping、実装が obligation を満たすかの判断はこの
  checker の出力ではなく、primary owner の evidence と review gate が行います。
