//! Reusable native library owners for AgentCanon template operations.

pub mod code_template_rendering;
pub mod entrypoint_composer;
pub(crate) mod runtime_boundary;
pub mod template_bundle;

#[cfg(test)]
mod template_tests;
