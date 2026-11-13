// @dependency-start
// contract implementation
// responsibility Invokes caller-selected Python/JAX roots through safe CPython APIs and returns lowered runtime observations.
// downstream implementation ../dispatch/agent-canon/src/jit_canonical_ir.rs owns StableHLO and evidence extraction
// @dependency-end

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyCFunction, PyDict, PyTuple};
use serde_json::{json, Value};
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::path::Path;

fn text(py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<String> {
    py.import("builtins")?
        .getattr("str")?
        .call1((value,))?
        .extract::<String>()
}

fn resolve_symbol<'py>(py: Python<'py>, reference: &str) -> PyResult<Bound<'py, PyAny>> {
    let (path, qualname) = reference.split_once("::").ok_or_else(|| {
        PyValueError::new_err(format!(
            "symbol must be path.py::qualname, got {reference:?}"
        ))
    })?;
    let path = Path::new(path)
        .canonicalize()
        .map_err(|error| PyValueError::new_err(format!("symbol path does not exist: {error}")))?;
    let path_text = path.to_string_lossy();
    let mut path_hash = DefaultHasher::new();
    path.hash(&mut path_hash);
    let module_name = format!("_agent_canon_jit_root_{:016x}", path_hash.finish());
    let util = py.import("importlib.util")?;
    let spec = util.call_method1(
        "spec_from_file_location",
        (&module_name, path_text.as_ref()),
    )?;
    if spec.is_none() {
        return Err(PyValueError::new_err(format!(
            "cannot load module from {path_text}"
        )));
    }
    let module = util.call_method1("module_from_spec", (&spec,))?;
    py.import("sys")?
        .getattr("modules")?
        .set_item(&module_name, &module)?;
    spec.getattr("loader")?
        .call_method1("exec_module", (&module,))?;
    let mut value = module;
    for part in qualname.split('.') {
        value = value.getattr(part)?;
    }
    if !value.is_callable() {
        return Err(PyValueError::new_err(format!(
            "resolved symbol is not callable: {reference}"
        )));
    }
    Ok(value)
}

fn normalize_inputs<'py>(
    py: Python<'py>,
    value: Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyTuple>, Bound<'py, PyDict>)> {
    let mapping = py.import("collections.abc")?.getattr("Mapping")?;
    let (args, kwargs) = if value.is_instance(&mapping)? {
        let args = value
            .get_item("args")
            .unwrap_or_else(|_| PyTuple::empty(py).into_any());
        let kwargs = value
            .get_item("kwargs")
            .unwrap_or_else(|_| PyDict::new(py).into_any());
        (args, kwargs)
    } else if value.is_instance_of::<PyTuple>() && value.len().unwrap_or_default() == 2 {
        let second = value.get_item(1)?;
        if second.is_instance(&mapping)? {
            (value.get_item(0)?, second)
        } else {
            (value, PyDict::new(py).into_any())
        }
    } else {
        (value, PyDict::new(py).into_any())
    };
    let tuple_type = py.import("builtins")?.getattr("tuple")?;
    let args = tuple_type.call1((args,))?.cast_into::<PyTuple>()?;
    let kwargs = py
        .import("builtins")?
        .getattr("dict")?
        .call1((kwargs,))?
        .cast_into::<PyDict>()?;
    Ok((args, kwargs))
}

