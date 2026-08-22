// @dependency-start
// contract implementation
// responsibility Owns semantic-index CLI parse dispatch, usage, process output, and integer exit mapping.
// upstream design ../../../../documents/design/semantic-index-module-boundaries.md approved semantic-index owner boundary
// upstream implementation ../main.rs canonical Rust CLI dispatch caller
// downstream implementation ../../../../tools/catalog.yaml command catalog and public command source
// downstream implementation ../../../../tools/agent_tools/review_backlog_scan.sh process-level semantic-index behavior oracle
// @dependency-end

use super::args::{parse_args, OutputFormat, ParsedArgs, SemanticCommand};
use super::eval::{compare_providers, eval_output, run_eval};
use super::pipeline::{build_index, embed_existing_nodes};
use super::query::{context_pack, responsibility_tree, search_index};
use super::relations::{discourse_relations, natural_relations, similar_pairs, thin_docs};
use super::report::{
    print_context_pack_results, print_discourse_relation_results, print_eval_summary,
    print_natural_relation_results, print_output_eval_summary, print_provider_compare_summary,
    print_responsibility_tree_results, print_search_results, print_similar_results,
    print_thin_docs_results, responsibility_tree_report_json, write_pretty_report, write_report,
};
use super::storage::{
    persist_discourse_relations, persist_natural_relations, persist_pairs, persist_thin_docs,
    temporary_db_identity, DiscourseRelationRow, NaturalRelationRow, SimilarPairRow, ThinDocRow,
};
use serde_json::Value;

