// @dependency-start
// contract implementation
// responsibility Calls existing external Python providers through PyO3's safe object APIs.
// upstream design ../../../../documents/design/rust-agent-tool-migration.md preserves consumer Python/JAX execution
// upstream reference https://github.com/PyO3/pyo3/blob/main/guide/src/python-from-rust.md Python object lifetime contract
// @dependency-end

use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyCFunction, PyDict};
use serde_json::{json, Value};
use std::io::{self, Read};
use std::path::Path;
use std::sync::{Arc, Mutex};

mod proof_trace_alignment;

#[derive(Default)]
struct HtmlText {
    title: Vec<String>,
    text: Vec<String>,
    hidden_depth: usize,
    in_title: bool,
}

fn html(py: Python<'_>, bytes: &[u8]) -> PyResult<Value> {
    let state = Arc::new(Mutex::new(HtmlText::default()));
    let parser = py.import("html.parser")?.getattr("HTMLParser")?.call0()?;
    let start_state = Arc::clone(&state);
    let start = PyCFunction::new_closure(py, None, None, move |args, _| -> PyResult<()> {
        let tag = args.get_item(0)?.extract::<String>()?.to_lowercase();
        let mut state = start_state.lock().map_err(|_| {
            pyo3::exceptions::PyRuntimeError::new_err("HTML text state lock poisoned")
        })?;
        if matches!(tag.as_str(), "script" | "style" | "noscript" | "template") {
            state.hidden_depth += 1;
        }
        if tag == "title" {
            state.in_title = true;
        }
        if matches!(
            tag.as_str(),
            "p" | "br" | "div" | "section" | "article" | "li" | "h1" | "h2" | "h3"
        ) {
            state.text.push("\n".into());
        }
        Ok(())
    })?;
    let end_state = Arc::clone(&state);
    let end = PyCFunction::new_closure(py, None, None, move |args, _| -> PyResult<()> {
        let tag = args.get_item(0)?.extract::<String>()?.to_lowercase();
        let mut state = end_state.lock().map_err(|_| {
            pyo3::exceptions::PyRuntimeError::new_err("HTML text state lock poisoned")
        })?;
        if matches!(tag.as_str(), "script" | "style" | "noscript" | "template")
            && state.hidden_depth > 0
        {
            state.hidden_depth -= 1;
        }
        if tag == "title" {
            state.in_title = false;
        }
        Ok(())
    })?;
    let data_state = Arc::clone(&state);
    let data = PyCFunction::new_closure(py, None, None, move |args, _| -> PyResult<()> {
        let data = args.get_item(0)?.extract::<String>()?;
        let mut state = data_state.lock().map_err(|_| {
            pyo3::exceptions::PyRuntimeError::new_err("HTML text state lock poisoned")
        })?;
        if state.in_title {
            state.title.push(data.clone());
        }
        if state.hidden_depth == 0 && !data.trim().is_empty() {
            state.text.push(data);
        }
        Ok(())
    })?;
    parser.setattr("handle_starttag", start)?;
    parser.setattr("handle_endtag", end)?;
    parser.setattr("handle_data", data)?;
    parser.call_method1("feed", (String::from_utf8_lossy(bytes).as_ref(),))?;
    let state = state
        .lock()
        .map_err(|_| pyo3::exceptions::PyRuntimeError::new_err("HTML text state lock poisoned"))?;
    Ok(
        json!({"status":"pass","title":state.title.join(" "),"text":state.text.join(" "),"method":"stdlib-html-parser"}),
    )
}

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
            "usage: agent-canon-python-provider <html-extract|pdf-extract|trace-json|proof-source|runtime> [arguments]"
        );
        std::process::exit(2);
    };
    if command == "proof-trace-alignment"
        && args.len() == 5
        && ["text", "json"].contains(&args[4].as_str())
    {
        std::process::exit(proof_trace_alignment::run(
            args[1].clone().into(),
            &args[2],
            &args[3],
            &args[4],
        ));
    }
    if command == "proof-source" && args.len() == 4 {
        match proof_trace_alignment::proof_source(&args[1], &args[2], &args[3]) {
            Ok(value) => {
                println!("{value}");
                std::process::exit(0);
            }
            Err(error) => {
                let unavailable = Python::attach(|py| {
                    error.is_instance_of::<pyo3::exceptions::PyModuleNotFoundError>(py)
                });
                println!(
                    "{}",
                    serde_json::json!({"status":"fail","available":!unavailable,"error":error.to_string()})
                );
                std::process::exit(1);
            }
        }
    }
    let result = match command {
        "runtime" if args.len() == 1 => Python::attach(runtime),
        "pdf-extract" | "html-extract" if args.len() == 1 => {
            let mut bytes = Vec::new();
            if let Err(error) = io::stdin().read_to_end(&mut bytes) {
                eprintln!("{error}");
                std::process::exit(2);
            }
            Python::attach(|py| {
                if command == "pdf-extract" {
                    pdf(py, &bytes)
                } else {
                    html(py, &bytes)
                }
            })
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
            let unavailable = Python::attach(|py| {
                error.is_instance_of::<pyo3::exceptions::PyModuleNotFoundError>(py)
            });
            println!(
                "{}",
                json!({"status":"fail","available":!unavailable,"error":error.to_string()})
            );
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
    fn proof_source_extracts_ast_without_importing_module() {
        let temporary = tempfile::tempdir().unwrap();
        let source = temporary.path().join("sample.py");
        let sentinel = temporary.path().join("executed.txt");
        std::fs::write(
            &source,
            format!(
                "open({:?}, 'w').write('executed')\n\ndef lemma(x: int) -> int:\n    \"\"\"Claim: lemma returns x + 1.\"\"\"\n    if x > 0:\n        return x + 1\n    return 1\n",
                sentinel.to_string_lossy()
            ),
        )
        .unwrap();
        let result = proof_trace_alignment::proof_source(
            source.to_str().unwrap(),
            "lemma",
            temporary.path().to_str().unwrap(),
        )
        .unwrap();
        assert_eq!(result["node_kind"], "FunctionDef");
        assert_eq!(result["signature"], "def lemma(x: int) -> int");
        assert_eq!(result["branch_count"], 1);
        assert_eq!(result["return_expressions"][0], "1");
        assert_eq!(result["return_expressions"][1], "x + 1");
        assert_eq!(result["path"], "sample.py");
        assert!(!sentinel.exists());
        assert!(proof_trace_alignment::proof_source(
            source.to_str().unwrap(),
            "missing",
            temporary.path().to_str().unwrap()
        )
        .is_err());
    }

    #[test]
    fn invalid_pdf_keeps_provider_failure() {
        assert!(Python::attach(|py| pdf(py, b"invalid PDF")).is_err());
    }

    #[test]
    fn pdf_extracts_text_through_the_real_pypdf_api() {
        let text = "BT /F1 12 Tf 10 100 Td (Native provider PDF) Tj ET";
        let objects = [
            "<< /Type /Catalog /Pages 2 0 R >>".to_owned(),
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>".to_owned(),
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>".to_owned(),
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>".to_owned(),
            format!("<< /Length {} >>\nstream\n{text}\nendstream", text.len()),
        ];
        let mut bytes = b"%PDF-1.4\n".to_vec();
        let mut offsets = vec![0];
        for (index, object) in objects.iter().enumerate() {
            offsets.push(bytes.len());
            bytes.extend_from_slice(format!("{} 0 obj\n{object}\nendobj\n", index + 1).as_bytes());
        }
        let xref = bytes.len();
        bytes.extend_from_slice(b"xref\n0 6\n0000000000 65535 f \n");
        for offset in &offsets[1..] {
            bytes.extend_from_slice(format!("{offset:010} 00000 n \n").as_bytes());
        }
        bytes.extend_from_slice(
            format!("trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n").as_bytes(),
        );
        let result = Python::attach(|py| pdf(py, &bytes)).unwrap();
        assert_eq!(result["method"], "pypdf");
        assert!(result["text"]
            .as_str()
            .unwrap()
            .contains("Native provider PDF"));
    }

    #[test]
    fn html_uses_standard_parser_entities_and_hides_scripts() {
        let result = Python::attach(|py| {
            html(
                py,
                b"<title>A &amp; B</title><script>hidden()</script><p>Visible &#65;</p>",
            )
        })
        .unwrap();
        assert_eq!(result["title"], "A & B");
        assert!(result["text"].as_str().unwrap().contains("Visible A"));
        assert!(!result["text"].as_str().unwrap().contains("hidden"));
    }
}