fn tree_leaves(
    py: Python<'_>,
    jax: &Bound<'_, PyAny>,
    root_name: &str,
    root_index: usize,
    value: &Bound<'_, PyAny>,
) -> PyResult<Vec<Value>> {
    let tree_util = jax.getattr("tree_util")?;
    let flattened = tree_util.call_method1("tree_flatten_with_path", (value,))?;
    let entries = flattened.get_item(0)?;
    let mut rows = Vec::new();
    for (leaf_index, item) in entries.try_iter()?.enumerate() {
        let item = item?;
        let path = item.get_item(0)?;
        let leaf = item.get_item(1)?;
        let local_path = text(py, &tree_util.call_method1("keystr", (&path,))?)?;
        let public_path = if local_path.is_empty() {
            root_name.to_owned()
        } else {
            format!("{root_name}{local_path}")
        };
        let type_name = leaf.get_type().getattr("__name__")?.extract::<String>()?;
        let shape = leaf
            .getattr("shape")
            .and_then(|shape| text(py, &shape))
            .unwrap_or_default();
        let dtype = leaf
            .getattr("dtype")
            .and_then(|dtype| text(py, &dtype))
            .unwrap_or_default();
        rows.push(json!({
            "leaf_index": leaf_index,
            "root_index": root_index,
            "root_name": root_name,
            "path": public_path,
            "local_path": local_path,
            "python_type": type_name,
            "shape": shape,
            "dtype": dtype
        }));
    }
    Ok(rows)
}

