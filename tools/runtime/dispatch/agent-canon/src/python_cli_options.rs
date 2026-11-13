// @dependency-start
// contract implementation
// responsibility Resolves unique Python argparse-compatible prefixes for native long options.
// downstream implementation compare_agent_run_paths.rs preserves its run-path CLI option contract
// downstream implementation docs.rs preserves duplicate-design CLI option compatibility
// @dependency-end

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum LongOptionError<'a> {
    Unrecognized,
    Ambiguous(Vec<&'a str>),
}

/// Resolve one long-option spelling or its unique argparse-style prefix.
pub(crate) fn resolve_long_option_prefix<'a, T: Copy>(
    value: &str,
    options: &'a [(&'a str, T)],
) -> Result<T, LongOptionError<'a>> {
    if let Some((_, name)) = options.iter().find(|(option, _)| *option == value) {
        return Ok(*name);
    }
    let matches = options
        .iter()
        .filter(|(option, _)| option.starts_with(value))
        .map(|(option, name)| (*option, *name))
        .collect::<Vec<_>>();
    match matches.as_slice() {
        [(_, name)] => Ok(*name),
        [] => Err(LongOptionError::Unrecognized),
        _ => Err(LongOptionError::Ambiguous(
            matches.iter().map(|(option, _)| *option).collect(),
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn complete_option_wins_while_short_shared_prefix_stays_ambiguous() {
        let options = [
            ("--source-mutation", 0),
            ("--source-mutation-evidence", 1),
            ("--source-mutation-capability-json", 2),
        ];
        assert_eq!(
            resolve_long_option_prefix("--source-mutation", &options),
            Ok(0)
        );
        assert!(matches!(
            resolve_long_option_prefix("--source", &options),
            Err(LongOptionError::Ambiguous(_))
        ));
        assert_eq!(
            resolve_long_option_prefix("--source-mutation-e", &options),
            Ok(1)
        );
        assert_eq!(
            resolve_long_option_prefix("--missing", &options),
            Err(LongOptionError::Unrecognized)
        );
    }
}
