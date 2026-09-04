# Workflow Index
<!--
@dependency-start
contract workflow
responsibility Provides the thin reader index for AgentCanon task families and public Skills.
upstream design ../TASK_WORKFLOWS.md task-family reader map
upstream design ../skills/README.md public Skill index
upstream implementation ../task_catalog.yaml workflow-family registry
downstream design workflow-references.md bibliography index
@dependency-end
-->

`agents/workflows/` contains this index and the bibliography at
`workflow-references.md`. Executable task procedures live in the public Skills;
task-family activation and stage topology live in `agents/task_catalog.yaml`.
The index is a reader aid, not another procedure or policy source.

## Task family index

| Task family | Primary Skill or owner | Registry |
| --- | --- | --- |
| bounded repository change | `$codex-task-workflow` | `agents/task_catalog.yaml` |
| comprehensive repository delivery | `$comprehensive-development` | `agents/task_catalog.yaml` |
| refactor and responsibility cleanup | `$refactor-loop`, `$code-cleanup`, `$responsibility-cleanup` | `agents/task_catalog.yaml` |
| research-driven change | `$research-workflow` | `agents/task_catalog.yaml` |
| experiment and benchmark run | `$experiment-lifecycle`, `$experiment-review` | `agents/task_catalog.yaml` |
| iterative improvement backlog | `$adaptive-improvement-loop` | `agents/task_catalog.yaml` |
| academic or paper writing | `$academic-writing`, `$paper-writing` | `agents/task_catalog.yaml` |
| slides and presentations | `$slides` | `agents/task_catalog.yaml` |
| integration and branch delivery | `$integration`, `$pr-processing` | `agents/task_catalog.yaml` |
| AgentCanon source update | `$agent-canon-update`, `$agent-canon-bootstrap` | `agents/task_catalog.yaml` |
| private learning and runtime feedback | `$agent-learning`, `$agent-log-analysis` | `agents/task_catalog.yaml` |
| token/resource-aware routing | `$tokens` | `agents/task_catalog.yaml` |

## Related indexes

- Task-family and stage reader: [`../TASK_WORKFLOWS.md`](../TASK_WORKFLOWS.md)
- Public Skill index: [`../skills/README.md`](../skills/README.md)
- External and local bibliography: [`workflow-references.md`](workflow-references.md)
