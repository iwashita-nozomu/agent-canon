use super::{
    AttestationRequest, AttestedParent, AuthorityError, ChildHandoffReceipt, ChildHandoffRequest,
    FileMode, NonEmptyTrimmedString, ParentOwnedNoReplaceOutcome, ParentOwnedPathReceipt,
    ParentRootReject,
};
use std::path::Path;

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

pub(crate) fn resolve_parent_owned_path(
    _: &AttestedParent,
    _: &Path,
    _: NonEmptyTrimmedString,
) -> Result<ParentOwnedPathReceipt, AuthorityError> {
    Err(unsupported())
}

pub(crate) fn read_parent_owned_file(
    _: &AttestedParent,
    _: &ParentOwnedPathReceipt,
) -> Result<Vec<u8>, AuthorityError> {
    Err(unsupported())
}

pub(crate) fn atomic_replace_parent_owned_file(
    _: &AttestedParent,
    _: &ParentOwnedPathReceipt,
    _: &[u8],
    _: FileMode,
) -> Result<ParentOwnedPathReceipt, AuthorityError> {
    Err(unsupported())
}

pub(crate) fn write_parent_owned_file(
    _: &AttestedParent,
    _: &Path,
    _: &[u8],
    _: NonEmptyTrimmedString,
) -> Result<ParentOwnedPathReceipt, AuthorityError> {
    Err(unsupported())
}

pub(crate) fn publish_parent_owned_file_noreplace(
    _: &AttestedParent,
    _: &Path,
    _: &[u8],
    _: NonEmptyTrimmedString,
) -> Result<ParentOwnedNoReplaceOutcome, AuthorityError> {
    Err(unsupported())
}

fn unsupported() -> AuthorityError {
    AuthorityError::new(
        ParentRootReject::UnsupportedPlatform,
        "native parent-root authority currently requires Linux",
    )
}
