<!--
@dependency-start
responsibility Catalogs external technical references for AgentCanon implementation and runtime surfaces.
upstream design README.md reference capture and source-record requirements.
upstream design ../agents/workflows/workflow-references.md workflow-level bibliography index.
upstream design ../documents/semantic_index.md semantic-index tool design and generated-cache policy.
upstream design ../documents/search-coordination.md coordinated search and bounded context-pack policy.
upstream design ../documents/dependency-manifest-design.md dependency header and dependency graph policy.
upstream design ../documents/local-llm-responsibility-analysis.md local LLM advisory boundary.
downstream design ../documents/tools/README.md documents operator-facing tool entrypoints.
downstream design ../tools/README.md documents root tool inventory.
downstream implementation ../rust/agent-canon/src/semantic_index.rs implements the semantic vector cache.
downstream implementation ../rust/agent-canon/src/local_llm.rs routes local LLM and llama.cpp tools.
downstream implementation ../tools/agent_tools/reference_materializer.py materializes consulted external sources.
@dependency-end
-->

# AgentCanon Technology Bibliography

Access date: 2026-05-24.

This bibliography registers external sources consulted for AgentCanon
technology choices. It complements
`agents/workflows/workflow-references.md`: that file remains the workflow and
review-method bibliography, while this file maps implementation/runtime
surfaces to primary technical sources.

Artifact retention decision for this pass: no external PDFs, HTML snapshots,
SQLite databases, model files, vector caches, or local LLM outputs were
retained in the tracked tree. The durable retained artifact is this source
record.

## Coverage Map

- Agent runtime: Codex `AGENTS.md`, custom subagents, slash commands, OpenAI
  embeddings, Model Context Protocol, JSON-RPC.
- LLM agent methods: chain-of-thought, ReAct, Reflexion, Toolformer, Tree of
  Thoughts.
- Semantic indexing: Transformer/BERT/SBERT, vector-space search, SQLite,
  llama.cpp, GGUF, SHA-256, Rust crates used by the Rust CLI.
- Static/dependency analysis: Python AST, Pyright, Ruff, pytest, program
  dependence graphs, code property graphs.
- Runtime and operations: Rust/Cargo, Dev Containers, GitHub Actions, Git
  worktrees/submodules.
- Security and documentation: GitHub secret scanning, Gitleaks, TruffleHog,
  detect-secrets, CommonMark, markdownlint, YAML, TOML.

## Agent Runtime And Tool Protocols