pub(super) fn run(args: &[String]) -> i32 {
    let configured = match configure_runtime_root(args) {
        Ok(value) => value,
        Err(error) => return fail("CLI", error),
    };
    match parse_args(&configured, temporary_db_identity) {
        Ok(ParsedArgs::Command(SemanticCommand::Help)) => {
            print_usage();
            0
        }
        Ok(ParsedArgs::Build(build_args)) => match build_index(&build_args) {
            Ok(stats) => {
                println!("SEMANTIC_INDEX_BUILD=ok");
                println!("SEMANTIC_INDEX_DB={}", stats.db.display());
                println!("SEMANTIC_INDEX_FILES={}", stats.files);
                println!("SEMANTIC_INDEX_NODES={}", stats.nodes);
                println!("SEMANTIC_INDEX_EMBEDDINGS={}", stats.embeddings);
                0
            }
            Err(error) => fail("BUILD", error),
        },
        Ok(ParsedArgs::Search(search_args)) => match search_index(&search_args) {
            Ok(results) => {
                print_search_results(&search_args, &results);
                0
            }
            Err(error) => fail("SEARCH", error),
        },
        Ok(ParsedArgs::ContextPack(context_args)) => match context_pack(&context_args) {
            Ok(cells) => {
                print_context_pack_results(&context_args, &cells);
                0
            }
            Err(error) => fail("CONTEXT_PACK", error),
        },
        Ok(ParsedArgs::ResponsibilityTree(tree_args)) => match responsibility_tree(&tree_args) {
            Ok(report) => {
                let value = responsibility_tree_report_json(&report);
                if let Some(path) = &tree_args.report {
                    if let Err(error) = write_pretty_report(path, &value) {
                        return fail("RESPONSIBILITY_TREE_REPORT", error);
                    }
                }
                print_responsibility_tree_results(&tree_args, &report, &value);
                if tree_args.check_directory_coverage && report.coverage.status != "pass" {
                    1
                } else {
                    0
                }
            }
            Err(error) => fail("RESPONSIBILITY_TREE", error),
        },
        Ok(ParsedArgs::EmbedProvider(embed_args)) => match embed_existing_nodes(&embed_args) {
            Ok(stats) => {
                println!("SEMANTIC_INDEX_EMBED_PROVIDER=ok");
                println!("SEMANTIC_INDEX_DB={}", stats.db.display());
                println!("SEMANTIC_INDEX_NODES={}", stats.nodes);
                println!("SEMANTIC_INDEX_EMBEDDINGS={}", stats.embeddings);
                0
            }
            Err(error) => fail("EMBED_PROVIDER", error),
        },
        Ok(ParsedArgs::Similar(similar_args)) => match similar_pairs(&similar_args) {
            Ok(results) => {
                let rows = results
                    .iter()
                    .map(|pair| SimilarPairRow {
                        left_node_id: pair.left.node_id,
                        right_node_id: pair.right.node_id,
                        score: pair.score,
                        rank: pair.rank,
                    })
                    .collect::<Vec<_>>();
                if let Err(error) = persist_pairs(&similar_args, &rows) {
                    fail("SIMILAR_PERSIST", error)
                } else {
                    print_similar_results(&similar_args, &results);
                    0
                }
            }
            Err(error) => fail("SIMILAR", error),
        },
        Ok(ParsedArgs::ThinDocs(thin_docs_args)) => match thin_docs(&thin_docs_args) {
            Ok(results) => {
                let rows = results
                    .iter()
                    .map(|candidate| {
                        let best_match = candidate.best_match.as_ref();
                        ThinDocRow {
                            node_id: candidate.node.node_id,
                            thin_score: candidate.thin_score,
                            rank: candidate.rank,
                            action: candidate.action.clone(),
                            reasons: candidate.reasons.clone(),
                            total_lines: candidate.metrics.total_lines,
                            meaningful_lines: candidate.metrics.meaningful_lines,
                            link_lines: candidate.metrics.link_lines,
                            wrapper_phrase_hits: candidate.metrics.wrapper_phrase_hits,
                            link_density: candidate.metrics.link_density,
                            target_node_id: best_match.map(|neighbor| neighbor.node.node_id),
                            target_score: best_match.map(|neighbor| neighbor.score),
                        }
                    })
                    .collect::<Vec<_>>();
                if let Err(error) = persist_thin_docs(&thin_docs_args, &rows) {
                    fail("THIN_DOCS_PERSIST", error)
                } else {
                    print_thin_docs_results(&thin_docs_args, &results);
                    0
                }
            }
            Err(error) => fail("THIN_DOCS", error),
        },
        Ok(ParsedArgs::NaturalRelations(relation_args)) => {
            match natural_relations(&relation_args) {
                Ok(results) => {
                    let rows = results
                        .iter()
                        .map(|relation| NaturalRelationRow {
                            left_node_id: relation.left.node_id,
                            right_node_id: relation.right.node_id,
                            similarity_score: relation.similarity_score,
                            left_is_kind_of_right_score: relation.left_is_kind_of_right_score,
                            right_is_kind_of_left_score: relation.right_is_kind_of_left_score,
                            relation_kind: relation.relation_kind.clone(),
                            rank: relation.rank,
                        })
                        .collect::<Vec<_>>();
                    if let Err(error) = persist_natural_relations(&relation_args, &rows) {
                        fail("NATURAL_RELATIONS_PERSIST", error)
                    } else {
                        print_natural_relation_results(&relation_args, &results);
                        0
                    }
                }
                Err(error) => fail("NATURAL_RELATIONS", error),
            }
        }
        Ok(ParsedArgs::DiscourseRelations(discourse_args)) => {
            match discourse_relations(&discourse_args) {
                Ok(results) => {
                    let rows = results
                        .iter()
                        .map(|relation| DiscourseRelationRow {
                            left_node_id: relation.left.node_id,
                            right_node_id: relation.right.node_id,
                            similarity_score: relation.similarity_score,
                            connective_profile: relation.connective_profile.clone(),
                            relation_family: relation.relation_family.clone(),
                            relation_schema: relation.relation_schema.clone(),
                            surface_phrase: relation.surface_phrase.clone(),
                            inverse_surface_phrase: relation.inverse_surface_phrase.clone(),
                            surface_order: relation.surface_order.clone(),
                            logical_direction: relation.logical_direction.clone(),
                            naturalness_score: relation.naturalness_score,
                            inverse_naturalness_score: relation.inverse_naturalness_score,
                            direction_confidence: relation.direction_confidence,
                            ambiguity: relation.ambiguity.clone(),
                            gap_flags: relation.gap_flags.clone(),
                            rank: relation.rank,
                        })
                        .collect::<Vec<_>>();
                    if let Err(error) = persist_discourse_relations(&discourse_args, &rows) {
                        fail("DISCOURSE_RELATIONS_PERSIST", error)
                    } else {
                        print_discourse_relation_results(&discourse_args, &results);
                        0
                    }
                }
                Err(error) => fail("DISCOURSE_RELATIONS", error),
            }
        }
        Ok(ParsedArgs::Eval(eval_args)) => match run_eval(&eval_args) {
            Ok(report) => {
                if let Some(path) = &eval_args.report {
                    if let Err(error) = write_report(path, &report) {
                        return fail("EVAL_REPORT", error);
                    }
                }
                if eval_args.format == OutputFormat::Json {
                    println!("{}", report);
                } else {
                    print_eval_summary(&report);
                }
                if report.get("semantic_index_eval").and_then(Value::as_str) == Some("pass") {
                    0
                } else {
                    1
                }
            }
            Err(error) => fail("EVAL", error),
        },
        Ok(ParsedArgs::CompareProviders(compare_args)) => match compare_providers(&compare_args) {
            Ok(report) => {
                if let Some(path) = &compare_args.report {
                    if let Err(error) = write_report(path, &report) {
                        return fail("COMPARE_PROVIDERS_REPORT", error);
                    }
                }
                if compare_args.format == OutputFormat::Json {
                    println!("{}", report);
                } else {
                    print_provider_compare_summary(&report);
                }
                0
            }
            Err(error) => fail("COMPARE_PROVIDERS", error),
        },
        Ok(ParsedArgs::EvalOutput(eval_output_args)) => match eval_output(&eval_output_args) {
            Ok(report) => {
                if let Some(path) = &eval_output_args.report {
                    if let Err(error) = write_report(path, &report) {
                        return fail("OUTPUT_EVAL_REPORT", error);
                    }
                }
                if eval_output_args.format == OutputFormat::Json {
                    println!("{}", report);
                } else {
                    print_output_eval_summary(&report);
                }
                if report
                    .get("semantic_index_output_eval")
                    .and_then(Value::as_str)
                    == Some("pass")
                {
                    0
                } else {
                    1
                }
            }
            Err(error) => fail("OUTPUT_EVAL", error),
        },
        Err(message) => {
            eprintln!("SEMANTIC_INDEX_CLI=fail");
            eprintln!("SEMANTIC_INDEX_CLI_ERROR={message}");
            print_usage();
            2
        }
    }
}

