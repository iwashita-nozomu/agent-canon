use super::{
    AttestationRequest, AttestedParent, AuthorityError, ChildHandoffReceipt, ChildHandoffRequest,
    FileMode, NonEmptyTrimmedString, ParentOwnedDirectoryTarget, ParentOwnedNoReplaceOutcome,
    ParentOwnedPathReceipt, ParentRootReject,
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

pub(crate) fn ensure_parent_owned_directory(
    _: &AttestedParent,
    _: &Path,
    _: NonEmptyTrimmedString,
) -> Result<ParentOwnedPathReceipt, AuthorityError> {
    Err(unsupported())
}

pub(crate) fn set_parent_owned_directory_mode(
    _: &AttestedParent,
    _: &ParentOwnedPathReceipt,
    _: u32,
) -> Result<(), AuthorityError> {
    Err(unsupported())
}

pub(crate) fn reserve_parent_owned_directory_target(
    _: &AttestedParent,
    _: &Path,
    _: NonEmptyTrimmedString,
) -> Result<ParentOwnedDirectoryTarget, AuthorityError> {
    Err(unsupported())
}

pub(crate) fn verify_parent_owned_directory_target(
    _: &AttestedParent,
    _: &ParentOwnedDirectoryTarget,
) -> Result<(), AuthorityError> {
    Err(unsupported())
}

pub(crate) fn abort_parent_owned_directory_target(
    _: &AttestedParent,
    _: &ParentOwnedDirectoryTarget,
) -> Result<(), AuthorityError> {
    Err(unsupported())
}

pub(crate) fn remove_parent_owned_tree(
    _: &AttestedParent,
    _: &ParentOwnedPathReceipt,
) -> Result<(), AuthorityError> {
    Err(unsupported())
}

pub(crate) fn remove_empty_parent_owned_directory(
    _: &AttestedParent,
    _: &ParentOwnedPathReceipt,
) -> Result<bool, AuthorityError> {
    Err(unsupported())
}

pub(crate) fn read_parent_owned_file(
    _: &AttestedParent,
    _: &ParentOwnedPathReceipt,
) -> Result<Vec<u8>, AuthorityError> {
    Err(unsupported())
}

pub(crate) fn remove_parent_owned_file(
    _: &AttestedParent,
    _: &ParentOwnedPathReceipt,
) -> Result<(), AuthorityError> {
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