| Source | URL or DOI | AgentCanon surface | Claim used | Limitations | Decision |
| --- | --- | --- | --- | --- | --- |
| Codex AGENTS.md guide | <https://developers.openai.com/codex/guides/agents-md> | Root and nested agent instruction files | Codex discovers and merges `AGENTS.md` instruction files by scope, with closer files overriding broader guidance. | Product behavior can change; re-check before changing runtime policy. | Adopt as the source for AGENTS entrypoint and scope-order claims. |
| Codex subagents guide | <https://developers.openai.com/codex/subagents> | `.codex/agents/*.toml`, subagent routing, spawn-budget policy | Custom agents are standalone TOML profiles; subagents are specialized parallel agents and should be explicitly requested because they consume more tokens. | Runtime availability and model names are product-specific. | Adopt for role TOML shape, explicit subagent routing, and cost caution. |
| Codex slash commands | <https://developers.openai.com/codex/cli/slash-commands> | `/plan`, `/agent`, `/review`, `/mcp`, `/status`, `/compact` workflow guidance | Codex CLI exposes planning, agent thread, review, MCP, status, and compaction controls as slash commands. | CLI command set may vary by runtime version. | Adopt for plan-mode and runtime-control references. |
| OpenAI embeddings API | <https://api.openai.com/v1/embeddings> | OpenAI-compatible embedding provider and local embedding endpoint parity | The embeddings endpoint creates embedding vectors representing input text. | API schema and model availability can change; local endpoints only mimic a subset. | Adopt as compatibility target for `openai-compatible-embedding`. |
| Model Context Protocol latest specification | <https://modelcontextprotocol.io/specification/latest> | MCP inventory, repo MCP tools, context/resource/tool boundaries | MCP standardizes connections between LLM applications, external data, and tools using JSON-RPC style messages and capability negotiation. | The latest URL redirected to version 2025-11-25 on access date; version-specific behavior must be pinned in implementation docs. | Adopt as the source for MCP protocol boundary and security notes. |
| MCP tools specification | <https://modelcontextprotocol.io/docs/concepts/tools> | Tool listing, tool result, structured output contracts | MCP servers expose model-invocable tools with input schemas, results, and security considerations around human control. | Fetched page redirected to version 2025-06-18; keep version drift visible. | Adopt for tool schema/output validation language. |
| MCP resources specification | <https://modelcontextprotocol.io/docs/concepts/resources> | Resource/context handoff concepts | MCP resources provide context/data surfaces separate from tools. | Version-specific page; use only for broad design mapping unless pinned. | Adopt for resource-vs-tool separation. |
| MCP prompts specification | <https://modelcontextprotocol.io/docs/concepts/prompts> | Reusable prompt/workflow surfaces | MCP prompts define reusable prompt templates and workflows that clients can surface. | Version-specific page; not all clients expose prompts. | Adopt for prompt-template terminology. |
| JSON-RPC 2.0 specification | <https://www.jsonrpc.org/specification> | MCP message-shape background | JSON-RPC defines a lightweight remote procedure call protocol with request, response, and error objects. | MCP adds its own schema and capability layers. | Adopt as background for MCP transport vocabulary. |

## LLM Agent Methods

| Source | URL or DOI | AgentCanon surface | Claim used | Limitations | Decision |
| --- | --- | --- | --- | --- | --- |
| Chain-of-Thought Prompting Elicits Reasoning in Large Language Models | <https://arxiv.org/abs/2201.11903> | Planning, reasoning, and test-design prompt patterns | Intermediate reasoning demonstrations can improve complex reasoning in sufficiently capable language models. | CoT text is not proof of faithful internal reasoning and should not replace validation. | Use as background for explicit reasoning steps, with validation gates preserved. |
| ReAct: Synergizing Reasoning and Acting in Language Models | <https://arxiv.org/abs/2210.03629> | Agent workflows that interleave reasoning, tool use, and observations | Interleaving reasoning traces with actions lets agents gather external information and update plans. | ReAct-style traces can loop or overtrust observations without guardrails. | Use as basis for tool-observation workflow vocabulary. |
| Reflexion: Language Agents with Verbal Reinforcement Learning | <https://arxiv.org/abs/2303.11366> | Agent-learning and retrospective loops | Verbal feedback can be stored and reused to improve future agent behavior. | Feedback quality is task-dependent; memory must not become user preference without evidence. | Use as background for agent-side learning logs. |
| Toolformer: Language Models Can Teach Themselves to Use Tools | <https://arxiv.org/abs/2302.04761> | Tool-selection evals and routing repair | Models can learn when to call tools, what arguments to pass, and how to incorporate results. | Paper is about training-time self-supervision, not a guarantee for runtime agents. | Use as conceptual support for measured tool-selection evals. |
| Tree of Thoughts: Deliberate Problem Solving with Large Language Models | <https://arxiv.org/abs/2305.10601> | Plan alternatives, branch review, and escalation | Exploring multiple candidate "thought" units can improve tasks needing planning/search. | Expensive and not required for small deterministic edits. | Use as background for high-risk branching and review waves. |

## Semantic Indexing, Embeddings, And Local LLMs