fn json_safe(py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<Value> {
    if value.is_none() {
        return Ok(Value::Null);
    }
    if let Ok(value) = value.extract::<bool>() {
        return Ok(json!(value));
    }
    if let Ok(value) = value.extract::<i64>() {
        return Ok(json!(value));
    }
    if let Ok(value) = value.extract::<u64>() {
        return Ok(json!(value));
    }
    if let Ok(value) = value.extract::<f64>() {
        return Ok(json!(value));
    }
    if let Ok(value) = value.extract::<String>() {
        return Ok(json!(value));
    }
    let mapping = py.import("collections.abc")?.getattr("Mapping")?;
    if value.is_instance(&mapping)? {
        let mut object = serde_json::Map::new();
        for item in value.call_method0("items")?.try_iter()? {
            let item = item?;
            let key = text(py, &item.get_item(0)?)?;
            object.insert(key, json_safe(py, &item.get_item(1)?)?);
        }
        return Ok(Value::Object(object));
    }
    if value.is_instance_of::<PyTuple>() || value.is_instance_of::<pyo3::types::PyList>() {
        return value
            .try_iter()?
            .map(|item| json_safe(py, &item?))
            .collect::<PyResult<Vec<_>>>()
            .map(Value::Array);
    }
    Ok(json!(text(py, value)?))
}

fn problem_assumptions(
    py: Python<'_>,
    jax: &Bound<'_, PyAny>,
    root_name: &str,
    root_index: usize,
    value: &Bound<'_, PyAny>,
) -> PyResult<Vec<Value>> {
    let attribute = "__agent_canon_problem_assumptions__";
    let predicate = PyCFunction::new_closure(py, None, None, move |args, _| -> PyResult<bool> {
        args.get_item(0)?.hasattr(attribute)
    })?;
    let options = PyDict::new(py);
    options.set_item("is_leaf", predicate)?;
    let flattened = jax.getattr("tree_util")?.call_method(
        "tree_flatten_with_path",
        (value,),
        Some(&options),
    )?;
    let entries = flattened.get_item(0)?;
    let tree_util = jax.getattr("tree_util")?;
    let mut rows = Vec::new();
    for (assumption_index, item) in entries.try_iter()?.enumerate() {
        let item = item?;
        let path = item.get_item(0)?;
        let leaf = item.get_item(1)?;
        if !leaf.hasattr(attribute)? {
            continue;
        }
        let local_path = text(py, &tree_util.call_method1("keystr", (&path,))?)?;
        let public_path = if local_path.is_empty() {
            root_name.to_owned()
        } else {
            format!("{root_name}{local_path}")
        };
        let type_name = leaf.get_type().getattr("__name__")?.extract::<String>()?;
        let metadata = json_safe(py, &leaf.getattr(attribute)?)?;
        rows.push(json!({
            "assumption_index": assumption_index,
            "root_index": root_index,
            "root_name": root_name,
            "path": public_path,
            "local_path": local_path,
            "python_type": type_name,
            "metadata": metadata
        }));
    }
    Ok(rows)
}

fn contains_abstract_dynamic_leaf(
    py: Python<'_>,
    jax: &Bound<'_, PyAny>,
    args: &Bound<'_, PyTuple>,
    kwargs: &Bound<'_, PyDict>,
) -> PyResult<bool> {
    let shape_type = jax.getattr("ShapeDtypeStruct")?;
    let values = PyTuple::new(py, [args.clone().into_any(), kwargs.clone().into_any()])?;
    let leaves = jax
        .getattr("tree_util")?
        .call_method1("tree_leaves", (values,))?;
    for leaf in leaves.try_iter()? {
        if leaf?.is_instance(&shape_type)? {
            return Ok(true);
        }
    }
    Ok(false)
}

fn lower_abstract_inputs<'py>(
    py: Python<'py>,
    function: &Bound<'py, PyAny>,
    args: &Bound<'py, PyTuple>,
    kwargs: &Bound<'py, PyDict>,
    jax: &Bound<'py, PyAny>,
    eqx: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let is_array = eqx.getattr("is_array")?.unbind();
    let shape_type = jax.getattr("ShapeDtypeStruct")?.unbind();
    let predicate =
        PyCFunction::new_closure(py, None, None, move |call_args, _| -> PyResult<bool> {
            let py = call_args.py();
            let value = call_args.get_item(0)?;
            let is_dynamic_array = is_array.bind(py).call1((&value,))?.is_truthy()?;
            Ok(is_dynamic_array || value.is_instance(shape_type.bind(py))?)
        })?;
    let inputs = PyTuple::new(
        py,
        [
            function.clone(),
            args.clone().into_any(),
            kwargs.clone().into_any(),
        ],
    )?;
    let partition = eqx.call_method1("partition", (inputs, predicate))?;
    let dynamic = partition.get_item(0)?;
    let static_tree = partition.get_item(1)?.unbind();
    let tree_util = jax.getattr("tree_util")?.unbind();
    let flattened = tree_util
        .bind(py)
        .call_method1("tree_flatten", (&dynamic,))?;
    let flat_values = py
        .import("builtins")?
        .getattr("tuple")?
        .call1((flattened.get_item(0)?,))?
        .cast_into::<PyTuple>()?;
    let tree_definition = flattened.get_item(1)?.unbind();
    let eqx = eqx.clone().unbind();
    let jnp = py.import("jax.numpy")?.unbind();
    let static_type = py.import("equinox._module")?.getattr("Static")?.unbind();
    let wrapped =
        PyCFunction::new_closure(py, None, None, move |flat_args, _| -> PyResult<Py<PyAny>> {
            let py = flat_args.py();
            let dynamic_tree = tree_util
                .bind(py)
                .call_method1("tree_unflatten", (tree_definition.bind(py), flat_args))?;
            let combined = eqx
                .bind(py)
                .call_method1("combine", (dynamic_tree, static_tree.bind(py)))?;
            let call_function = combined.get_item(0)?;
            let call_args = combined.get_item(1)?.cast_into::<PyTuple>()?;
            let call_kwargs = combined.get_item(2)?.cast_into::<PyDict>()?;
            let output = call_function.call(&call_args, Some(&call_kwargs))?;
            let is_array = eqx.bind(py).getattr("is_array")?;
            let outputs = eqx.bind(py).call_method1("partition", (output, is_array))?;
            let static_output = static_type.bind(py).call1((outputs.get_item(1)?,))?;
            let zero = jnp.bind(py).getattr("array")?.call1((0,))?;
            Ok(
                PyTuple::new(py, [zero, outputs.get_item(0)?, static_output])?
                    .into_any()
                    .unbind(),
            )
        })?;
    let jitted = jax.call_method1("jit", (wrapped,))?;
    jitted.call_method("lower", &flat_values, None)
}

