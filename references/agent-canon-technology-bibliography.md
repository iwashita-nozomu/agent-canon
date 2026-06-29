<!--
@dependency-start
contract reference
responsibility Catalogs external technical references for AgentCanon implementation and runtime surfaces.
upstream design README.md reference capture and source-record requirements.
upstream design ../agents/workflows/workflow-references.md workflow-level bibliography index.
upstream design ../documents/semantic_index.md semantic-index tool design and generated-cache policy.
upstream design ../documents/search-coordination.md coordinated search and bounded context-pack policy.
upstream design ../documents/dependency-manifest-design.md dependency header and dependency graph policy.
downstream design ../documents/tools/README.md documents operator-facing tool entrypoints.
downstream design ../documents/tools/lean_capability_matrix.md records Lean feature routing adopted from bibliography sources.
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

## Reader Map

Use this bibliography to answer which external technical sources support
AgentCanon runtime, LLM agent, semantic-index, discourse, proof, compiler,
static-analysis, environment, security, and documentation choices. Start with
Coverage Map to find the source cluster, then read the matching topical section.
The out-of-scope section prevents related sources from being treated as adopted
implementation authority.

## Coverage Map

- Agent runtime: `$openai-docs` source route for OpenAI/Codex product docs and
  API reference, Model Context Protocol, JSON-RPC.
- LLM agent methods: chain-of-thought, ReAct, Reflexion, Toolformer, Tree of
  Thoughts.
- Semantic indexing and discourse structure: Transformer/BERT/SBERT,
  vector-space search, provider-compatible embeddings via `$openai-docs` API
  reference route, discourse relations/connectives, SQLite, llama.cpp, GGUF,
  SHA-256, Rust crates used by the Rust CLI.
- Formal proof support: Lean 4, mathlib theorem search, LeanSearch,
  Isabelle/Sledgehammer, CoqHammer, and informal-to-formal proof sketching.
- Compiler and proof graph tooling: LLVM Kaleidoscope, MLIR, CompCert,
  CakeML, Lean metaprogramming, and code property graphs.
- Static/dependency analysis: Python AST, Pyright, Ruff, pytest, program
  dependence graphs, code property graphs.
- Runtime and operations: Rust/Cargo, Dev Containers, GitHub Actions, Git
  worktrees/submodules.
- Security and documentation: GitHub secret scanning, Gitleaks, TruffleHog,
  detect-secrets, CommonMark, markdownlint, YAML, TOML.

## Agent Runtime And Tool Protocols

| Source | URL or DOI | AgentCanon surface | Claim used | Limitations | Decision |
| --- | --- | --- | --- | --- | --- |
| `$openai-docs` source route | host-provided Codex skill | OpenAI/Codex docs, model selection, model upgrades, prompt guidance, Codex manual, and OpenAI API reference | Current OpenAI/Codex product facts are resolved through the Codex manual helper, Docs MCP, official-domain web alternate route, and bundled alternate route references owned by `$openai-docs`. | The route is host-provided rather than vendored in AgentCanon; record task-local run evidence when a current product claim changes repo policy. | Adopt as the only source route for OpenAI/Codex product docs and API reference. Do not add individual OpenAI doc URLs or alternate route copies here. |
| Model Context Protocol latest specification | <https://modelcontextprotocol.io/specification/latest> | External connector boundaries | MCP standardizes connections between LLM applications, external data, and tools using JSON-RPC style messages and capability negotiation. | The latest URL redirected to version 2025-11-25 on access date; version-specific behavior must be pinned in implementation docs. | Adopt as the source for optional connector boundary and security notes. |
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
| `$openai-docs` API reference route | host-provided Codex skill | Provider-compatible vector request/response shape | Embedding request/response shape is checked through `$openai-docs` Docs MCP / API reference when the OpenAI-compatible provider contract changes. | Local llama.cpp endpoints may not match every OpenAI schema feature. | Adopt as compatibility route, not as requirement to use remote OpenAI. |
| FIPS 180-4 Secure Hash Standard | <https://csrc.nist.gov/pubs/fips/180-4/upd1/final> | SHA-256 content hashing in Rust CLI tools | FIPS 180-4 specifies SHA-1 and SHA-2 hash algorithms including SHA-256. | NIST notes FIPS 180-4 is planned for revision; keep hash usage conventional, not cryptographic-policy-heavy. | Adopt for SHA-256 naming and standards reference. |
| rusqlite crate docs | <https://docs.rs/rusqlite/latest/rusqlite/> | Rust SQLite access | `rusqlite` is an ergonomic Rust wrapper around SQLite. | Crate version in AgentCanon is pinned separately in `Cargo.toml` and `Cargo.lock`. | Adopt for Rust SQLite API reference. |
| serde_json crate docs | <https://docs.rs/serde_json/latest/serde_json/> | JSON and JSONL output from Rust tools | `serde_json` serializes/deserializes JSON and provides untyped `Value` support. | Docs describe latest crate; validate against locked version for API changes. | Adopt for JSON output implementation reference. |
| sha2 crate docs | <https://docs.rs/sha2/latest/sha2/> | Rust SHA-256 implementation | `sha2` provides SHA-2 hash functions in Rust. | Cryptographic security depends on correct use and dependency version. | Adopt for implementation dependency reference. |
| yaml-rust2 crate docs | <https://docs.rs/yaml-rust2/latest/yaml_rust2/> | Rust catalog-backed YAML parsing | `yaml-rust2` parses YAML into structured `Yaml` values used by the Rust skill router. | Docs describe latest crate; validate parser behavior against the locked version in `Cargo.lock`. | Adopt for `agents/skills/catalog.yaml` routing metadata parsing. |