fn configure_runtime_root(args: &[String]) -> Result<Vec<String>, String> {
    let mut configured = Vec::with_capacity(args.len());
    let mut index = 0;
    while index < args.len() {
        if args[index] == "--runtime-root" {
            let value = args
                .get(index + 1)
                .ok_or_else(|| "--runtime-root requires a value".to_string())?;
            if value.trim().is_empty() {
                return Err("--runtime-root must not be empty".to_string());
            }
            std::env::set_var(crate::runtime_boundary::RUNTIME_ROOT_ENV, value);
            index += 2;
        } else {
            configured.push(args[index].clone());
            index += 1;
        }
    }
    Ok(configured)
}

fn fail(scope: &str, message: String) -> i32 {
    eprintln!("SEMANTIC_INDEX_{scope}=fail");
    eprintln!("SEMANTIC_INDEX_ERROR={message}");
    1
}

fn print_usage() {
    eprintln!(
        "usage: agent-canon semantic-index <build|embed-provider|search|context-pack|responsibility-tree|similar|merge-candidates|thin-docs|natural-relations|discourse-relations|eval|compare-providers|eval-output> [options]"
    );
    eprintln!("build: --root <repo-root> [--runtime-root path] [--include path] [--db path] [--provider name] [--model name] [--dim N] [--embedding-url URL] [--embedding-batch N]");
    eprintln!("embed-provider: --root <repo-root> --db path --provider name --model name [--dim N] [--embedding-url URL] [--embedding-batch N]");
    eprintln!("search: (--query <text>|--query-file path|--query-stdin) [--root repo] [--db path] [--provider name] [--model name] [--embedding-url URL] [--top-k N] [--format text|json|jsonl]");
    eprintln!("context-pack: (--query <text>|--query-file path|--query-stdin) [--root repo] [--db path] [--provider name] [--model name] [--embedding-url URL] [--max-cells N] [--max-cell-chars N] [--max-total-chars N] [--format text|json|jsonl]");
    eprintln!("responsibility-tree: [--root repo] [--include path] [--db path] [--provider name] [--model name] [--dim N] [--node-kind document|section|block|all] [--check-directory-coverage] [--report path] [--format text|json|jsonl]");
    eprintln!("similar: [--root repo] [--db path] [--min-score S] [--cross-file-only] [--format text|json|jsonl]");
    eprintln!(
        "merge-candidates: [--root repo] [--db path] [--min-score S] [--format text|json|jsonl]"
    );
    eprintln!("thin-docs: [--root repo] [--db path] [--min-thin-score S] [--min-neighbor-score S] [--top-k N] [--format text|json|jsonl]");
    eprintln!("natural-relations: [--root repo] [--db path] [--min-similarity S] [--min-kind-of-score S] [--top-k N] [--format text|json|jsonl]");
    eprintln!("discourse-relations: [--root repo] [--db path] [--profile general|experiment-report|methods-protocol|academic-argument|refactor-design] [--min-naturalness S] [--window N] [--top-k N] [--format text|json|jsonl]");
    eprintln!("eval: --fixture <fixture-dir> [--db path] [--report path] [--format text|json]");
    eprintln!("compare-providers: --db path [--query-file path] [--left-provider name] [--right-provider name] [--left-dim N] [--right-dim N] [--report path]");
    eprintln!("eval-output: [--merge-candidates path] [--thin-docs path] [--search path] [--report path] [--format text|json]");
}