fn lower<'py>(
    py: Python<'py>,
    function: &Bound<'py, PyAny>,
    args: &Bound<'py, PyTuple>,
    kwargs: &Bound<'py, PyDict>,
) -> PyResult<(String, String, Vec<String>, Bound<'py, PyAny>)> {
    let eqx = py.import("equinox")?;
    let jax = py.import("jax")?;
    let lowered = if contains_abstract_dynamic_leaf(py, &jax, args, kwargs)? {
        lower_abstract_inputs(py, function, args, kwargs, &jax, &eqx)?
    } else {
        let filter_jit = eqx.getattr("filter_jit")?.call1((function,))?;
        filter_jit.call_method("lower", args, Some(kwargs))?
    };
    let compiler_ir = lowered.getattr("compiler_ir");
    let mut errors = Vec::new();
    if let Ok(compiler_ir) = compiler_ir {
        for dialect in ["stablehlo", "hlo"] {
            let options = PyDict::new(py);
            options.set_item("dialect", dialect)?;
            match compiler_ir.call((), Some(&options)) {
                Ok(value) => return Ok((dialect.to_owned(), text(py, &value)?, errors, lowered)),
                Err(error) => errors.push(format!(
                    "{dialect}: {}: {error}",
                    error.get_type(py).name()?
                )),
            }
        }
    }
    if let Ok(as_text) = lowered.getattr("as_text") {
        match as_text.call0() {
            Ok(value) => return Ok(("stablehlo".into(), text(py, &value)?, errors, lowered)),
            Err(error) => errors.push(format!("as_text: {}: {error}", error.get_type(py).name()?)),
        }
    }
    Err(PyValueError::new_err(format!(
        "failed to obtain compiler IR text: {}",
        errors.join("; ")
    )))
}