## Discourse Relations, Connectives, And Structure Planning

Access date for this section: 2026-06-10.

| Source | URL or DOI | AgentCanon surface | Claim used | Limitations | Decision |
| --- | --- | --- | --- | --- | --- |
| Annotation Graphs as a Framework for Multidimensional Linguistic Data Analysis | <https://aclanthology.org/W99-0301/> | Prose Reasoning Graph source-span annotation model | Annotation graphs support multiple typed annotation layers anchored to linguistic data. | General linguistic annotation model, not a prose-quality evaluator. | Use as direct support for text anchors plus layered derived annotations. |
| Rhetorical Structure Theory: Toward a Functional Theory of Text Organization | <https://doi.org/10.1515/text.1.1988.8.3.243> | `semantic-index discourse-relations`, `structure-planning`, writing skills | Text organization can be modeled through relations between text spans; this supports treating paragraphs/blocks as ordered discourse units. | RST analysis is richer and more hierarchical than the MVP edge scorer. | Use as background for span-to-span discourse edge representation, not as a full RST parser. |
| Using Linguistic Phenomena to Motivate a Set of Coherence Relations | <https://doi.org/10.1080/01638539409544883> | Discourse connective profiles and transition evidence | Cue phrases/connectives provide linguistic evidence for coherence relations. | Cue phrases are not sufficient on their own, and relation inventories differ by theory. | Adopt the split between relation primitives and surface connective evidence. |
| The Penn Discourse TreeBank 2.0 | <https://aclanthology.org/L08-1093/> | Prose Reasoning Graph discourse argument contract | PDTB-style discourse relations have text-span arguments, sense labels, and attribution, supporting typed graph edges over source units. | PDTB is an annotation resource, not an authoring workflow or total document-quality metric. | Use as evidence for span-grounded relation objects and relation provenance. |
| Penn Discourse Treebank 3.0 Annotation Manual | <https://catalog.ldc.upenn.edu/docs/LDC2019T05/PDTB3-Annotation-Manual.pdf> | Discourse relation schema names and connective-pair handling | PDTB-style annotation grounds relations in explicit connectives and their senses, including contingency cause reason/result variants. | The manual is an annotation guide, not a lightweight repo-review algorithm. | Use as source for keeping `because` / `therefore` surface variants separate from logical relation schemas. |
| Logics of Conversation | <https://www.research.ed.ac.uk/en/publications/logics-of-conversation/> | Future graph and coherence-relation interpretation | SDRT treats discourse interpretation as relations over discourse segments with logical/pragmatic constraints. | The book-level theory is more formal than the MVP tool and is not implemented wholesale. | Register as related prior art for later graph optimization and relation consistency checks. |
| A Dependency Perspective on RST Discourse Parsing and Evaluation | <https://aclanthology.org/J18-2001/> | Prose Reasoning Graph canonical graph and projection-view design | RST discourse structure can be recast from constituency trees into dependency-style relations. | RST-specific; dependency conversion is not a general authoring algorithm. | Use as support for not treating macro constituency spans as canonical source nodes. |
| eRST: Enhanced Rhetorical Structure Theory | <https://gucorpling.org/erst/> | Prose Reasoning Graph graph overlays and relation signals | eRST adds secondary graph edges and explicit signals over RST-style units, addressing tree limitations and relation evidence. | Richer than MVP and source is a project page plus paper reference. | Use as support for secondary edges, signal provenance, and graph projections. |
| Centering: A Framework for Modeling the Local Coherence of Discourse | <https://aclanthology.org/J95-2003/> | Prose Reasoning Graph reader-state and local-coherence projections | Centering models local discourse coherence through attentional state across utterances. | Centering does not define full-document macrostructure or argument support. | Use as background for reader-state projection fields and local coherence diagnostics. |
| Toward a Model of Text Comprehension and Production | <https://eric.ed.gov/?id=EJ191792> | Prose Reasoning Graph projection-view design | Kintsch and van Dijk distinguish detailed text meaning from condensed gist generated through comprehension processes. | Cognitive macrostructure theory is not a direct graph schema. | Use as rationale for deriving macro prose views from source text evidence instead of storing them as source truth. |
| Text Tiling: Segmenting Text into Multi-paragraph Subtopic Passages | <https://aclanthology.org/J97-1003/> | Prose Reasoning Graph projection segmentation | TextTiling treats multi-paragraph subtopic passages as derived segmentation over source text evidence. | Lexical cohesion alone is insufficient for argument, evidence, and reader-state structure. | Use as a segmentation prior for projection views, not as a replacement for typed discourse relations. |
| Summarizing Scientific Articles: Experiments with Relevance and Rhetorical Status | <https://aclanthology.org/J02-4002/> | Prose Reasoning Graph scholarly move projections | Argumentative zoning supports sentence/span-level rhetorical status labels for scientific articles. | Role labels do not encode support, prerequisite, or discourse-relation edges by themselves. | Use as background for derived scholarly phase projections, not as canonical source nodes. |

