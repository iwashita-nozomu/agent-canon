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
