# Workflow References
<!--
@dependency-start
contract workflow
responsibility Documents Workflow References for this repository.
upstream design README.md workflow catalog
downstream design ../../references/agent-canon-technology-bibliography.md catalogs implementation/runtime technical sources
@dependency-end
-->


この文書は、workflow、review、agent system、report policy を設計するときに参照した外部資料の索引です。
外部根拠で repo-wide な手順を更新した場合は、この文書へ出典を追記します。

## Reader Map

- This document owns the bibliography and source-route index for workflow, review, agent runtime, reporting, writing, memory, and academic-writing policy.
- The local index and OpenAI / Codex source route come first; later clusters group external sources by runtime customization, system development, research/reporting, writing, agent learning, and academic logic / notation.
- Use this file when a workflow claim needs source grounding or when adding an external basis to a repo-wide procedure.
- For chunked reading, choose the source cluster matching the claim under review and avoid treating this bibliography as a replacement for current official-doc routes such as `$openai-docs`.

## Local Reference Indexes

- [AgentCanon Technology Bibliography](../../references/agent-canon-technology-bibliography.md)
  - AgentCanon implementation/runtime surfaces such as Codex runtime,
    semantic-index, local LLM, SQLite, Rust tooling, dependency analysis,
    devcontainer, GitHub Actions, scanners, Markdown, YAML, and TOML.

## OpenAI And Codex Product Source Route

OpenAI / Codex の現在情報、API reference、model selection、model upgrade、
prompt-upgrade guidance、Codex manual、official-domain web alternate route は、この
workflow bibliography で個別 URL や alternate route 文書として二重管理しない。
host-provided `$openai-docs` skill を正本 route とし、そこが指定する
Codex manual helper、Docs MCP、latest-model page、bundled alternate route
references を使う。

OpenAI / Codex の current product evidence をこの文書へ source-by-source で
追加してはいけない。role TOML の実装値を変更するときも、根拠確認は
`$openai-docs` で行い、この bibliography には local decision artifact だけを
残す。

## Agent Runtime And Customization