| Source | URL or DOI | AgentCanon surface | Claim used | Limitations | Decision |
| --- | --- | --- | --- | --- | --- |
| Attention Is All You Need | <https://arxiv.org/abs/1706.03762> | Transformer/attention background for embedding models | Transformer attention is a foundation for modern language encoders and LLMs. | Architectural background only; AgentCanon does not inspect attention maps. | Use as theoretical background, not implementation authority. |
| BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding | <https://arxiv.org/abs/1810.04805> | Encoder-model background | Bidirectional Transformer pretraining supports transfer to language understanding tasks. | BERT itself is not the configured local model. | Use as encoder background for semantic embeddings. |
| Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks | <https://arxiv.org/abs/1908.10084> | Dense vector similarity and cosine-ranking rationale | Siamese/triplet fine-tuning can produce semantically meaningful sentence embeddings comparable with cosine similarity. | Candidate quality depends on model/domain and threshold tuning. | Use as main paper reference for sentence-level semantic vectors. |
| A Vector Space Model for Automatic Indexing | <https://doi.org/10.1145/361219.361220> | Deterministic vector baseline and TF-IDF-style search | Vector representations and similarity ranking are a classic information retrieval basis. | Classic lexical vector space is not equivalent to neural embeddings. | Use as background for deterministic lexical-vector providers. |
| SQLite database file format | <https://www.sqlite.org/fileformat.html> | Semantic-index SQLite cache layout and generated DB policy | SQLite stores database state in a main database file and may use rollback or WAL files during transactions. | Low-level format details are not an API contract for application logic. | Use for generated cache and artifact-retention policy. |
| SQLite write-ahead logging | <https://www.sqlite.org/wal.html> | Semantic-index publish/locking behavior | WAL mode records committed changes in a separate log and supports readers with a stable end mark. | AgentCanon currently publishes completed temporary DBs rather than relying on repo-local WAL artifacts. | Use to explain SQLite sidecar files and why DB caches are ignored. |
| llama.cpp HTTP server README | <https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md> | `llama-server-embedding` and OpenAI-compatible local endpoint | llama.cpp server exposes OpenAI-compatible chat, responses, and embeddings routes, with CPU/GPU options. | README tracks `master`; pin versions in installer/tests when reproducibility matters. | Adopt as operational source for local embedding server support. |
| GGUF format documentation | <https://github.com/ggml-org/ggml/blob/master/docs/gguf.md> | Local model artifact handling and ignored model files | GGUF stores models for inference with ggml-based executors and is designed for extensibility. | Format evolves with ggml; model licensing is separate. | Adopt for local model file terminology and ignore policy. |
| OpenAI embeddings API | <https://api.openai.com/v1/embeddings> | Provider-compatible vector request/response shape | Embedding responses contain vectors plus model and usage metadata. | Local llama.cpp endpoints may not match every OpenAI schema feature. | Adopt as compatibility reference, not as requirement to use remote OpenAI. |
| FIPS 180-4 Secure Hash Standard | <https://csrc.nist.gov/pubs/fips/180-4/upd1/final> | SHA-256 content hashing in Rust CLI tools | FIPS 180-4 specifies SHA-1 and SHA-2 hash algorithms including SHA-256. | NIST notes FIPS 180-4 is planned for revision; keep hash usage conventional, not cryptographic-policy-heavy. | Adopt for SHA-256 naming and standards reference. |
| rusqlite crate docs | <https://docs.rs/rusqlite/latest/rusqlite/> | Rust SQLite access | `rusqlite` is an ergonomic Rust wrapper around SQLite. | Crate version in AgentCanon is pinned separately in `Cargo.toml` and `Cargo.lock`. | Adopt for Rust SQLite API reference. |
| serde_json crate docs | <https://docs.rs/serde_json/latest/serde_json/> | JSON and JSONL output from Rust tools | `serde_json` serializes/deserializes JSON and provides untyped `Value` support. | Docs describe latest crate; validate against locked version for API changes. | Adopt for JSON output implementation reference. |
| sha2 crate docs | <https://docs.rs/sha2/latest/sha2/> | Rust SHA-256 implementation | `sha2` provides SHA-2 hash functions in Rust. | Cryptographic security depends on correct use and dependency version. | Adopt for implementation dependency reference. |

