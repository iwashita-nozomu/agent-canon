pub(crate) fn run(args: &[String]) -> i32 {
    let Some(command) = args.first() else {
        return 2;
    };
    match command.as_str() {
        "build" => run_build(&args[1..]),
        "status" => run_status(&args[1..]),
        "query" => run_query(&args[1..]),
        "context" => run_context(&args[1..]),
        _ => 2,
    }
}
