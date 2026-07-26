mod graph;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() >= 2 && args[1] == "graph" {
        std::process::exit(graph::run(&args[2..]));
    }
}