## Static Analysis, Dependency, And Code Intelligence

| Source | URL or DOI | AgentCanon surface | Claim used | Limitations | Decision |
| --- | --- | --- | --- | --- | --- |
| Python `ast` documentation | <https://docs.python.org/3/library/ast.html> | Python dependency scanner and structure-hash extractor | Python's `ast` module processes Python abstract syntax trees. | AST shape changes with Python versions; tests must cover supported runtime versions. | Adopt for AST-based scanner and normalized structure-hash references. |
| Pyright documentation | <https://microsoft.github.io/pyright/> | Python static type validation | Pyright is a standards-compliant static type checker for Python. | Pyright coverage is type-focused, not full behavioral verification. | Adopt for Python type-check gate references. |
| Ruff linter documentation | <https://docs.astral.sh/ruff/linter/> | Python lint gate | Ruff is a fast Python linter replacing several lint/import/docstring tools. | Rule selection is repo policy, not inherent Ruff behavior. | Adopt for lint gate references. |
| Ruff formatter documentation | <https://docs.astral.sh/ruff/formatter/> | Python formatting gate | Ruff formatter is a fast Python formatter and `ruff format` entrypoint. | Formatter choices are style policy; not all docs are Python docs. | Adopt for formatter references where used. |
| pytest documentation | <https://docs.pytest.org/en/stable/contents.html> | Python test execution and fixtures | pytest supports assertions, fixtures, parametrization, and test invocation patterns. | Passing tests do not prove untested behavior. | Adopt for Python test gate references. |
| The Program Dependence Graph and Its Use in Optimization | <https://doi.org/10.1145/24039.24041> | Dependency graph and edit-scope reasoning | Program dependence graphs make data and control dependencies explicit. | AgentCanon dependency headers are lighter-weight metadata, not full PDGs. | Use as conceptual background for dependency expansion. |
| Modeling and Discovering Vulnerabilities with Code Property Graphs | <https://www.ieee-security.org/TC/SP2014/papers/ModelingandDiscoveringVulnerabilitieswithCodePropertyGraphs.pdf> | Future strict structure/code graph analysis context | Code property graphs combine code representations for vulnerability/discovery queries. | AgentCanon does not yet implement CPG; do not overclaim. | Register as related prior art for future graph analysis. |
| SCIP code indexing format | <https://sourcegraph.com/blog/announcing-scip> | Code intelligence and precise index comparison | SCIP was introduced as a typed indexing format for code navigation data. | Sourcegraph-specific blog, not an AgentCanon dependency. | Register as related tool-design prior art only. |

## Runtime, Environment, CI, And Git Operations

| Source | URL or DOI | AgentCanon surface | Claim used | Limitations | Decision |
| --- | --- | --- | --- | --- | --- |
| The Rust Programming Language | <https://doc.rust-lang.org/stable/book/> | Rust CLI implementation | Rust provides systems-programming ergonomics with control over low-level details. | Language book is educational; API details belong in std/crate docs. | Adopt as Rust language background. |
| The Cargo Book | <https://doc.rust-lang.org/stable/cargo/> | Rust package/build/test workflow | Cargo is Rust's package manager and build tool documentation source. | Specific CLI behavior depends on installed toolchain. | Adopt for Cargo command references. |
| Development Containers specification | <https://github.com/devcontainers/spec> | `.devcontainer/devcontainer.json`, post-create, generated compose | Dev Containers define reproducible development environments through `devcontainer.json` and related metadata. | Implementations differ across VS Code, Codespaces, and CLI. | Adopt for devcontainer source policy. |
| GitHub Actions workflow syntax | <https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax> | `.github/workflows/*.yml` CI gates | GitHub Actions workflows are YAML files under `.github/workflows` defining jobs and triggers. | Hosted behavior can change; re-check for permissions/secrets semantics. | Adopt for CI workflow syntax references. |
| Git worktree documentation | <https://git-scm.com/docs/git-worktree> | Worktree lifecycle and scope files | Linked worktrees have private metadata under `$GIT_DIR/worktrees` and share repository data. | Git notes submodule support in multiple checkouts is incomplete. | Adopt for worktree lifecycle guardrails. |
| Git submodule documentation | <https://git-scm.com/docs/git-submodule> | Template-to-AgentCanon submodule pin workflow | Submodule initialization uses `.gitmodules` in the containing repository. | Submodule UX has edge cases; repo policy must add explicit pin evidence. | Adopt for submodule terminology and pin evidence. |