## Formal Proof Support

Access date for this section: 2026-06-01.

| Source | URL or DOI | AgentCanon surface | Claim used | Limitations | Decision |
| --- | --- | --- | --- | --- | --- |
| Lean Language Reference | <https://lean-lang.org/doc/reference/latest/> | `documents/tools/lean_capability_matrix.md`, `$formal-proof-workflow` | Lean has a reference manual for tactics, simplification, `grind`, Lake, and the kernel-oriented proof-checking model. | The latest manual can describe features newer than a pinned proof package; verify with the local `lean-toolchain`. | Use as the primary route for Lean feature availability and tactic semantics. |
| Theorem Proving in Lean 4 | <https://lean-lang.org/theorem_proving_in_lean4/> | `$formal-proof-workflow`, `formal_proof.py` Lean target scaffolds | Lean 4 has a documented theorem-proving workflow covering propositions, tactics, interaction, induction, structures, and type classes. | Tutorial material does not imply that a user claim is already formalized or easy to prove. | Use Lean 4 as the default target stub language when no project-specific prover is mandated. |
| Mathlib documentation | <https://leanprover-community.github.io/mathlib4_docs/Mathlib> | `documents/tools/lean_capability_matrix.md`, Mathlib-backed proof attempts | Mathlib exposes a broad module and tactic surface including algebra, order, tactic, and theorem-search-adjacent modules. | Documentation volume is large and search-sensitive; import availability depends on the pinned Mathlib revision. | Use for existing theorem/tactic discovery before hand-rolling lemmas. |
| Searching for Theorems in Mathlib | <https://leanprover-community.github.io/blog/posts/searching-for-theorems-in-mathlib/> | Existing proof search stage and query packet | Mathlib theorem search should combine documentation search, natural-language search tools, type/signature search, community archive search, and in-editor tactics such as `exact?`. | Search tools are heuristic and can miss a theorem if names, statement shape, or imports differ. | Require existing proof search before new formalization for likely-library claims. |
| Loogle | <https://loogle.lean-lang.org/> | Existing proof search stage and `lean_capability_matrix.md` theorem-search route | Loogle searches Lean and Mathlib definitions and theorems by name/type/pattern and can be used from editor integrations. | Requires accurate symbols or patterns; it is a search aid, not a checker. | Use for type/signature-driven theorem discovery. |
| LeanSearch | <https://leansearch.net/> | Optional mathlib natural-language search target | LeanSearch provides natural-language query over Mathlib4 theorem/definition content. | The service may collect search terms and feedback; it is not a checker. | Include as an optional web target with privacy caveat. |
| Aesop tactic docs | <https://leanprover-community.github.io/mathlib4_docs/Aesop/Frontend/Tactic.html> | `$formal-proof-workflow`, `documents/tools/lean_capability_matrix.md` | `aesop` searches using registered rules, and `aesop?` can print a suggested proof script. | The found proof still has to check; broad goals can search too much or fail. | Use Aesop as bounded automation for structural and routine proof obligations. |
| Aesop repository | <https://github.com/leanprover-community/aesop> | `$formal-proof-workflow`, proof-environment setup | Aesop is a Lean 4 white-box proof-search tactic. | It is not a substitute for domain-specific hypotheses or analytic estimates. | Keep as the automation source for routine proof search. |
| Lake reference | <https://lean-lang.org/doc/reference/latest/Build-Tools-and-Distribution/Lake/> | `lean_proof_env.py`, topic-local Lean packages | Lake configures/builds Lean code and manages dependencies. | Lake behavior still depends on the pinned Lean version and package manifest. | Use Lake as the standard build/dependency route for proof packages. |
| Hammering Away: A User's Guide to Sledgehammer for Isabelle/HOL | <https://isabelle.in.tum.de/dist/Isabelle2025-2/doc/sledgehammer.pdf> | Isabelle target route and automation boundary | Sledgehammer applies ATPs, SMT solvers, and Isabelle proof methods to current goals and can return Isabelle proof text that reconstructs in Isabelle. | Works on loaded context and selected facts; generated proof text may need reconstruction/minimization and can fail. | Use as source for assistant-backed search/reconstruction, with checker log as authority. |
| CoqHammer | <https://coqhammer.github.io/> | Coq/Rocq target route and automation caveats | CoqHammer integrates external automated theorem provers and reconstruction tactics for Coq/Rocq. | It is limited on some fragments and does not try induction by design; SMT-heavy goals may need SMTCoq instead. | Include Coq/Rocq route when project context selects it, not as universal default. |
| Draft, sketch, and prove: Guiding formal theorem provers with informal proofs | <https://doi.org/10.17863/CAM.94959> | Natural-language proof sketch to formal obligation workflow | Informal proofs can guide formal proof sketches and automated prover search, but success is measured by checked formal proof. | Research setting does not guarantee arbitrary natural-language formalization. | Shape workflow as sketch -> obligations -> checker, never direct proof assertion. |

