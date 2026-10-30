use super::{
    AttestationRequest, AttestedParent, AuthorityError, ChildHandoffReceipt, ChildHandoffRequest,
    ParentRootReject,
};

pub(crate) fn attest(_: &AttestationRequest) -> Result<AttestedParent, AuthorityError> {
    Err(unsupported())
}

pub(crate) fn issue_child_handoff(
    _: &ChildHandoffRequest,
) -> Result<ChildHandoffReceipt, AuthorityError> {
    Err(unsupported())
}

pub(crate) fn verify_live_identity(_: &AttestedParent) -> Result<(), AuthorityError> {
    Err(unsupported())
}

fn unsupported() -> AuthorityError {
    AuthorityError::new(
        ParentRootReject::UnsupportedPlatform,
        "native parent-root authority currently requires Linux",
    )
}
