//! Native runtime artifact identities and external projection bindings.
// @dependency-start
// contract implementation
// responsibility Groups native artifact identity and external binding implementations.
// upstream design ../../../../../../agents/COMMUNICATION_PROTOCOL.md artifact identity schemas
// downstream implementation artifact_identity.rs canonical bytes and Git source identity
// downstream implementation external_artifact_binding.rs local-event projection acknowledgements
// @dependency-end

pub(crate) mod artifact_identity;
pub(crate) mod external_artifact_binding;