## Compiler, IR, And Proof-Graph Tooling

Access date for this section: 2026-06-12.

| Source | URL or DOI | AgentCanon surface | Claim used | Limitations | Decision |
| --- | --- | --- | --- | --- | --- |
| LLVM Kaleidoscope: Code generation to LLVM IR | <https://llvm.org/docs/tutorial/MyFirstLanguageFrontend/LangImpl03.html> | `jit_canonical_ir.py` backend trace design | A compiler pipeline can lower a source-root representation toward backend IR and preserve inspectable intermediate artifacts. | Tutorial language and not a verified compiler. | Keep the proof entrypoint on the JIT root and record StableHLO/backend artifacts. |
| MLIR Toy Tutorial | <https://mlir.llvm.org/docs/Tutorials/Toy/> | `jit_canonical_ir.py` thin operational IR | MLIR uses dialects to preserve operation structure while enabling analysis, verification, transforms, and later lowering. | MLIR is an SSA compiler framework; AgentCanon should not import MLIR machinery or TableGen complexity. | Treat StableHLO-derived records as thin operational evidence and keep mathematical labels in the theorem graph. |
| CompCert verified compiler documentation | <https://compcert.org/doc/> | Future compiler-correctness validation for JIT-canonical lowering | CompCert's correctness claim is semantic equivalence between source and generated assembly, proved in Coq. | AgentCanon's current lowering emits evidence catalogs only; it is not yet a verified compiler theorem. | Do not claim semantic preservation for `jit-ir-to-lean` until a pass-correctness proof or validator exists. |
| CakeML publications | <https://cakeml.org/publications.html> | Future multi-pass proof layering for JIT-canonical IR | CakeML records verified compiler work through multiple intermediate languages and proof stages. | Source counts and pass structure are version-sensitive; project and paper versions can differ. | Leave room for multiple JIT/IR/backend evidence layers and per-layer invariants instead of one permanent graph schema. |
| The verified CakeML compiler backend | <https://www.cambridge.org/core/journals/journal-of-functional-programming/article/verified-cakeml-compiler-backend/E43ED3EA740D2DF970067F4E2BB9EF7D> | Future compiler-correctness and backend proof design | The CakeML backend explains how intermediate languages, semantics, and proofs fit across compiler phases. | HOL4/CakeML organization is not a Lean template. | Keep generated code graph files separate from theorem/proof graph modules, with stable references between them. |
| Lean Language Reference: Syntax, macros, elaborators, and terms | <https://lean-lang.org/doc/reference/latest/> | Generated Lean artifact design | Lean parses syntax, expands macros, elaborates terms, and checks core terms in the kernel. | Metaprogramming APIs and generated syntax are Lean-version-sensitive. | Emit ordinary exposed Lean definitions/records before adding custom syntax or elaborators. |
| Modeling and Discovering Vulnerabilities with Code Property Graphs | <https://www.ieee-security.org/TC/SP2014/papers/ModelingandDiscoveringVulnerabilitieswithCodePropertyGraphs.pdf> | Theorem graph traversal validation | Code property graphs unify AST, control flow, and dependence information into a graph that can be traversed. | CPG is analysis evidence, not a theorem or semantic-preservation proof. | Keep operational evidence and theorem dependency edges distinct; reachability evidence is not a mathematical equation by itself. |

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
