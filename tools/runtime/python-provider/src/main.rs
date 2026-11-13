// @dependency-start
// contract implementation
// responsibility Calls existing external Python providers through PyO3's safe object APIs.
// upstream design ../../../../documents/design/rust-agent-tool-migration.md preserves consumer Python/JAX execution
// upstream reference https://github.com/PyO3/pyo3/blob/main/guide/src/python-from-rust.md Python object lifetime contract
// @dependency-end

use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict};
use serde_json::{json, Value};
use std::io::{self, Read};
use std::path::Path;

fn runtime(py: Python<'_>) -> PyResult<Value> {
    let sys = py.import("sys")?;
    Ok(json!({
        "implementation": "CPython",
        "version": sys.getattr("version")?.extract::<String>()?,
        "executable": sys.getattr("executable")?.extract::<String>()?,
    }))
}

fn pdf(py: Python<'_>, bytes: &[u8]) -> PyResult<Value> {
    let input = py
        .import("io")?
        .getattr("BytesIO")?
        .call1((PyBytes::new(py, bytes),))?;
    let reader = py.import("pypdf")?.getattr("PdfReader")?.call1((input,))?;
    let mut pages = Vec::new();
    for page in reader.getattr("pages")?.try_iter()? {
        let text = page?.call_method0("extract_text")?;
        pages.push(if text.is_none() {
            String::new()
        } else {
            text.extract::<String>()?
        });
    }
    Ok(json!({"status":"pass","method":"pypdf","text":pages.join("\n"),"runtime":runtime(py)?}))
}

fn trace(py: Python<'_>, path: &Path, symbol: &str) -> PyResult<Value> {
    let path = path.to_str().ok_or_else(|| {
        pyo3::exceptions::PyValueError::new_err("trace module path must be UTF-8")
    })?;
    let module = py.import("runpy")?.getattr("run_path")?.call1((path,))?;
    let globals = module.cast::<PyDict>()?;
    let value = globals.get_item(symbol)?.ok_or_else(|| {
        pyo3::exceptions::PyValueError::new_err(format!("missing trace symbol: {symbol}"))
    })?;
    let text = py
        .import("json")?
        .getattr("dumps")?
        .call1((value,))?
        .extract::<String>()?;
    let value: Value = serde_json::from_str(&text)
        .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))?;
    Ok(json!({"status":"pass","value":value,"runtime":runtime(py)?}))
}

fn main() {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let Some(command) = args.first().map(String::as_str) else {
        eprintln!(
            "usage: agent-canon-python-provider <pdf-extract|trace-json|runtime> [arguments]"
        );
        std::process::exit(2);
    };
    let result = match command {
        "runtime" if args.len() == 1 => Python::attach(runtime),
        "pdf-extract" if args.len() == 1 => {
            let mut bytes = Vec::new();
            if let Err(error) = io::stdin().read_to_end(&mut bytes) {
                eprintln!("{error}");
                std::process::exit(2);
            }
            Python::attach(|py| pdf(py, &bytes))
        }
        "trace-json" if args.len() == 3 => {
            Python::attach(|py| trace(py, Path::new(&args[1]), &args[2]))
        }
        _ => {
            eprintln!("unsupported provider command or arguments");
            std::process::exit(2);
        }
    };
    match result {
        Ok(value) => println!("{value}"),
        Err(error) => {
            println!("{}", json!({"status":"fail","error":error.to_string()}));
            std::process::exit(1);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn runtime_identifies_the_selected_interpreter() {
        let result = Python::attach(runtime).unwrap();
        assert_eq!(result["implementation"], "CPython");
        assert!(!result["version"].as_str().unwrap().is_empty());
    }

    #[test]
    fn trace_preserves_consumer_mapping_and_reports_missing_symbols() {
        let temporary = tempfile::tempdir().unwrap();
        let module = temporary.path().join("trace.py");
        std::fs::write(
            &module,
            "FORMAL_PROOF_TRACE = {'claim': '保持', 'steps': [1, 2], 'checked': True}\n",
        )
        .unwrap();
        let result = Python::attach(|py| trace(py, &module, "FORMAL_PROOF_TRACE")).unwrap();
        assert_eq!(
            result["value"],
            json!({"claim":"保持","steps":[1,2],"checked":true})
        );
        assert!(Python::attach(|py| trace(py, &module, "MISSING")).is_err());
    }

    #[test]
    fn invalid_pdf_keeps_provider_failure() {
        assert!(Python::attach(|py| pdf(py, b"invalid PDF")).is_err());
    }
}