## Security, Supply Chain, And Public-Repo Hygiene

| Source | URL or DOI | AgentCanon surface | Claim used | Limitations | Decision |
| --- | --- | --- | --- | --- | --- |
| GitHub secret scanning docs | <https://docs.github.com/en/code-security/secret-scanning/introduction/about-secret-scanning> | Public repo protection and final secret-scan recommendations | GitHub secret scanning detects known secret types and scans Git history on supported repositories. | Feature availability depends on repository/account settings. | Adopt for GitHub-side protection notes. |
| Gitleaks repository | <https://github.com/gitleaks/gitleaks> | Local and CI secret scanning | Gitleaks is an open-source tool for finding secrets in Git repositories and worktrees. | Rule coverage and false positives require baseline policy. | Adopt as one scanner in public-repo audit flow. |
| TruffleHog repository | <https://github.com/trufflesecurity/trufflehog> | Verified secret scanning and history scanning | TruffleHog discovers, classifies, verifies, and analyzes leaked credentials across Git and other sources. | It is broader/heavier than simple regex scans and may require network for verification. | Adopt as complementary scanner for publicization audits. |
| detect-secrets repository | <https://github.com/Yelp/detect-secrets> | Baseline-based secret prevention | detect-secrets supports baselines to prevent new secrets while tracking existing findings. | Baseline quality depends on review and maintenance. | Adopt for baseline-style local guardrails. |
| NIST SSDF SP 800-218 | <https://csrc.nist.gov/pubs/sp/800/218/final> | Secure development and supply-chain review | SSDF provides secure software development practices across the lifecycle. | High-level framework, not a repo-specific checklist. | Keep as security workflow reference and link to workflow bibliography. |

## Documentation And Configuration Formats

| Source | URL or DOI | AgentCanon surface | Claim used | Limitations | Decision |
| --- | --- | --- | --- | --- | --- |
| CommonMark specification | <https://spec.commonmark.org/> | Markdown formatting and parser assumptions | CommonMark provides a strongly specified Markdown syntax. | GitHub Flavored Markdown adds extensions not covered by base CommonMark. | Adopt as base Markdown syntax reference. |
| markdownlint repository | <https://github.com/DavidAnson/markdownlint> | Markdown lint rules and docs checks | markdownlint provides configurable Markdown linting rules. | Repo-local rule selection determines actual enforcement. | Adopt for Markdown lint tooling reference. |
| YAML 1.2.2 specification | <https://yaml.org/spec/1.2.2/> | GitHub Actions, manifests, run bundles | YAML 1.2.2 defines the YAML data language and clarifies YAML 1.2. | Parser behavior can vary; CI must validate actual files. | Adopt for YAML format references. |
| TOML 1.0.0 specification | <https://toml.io/en/v1.0.0> | `.codex/agents/*.toml`, config files | TOML is a minimal configuration format mapping unambiguously to hash tables. | TOML format validity does not validate semantic role policy. | Adopt for TOML config format references. |

## Out-Of-Scope Or Related-Only Sources

- Workflow/review/research-process literature remains indexed in
  `agents/workflows/workflow-references.md`; this file only adds technology
  sources that map to AgentCanon implementation and runtime surfaces.
- No single source here authorizes deletion, document consolidation, dependency
  rewrites, or model-generated conclusions. AgentCanon tools remain advisory
  unless a strict checker, dependency analysis, and human/review gate agree.