/// Execute only the selected consumer symbols and return Python/JAX runtime observations.
pub fn jit_lower(
    python_symbol: &str,
    input_factory_symbol: &str,
    input_device: Option<&str>,
    compile_for_dump: bool,
) -> PyResult<Value> {
    Python::attach(|py| {
        let function = resolve_symbol(py, python_symbol)?;
        let input_factory = resolve_symbol(py, input_factory_symbol)?;
        let jax = py.import("jax")?.into_any();
        let factory_value =
            if let Some(device_kind) = input_device.filter(|value| !value.is_empty()) {
                let devices = jax.call_method1("devices", (device_kind,))?;
                if devices.len()? == 0 {
                    return Err(PyValueError::new_err(format!(
                        "No JAX devices for input device kind: {device_kind}"
                    )));
                }
                let context = jax.call_method1("default_device", (devices.get_item(0)?,))?;
                context.call_method0("__enter__")?;
                let value = input_factory.call0();
                let exit = context.call_method1("__exit__", (py.None(), py.None(), py.None()));
                exit?;
                value?
            } else {
                input_factory.call0()?
            };
        let (args, kwargs) = normalize_inputs(py, factory_value)?;
        let (dialect, stablehlo, compiler_ir_errors, lowered) =
            if let Some(device_kind) = input_device.filter(|value| !value.is_empty()) {
                let devices = jax.call_method1("devices", (device_kind,))?;
                if devices.len()? == 0 {
                    return Err(PyValueError::new_err(format!(
                        "No JAX devices for input device kind: {device_kind}"
                    )));
                }
                let context = jax.call_method1("default_device", (devices.get_item(0)?,))?;
                context.call_method0("__enter__")?;
                let lowered = lower(py, &function, &args, &kwargs);
                let exit = context.call_method1("__exit__", (py.None(), py.None(), py.None()));
                exit?;
                lowered?
            } else {
                lower(py, &function, &args, &kwargs)?
            };
        let xla_compile = if !compile_for_dump {
            json!({})
        } else if let Ok(compile_fn) = lowered.getattr("compile") {
            match compile_fn.call0() {
                Ok(compiled) => {
                    json!({"available":true,"returncode":0,"status":"succeeded","compiled_type":compiled.get_type().getattr("__name__")?.extract::<String>()?})
                }
                Err(error) => {
                    json!({"available":true,"returncode":1,"status":"failed","error":format!("{}: {error}",error.get_type(py).name()?)})
                }
            }
        } else {
            json!({"available":false,"returncode":null,"status":"compile_method_unavailable"})
        };
        let mut argument_leaves = Vec::new();
        let mut assumption_rows = Vec::new();
        for (index, value) in args.iter().enumerate() {
            argument_leaves.extend(tree_leaves(
                py,
                &jax,
                &format!("arg{index}"),
                index,
                &value,
            )?);
            assumption_rows.extend(problem_assumptions(
                py,
                &jax,
                &format!("arg{index}"),
                index,
                &value,
            )?);
        }
        let kwargs_items = kwargs.items();
        let mut kwargs_values = kwargs_items
            .try_iter()?
            .map(|item| {
                let item = item?;
                Ok((text(py, &item.get_item(0)?)?, item.get_item(1)?))
            })
            .collect::<PyResult<Vec<_>>>()?;
        kwargs_values.sort_by(|left, right| left.0.cmp(&right.0));
        for (offset, (name, value)) in kwargs_values.iter().enumerate() {
            argument_leaves.extend(tree_leaves(py, &jax, name, args.len() + offset, value)?);
            assumption_rows.extend(problem_assumptions(
                py,
                &jax,
                name,
                args.len() + offset,
                value,
            )?);
        }
        let eval_shape = py.import("equinox")?.getattr("filter_eval_shape")?;
        let mut eval_arguments = vec![function.clone()];
        eval_arguments.extend(args.iter());
        let eval_arguments = PyTuple::new(py, eval_arguments)?;
        let output = eval_shape.call(&eval_arguments, Some(&kwargs));
        let output = match output {
            Ok(value) => value,
            Err(_) => jax.call_method("eval_shape", &eval_arguments, Some(&kwargs))?,
        };
        let roots = if output.is_instance_of::<PyTuple>() {
            output.cast_into::<PyTuple>()?
        } else {
            PyTuple::new(py, [output])?
        };
        let mut return_leaves = Vec::new();
        for (index, value) in roots.iter().enumerate() {
            return_leaves.extend(tree_leaves(
                py,
                &jax,
                &format!("return_{index}"),
                index,
                &value,
            )?);
        }
        let devices = jax.call_method0("devices")?;
        let device_names = devices
            .try_iter()?
            .map(|device| text(py, &device?))
            .collect::<PyResult<Vec<_>>>()?;
        let sys = py.import("sys")?;
        let platform = py
            .import("platform")?
            .call_method0("platform")?
            .extract::<String>()?;
        let metadata = py.import("importlib.metadata")?;
        let mut packages = serde_json::Map::new();
        for name in [
            "jax",
            "jaxlib",
            "equinox",
            "iree-base-compiler",
            "iree-base-runtime",
            "iree-compiler",
            "iree-runtime",
        ] {
            let version = metadata
                .call_method1("version", (name,))
                .and_then(|value| value.extract::<String>())
                .unwrap_or_default();
            packages.insert(
                name.to_owned(),
                if version.is_empty() {
                    Value::Null
                } else {
                    json!(version)
                },
            );
        }
        Ok(json!({
            "dialect": dialect,
            "stablehlo": stablehlo,
            "compiler_ir_errors": compiler_ir_errors,
            "argument_leaves": argument_leaves,
            "problem_assumptions": assumption_rows,
            "return_leaves": return_leaves,
            "jax_default_backend": text(py, &jax.call_method0("default_backend")?)?,
            "jax_devices": device_names,
            "jax_version": jax.getattr("__version__").and_then(|value| value.extract::<String>()).unwrap_or_default(),
            "python_version": text(py, &sys.getattr("version")?)?,
            "platform": platform,
            "packages": packages,
            "xla_compile": xla_compile
        }))
    })
}