- [Git - git-worktree Documentation](https://git-scm.com/docs/git-worktree)
  - worktree ごとに snapshot を持つ、という運用整理の根拠です。
- [About Git subtree merges - GitHub Docs](https://docs.github.com/en/get-started/using-git/about-git-subtree-merges)
  - legacy subtree repo を submodule-first 運用へ移行する互換整理だけに使う参考です。新規 template / 派生 repo の標準 path は AgentCanon submodule pin です。
- [Events that trigger workflows - GitHub Docs](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows)
  - fork-like PR で repository secrets が渡らない場合があることの根拠です。
- [Secrets - GitHub Docs](https://docs.github.com/en/actions/concepts/security/secrets)
  - `AGENT_CANON_REPO_TOKEN` のような secret は workflow 側で明示的に渡す必要があること、最小権限の根拠です。
- [REST API endpoints for deploy keys - GitHub Docs](https://docs.github.com/en/rest/deploy-keys/deploy-keys)
  - private AgentCanon を PAT ではなく read-only deploy key で読む alternate route の根拠です。

## System Development, Security, Release, And Operations

- [Managing the Development of Large Software Systems](https://faculty.washington.edu/hazeline/misc/reserve/royce_waterfall.pdf)
  - waterfall の段階列、設計先行、文書化、pilot model、test planning の基礎資料です。
- [NIST SP 800-218, Secure Software Development Framework (SSDF)](https://csrc.nist.gov/pubs/sp/800/218/final)
  - secure development workflow、review gate、supply-chain 観点の根拠です。
- [NIST SP 800-218A, Secure Software Development Practices for Generative AI and Dual-Use Foundation Models](https://csrc.nist.gov/pubs/sp/800/218/a/final)
  - AI を含む実装で、secure development practice を SDLC 全体へ広げる根拠です。
- [Microsoft Security Development Lifecycle](https://www.microsoft.com/en-us/securityengineering/sdl)
  - security review と設計段階の gate を考えるときの基礎資料です。
- [OWASP Threat Modeling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html)
  - threat-model workflow を追加するときの根拠です。
- [NASA Systems Engineering Handbook](https://ntrs.nasa.gov/api/citations/20170001761/downloads/20170001761.pdf)
  - stakeholder expectations、requirements、design、verification、validation、transition を分ける根拠です。
- [Sequential Development Approach - SEBoK](https://sebokwiki.org/wiki/Sequential_Development_Approach)
  - phase-based sequential development と、初期段階の限定的 iteration の整理に使った資料です。
- [Technical Reviews and Audits - SEBoK](https://sebokwiki.org/wiki/Technical_Reviews_and_Audits)
  - decision gate と readiness review の根拠です。
- [Design and Code Inspections to Reduce Errors in Program Development](https://web.mit.edu/16.35/OldFiles/www/lecturenotes/fagan.pdf)
  - 独立 reviewer を役割分離して立てる inspection process の根拠です。
- [What to look for in a code review | eng-practices](https://google.github.io/eng-practices/review/reviewer/looking-for.html)
  - local consistency、既存コードとの整合、関連文書更新確認を review 観点へ入れる根拠です。
- [NASA Software Engineering Handbook](https://swehb.nasa.gov/download/attachments/76447896/SWE_Handbook_Rel0.1_March2011_RevC.pdf?api=v2)
  - 既存 software reuse と設計・review の統制を強めるときの参考資料です。
- [Google SRE: Release Engineering](https://sre.google/sre-book/release-engineering/)
  - release-readiness と deploy 前後の運用手順の根拠です。
- [Google SRE Workbook: Postmortem Culture](https://sre.google/workbook/postmortem-culture/)
  - postmortem と failure follow-up workflow の根拠です。
- [Microsoft Azure Well-Architected: Safe deployment practices](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/safe-deployments)
  - safe deployment と rollback readiness の観点を入れる根拠です。

## Research, Experiment, And Reporting

- [Ten Simple Rules for Reproducible Computational Research](https://doi.org/10.1371/journal.pcbi.1003285)
  - reproducibility review の基礎です。
- [Best Practices for Scientific Computing](https://doi.org/10.1371/journal.pbio.1001745)
  - scientific-computing review の基礎です。
- [Good Enough Practices in Scientific Computing](https://doi.org/10.1371/journal.pcbi.1005510)
  - 軽量な研究運用と実務レベルの checklist の根拠です。
- [Guidance on Reproducibility for Papers Using Computational Tools](https://www.nature.com/articles/d41586-022-00563-z)
  - computational paper の再現性要件を整理するときに使う資料です。
- [Implementing Code Review in the Scientific Workflow](https://doi.org/10.12688/f1000research.27137.2)
  - scientific workflow に code review を組み込む根拠です。
- [Ten Simple Rules for Better Figures](https://doi.org/10.1371/journal.pcbi.1003833)
  - report-review の figure / table 観点の基礎です。
- [Benchmarking in Optimization: Best Practice and Open Issues](https://doi.org/10.48550/arXiv.2007.03488)
  - benchmark fairness と比較条件の根拠です。
- [Benchmarking Crimes: An Emerging Threat in Systems Security](https://doi.org/10.48550/arXiv.1801.02381)
  - benchmarking anti-pattern review の根拠です。
- [Artifact Review and Badging - Current | ACM](https://www.acm.org/publications/policies/artifact-review-and-badging-current)
  - artifact readiness と公開物 completeness の根拠です。
- [The FAIR Guiding Principles for scientific data management and stewardship](https://doi.org/10.1038/sdata.2016.18)
  - FAIR-style data review の根拠です。
- [NeurIPS Paper Checklist](https://nips.cc/public/guides/PaperChecklist)
  - experiment report と claim review の根拠です。
- [REFORMS: Consensus-based Recommendations for Machine-learning-based Science](https://reforms.cs.princeton.edu/)
  - ML-science reporting review の根拠です。

## Long-Form Writing And Revision

- [Reverse Outlining | John S. Knight Institute for Writing in the Disciplines](https://knight.as.cornell.edu/reverse-outlining)
  - `summary statement` を固定し、reverse outline で focus / logic gap を見る構成の根拠です。
- [Creating a Roadmap | Purdue OWL](https://owl.purdue.edu/owl/graduate_writing/documents/creating-a-roadmap.pdf)
  - roadmap、sentence outline、skeleton outline、section purpose を先に固定する構成の根拠です。
- [Writing with Feedback on a Manuscript | Purdue OWL](https://owl.purdue.edu/owl/general_writing/the_writing_process/feedback/editor-reviewer_feedback.html)
  - feedback を checklist 化して priority 順に処理する revision 運用の根拠です。
- [Higher Order Concerns | Purdue OWL](https://owl.purdue.edu/owl/subject_specific_writing/professional_technical_writing/prioritizing_your_concerns_for_effective_business_writing/index.html)
  - line edit より先に focus、purpose、organization を直す review 順序の根拠です。
- [Scannable content - Microsoft Style Guide](https://learn.microsoft.com/en-us/style-guide/scannable-content/)
  - reader path が長い文書に navigation、parallel structure、short paragraph、lead-with-what-matters を入れる根拠です。

## Agent Learning, Memory, And Philosophy

- [Reflective Equilibrium - Stanford Encyclopedia of Philosophy](https://plato.stanford.edu/entries/reflective-equilibrium/)
  - 個別判断と一般原則を相互調整し、task observation と agent philosophy を往復させる根拠です。
- [The Reflective Practitioner: How Professionals Think in Action - WorldCat](https://search.worldcat.org/title/The-reflective-practitioner-how-professionals-think-in-action/oclc/1166337782)
  - reflection-in-action と実践後 reflection を task retrospective として残す根拠です。
- [Situated Knowledges - New Materialism Almanac](https://newmaterialism.eu/almanac/s/situated-knowledges.html)
  - knowledge を立場、実践、scope と結び付け、observation に source / evidence / confidence を付ける根拠です。原典は Haraway (1988), Feminist Studies, DOI `10.2307/3178066` です。
- [About Value Sensitive Design - VSD Lab](https://vsdesign.org/vsd/)
  - human values を design process 全体で扱い、user preference、agent philosophy、repo rule の出所を分ける根拠です。
- [The Extended Mind - Clark and Chalmers](https://fitelson.org/prosem/clark_chalmers.pdf)
  - notes を agent の外部記憶、language-based scaffold として扱い、毎回読む runtime note にする根拠です。
- [Deep Reinforcement Learning from Human Preferences](https://arxiv.org/abs/1706.03741)
  - human feedback を preference 更新へ使う発想の技術的参考です。この repo では raw feedback ではなく evidence 付き observation を明示的に記録します。

## Academic Writing, Logic, And Notation

- [Rhetorical Structure Theory: Toward a Functional Theory of Text Organization](https://doi.org/10.1515/text.1.1988.8.3.243)
  - discourse span relation and text organization background for structure-planning.
- [Using Linguistic Phenomena to Motivate a Set of Coherence Relations](https://doi.org/10.1080/01638539409544883)
  - cue phrase / connective evidence for coherence relation design.
- [Penn Discourse Treebank 3.0 Annotation Manual](https://catalog.ldc.upenn.edu/docs/LDC2019T05/PDTB3-Annotation-Manual.pdf)
  - explicit connective and relation-sense background for separating surface
    phrases such as `therefore` / `because` from relation primitives.
- [Ten simple rules for structuring papers](https://doi.org/10.1371/journal.pcbi.1005619)
  - central contribution、context-content-conclusion、logical flow、results を claim sequence として積む構成、複数 reader からの feedback を得る process の根拠です。
- [Flow in Scholarly Writing | Purdue OWL](https://owl.purdue.edu/owl/graduate_writing/documents/Flow-Handout.pdf)
  - sentence / paragraph / text の flow、support、transition、alignment を review 観点に入れる根拠です。
- [Creating a Roadmap | Purdue OWL](https://owl.purdue.edu/owl/graduate_writing/documents/creating-a-roadmap.pdf)
  - roadmap、section purpose、skeleton outline を先に固定する根拠です。
- [Writing with Feedback on a Manuscript | Purdue OWL](https://owl.purdue.edu/owl/general_writing/the_writing_process/feedback/editor-reviewer_feedback.html)
  - feedback を checklist 化し、higher-order concerns から revision する根拠です。
- [Writing Tips | MIT OpenCourseWare](https://ocw.mit.edu/courses/8-06-quantum-physics-iii-spring-2016/e498e7c0d2db9e3846df12bfdac3e10e_MIT8_06S16_TermPaper.pdf)
  - scientific writing で ambiguity を避け、導入した quantity を明確に定義する根拠です。

## Related Local Canon

- [references/README.md](../../references/README.md)
  - reference 置き場の入口です。
- [agents/workflows/research-workflow.md](research-workflow.md)
  - 研究・実験改造の正本です。
- [agents/workflows/implementation-waterfall-workflow.md](implementation-waterfall-workflow.md)
  - 実装パスのウォーターフォール正本です。
- [documents/experiment-critical-review.md](../../documents/experiment-critical-review.md)
  - 批判的レビュー観点の正本です。
- [references/workflow/implementation-waterfall.md](../../references/workflow/implementation-waterfall.md)
  - 実装ウォーターフォール化の文献メモです。
- [agents/README.md](../README.md)
  - agent canon の入口です。

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/agent_tools/check_convention_compliance.py` and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps workflow prohibitions, convention tool gates, and skill-routing hooks mechanically checked instead of relying on prompt memory.
