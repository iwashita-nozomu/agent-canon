# Closeout Gate

- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

## Gate Status

- verifier_status: pending
- auditor_status: pending
- required_reviews_complete: no
- validation_complete: no
- request_contract_complete: no
- commit_created: no
- push_completed: no
- user_completion_report: locked

## Unlock Rule

`user_completion_report` を `unlocked` にしてよいのは、少なくとも次を満たしたあとだけです。

- verifier_status: pass
- auditor_status: resolved
- required_reviews_complete: yes
- validation_complete: yes
- request_contract_complete: yes
- commit_created: yes
- push_completed: yes

## Evidence

<!-- Record the exact verification artifact, review artifacts, commit, branch, and push evidence used to close the run. -->
