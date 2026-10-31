//! Native parent-root attestation and authenticated child handoffs.
//!
//! This module is the authority foundation for later Rust-owned filesystem
//! effects. It deliberately exposes no raw-path mutation operation.

#[cfg(target_os = "linux")]
use cap_std::fs::Dir;
#[cfg(target_os = "linux")]
use sha2::{Digest, Sha256};
#[cfg(target_os = "linux")]
use std::ffi::OsString;
use std::fmt;
use std::path::{Path, PathBuf};
use std::time::Duration;

#[cfg(target_os = "linux")]
mod linux;
#[cfg(not(target_os = "linux"))]
mod unsupported;

#[cfg(target_os = "linux")]
const HANDOFF_SCHEMA: &str = "agent-canon.child-handoff.v1";
const DEFAULT_HANDOFF_TTL: Duration = Duration::from_secs(900);

/// Stable rejection categories shared with the existing Python boundary.
#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub enum ParentRootReject {
    RootMissing,
    RootAmbiguous,
    RootMismatch,
    RootSpoofed,
    MarkerInvalid,
    ModuleInvalid,
    OwnerEvidenceInvalid,
    SymlinkEscape,
    RootRaceDetected,
    HandoffInvalid,
    UnsupportedPlatform,
    RuntimeRootRequired,
    RuntimeRootUnattested,
    RuntimeRootInvalid,
    RuntimePathEscape,
    RuntimeSymlinkEscape,
}

impl ParentRootReject {
    /// Return the stable serialized category used by existing callers.
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::RootMissing => "root_missing",
            Self::RootAmbiguous => "root_ambiguous",
            Self::RootMismatch => "root_mismatch",
            Self::RootSpoofed => "root_spoofed",
            Self::MarkerInvalid => "marker_invalid",
            Self::ModuleInvalid => "module_invalid",
            Self::OwnerEvidenceInvalid => "owner_evidence_invalid",
            Self::SymlinkEscape => "symlink_escape",
            Self::RootRaceDetected => "root_race_detected",
            Self::HandoffInvalid => "handoff_invalid",
            Self::UnsupportedPlatform => "unsupported_platform",
            Self::RuntimeRootRequired => "runtime_root_required",
            Self::RuntimeRootUnattested => "runtime_root_unattested",
            Self::RuntimeRootInvalid => "runtime_root_invalid",
            Self::RuntimePathEscape => "runtime_path_escape",
            Self::RuntimeSymlinkEscape => "runtime_symlink_escape",
        }
    }
}

impl fmt::Display for ParentRootReject {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

/// A typed authority rejection with a stable prefix and non-secret context.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AuthorityError {
    pub reject: ParentRootReject,
    detail: String,
}

impl AuthorityError {
    pub(crate) fn new(reject: ParentRootReject, detail: impl Into<String>) -> Self {
        Self {
            reject,
            detail: detail.into(),
        }
    }

    /// Return contextual detail that contains no handoff token or key bytes.
    pub fn detail(&self) -> &str {
        &self.detail
    }
}

impl fmt::Display for AuthorityError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.reject, self.detail)
    }
}

impl std::error::Error for AuthorityError {}

/// A validated non-empty string whose input has no surrounding whitespace.
#[derive(Clone, Debug, Eq, Hash, PartialEq)]
pub struct NonEmptyTrimmedString(String);

impl NonEmptyTrimmedString {
    pub fn new(value: impl Into<String>) -> Result<Self, AuthorityError> {
        let value = value.into();
        if value.trim().is_empty() || value.trim() != value {
            return Err(AuthorityError::new(
                ParentRootReject::RootMismatch,
                "purpose must be non-empty and trimmed",
            ));
        }
        Ok(Self(value))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl TryFrom<String> for NonEmptyTrimmedString {
    type Error = AuthorityError;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        Self::new(value)
    }
}

impl TryFrom<&str> for NonEmptyTrimmedString {
    type Error = AuthorityError;

    fn try_from(value: &str) -> Result<Self, Self::Error> {
        Self::new(value)
    }
}

/// A SHA-256 digest represented as exactly 32 bytes.
#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub struct Sha256Digest([u8; 32]);

impl Sha256Digest {
    pub fn from_bytes(bytes: [u8; 32]) -> Self {
        Self(bytes)
    }

    pub fn parse_hex(value: &str) -> Result<Self, AuthorityError> {
        if value.len() != 64 {
            return Err(AuthorityError::new(
                ParentRootReject::ModuleInvalid,
                "SHA-256 digest must contain 64 hexadecimal characters",
            ));
        }
        let mut bytes = [0_u8; 32];
        let (pairs, remainder) = value.as_bytes().as_chunks::<2>();
        if !remainder.is_empty() {
            return Err(AuthorityError::new(
                ParentRootReject::ModuleInvalid,
                "SHA-256 digest must contain 64 hexadecimal characters",
            ));
        }
        for (index, pair) in pairs.iter().enumerate() {
            let high = hex_nibble(pair[0]).ok_or_else(|| {
                AuthorityError::new(
                    ParentRootReject::ModuleInvalid,
                    "SHA-256 digest contains a non-hexadecimal character",
                )
            })?;
            let low = hex_nibble(pair[1]).ok_or_else(|| {
                AuthorityError::new(
                    ParentRootReject::ModuleInvalid,
                    "SHA-256 digest contains a non-hexadecimal character",
                )
            })?;
            bytes[index] = (high << 4) | low;
        }
        Ok(Self(bytes))
    }

    pub fn as_bytes(&self) -> &[u8; 32] {
        &self.0
    }

    pub fn to_hex(self) -> String {
        encode_hex(&self.0)
    }
}

/// A cryptographically generated, exactly 128-bit nonce.
#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub struct Nonce128([u8; 16]);

impl Nonce128 {
    pub fn from_bytes(bytes: [u8; 16]) -> Self {
        Self(bytes)
    }

    pub fn generate() -> Result<Self, AuthorityError> {
        let mut bytes = [0_u8; 16];
        getrandom::getrandom(&mut bytes).map_err(|_| {
            AuthorityError::new(
                ParentRootReject::UnsupportedPlatform,
                "operating-system nonce generation is unavailable",
            )
        })?;
        Ok(Self(bytes))
    }

    pub fn as_bytes(&self) -> &[u8; 16] {
        &self.0
    }
}

/// An untrusted bearer token. Formatting always redacts its contents.
#[derive(Clone)]
pub struct SecretToken(String);

impl SecretToken {
    pub fn from_untrusted(value: impl Into<String>) -> Self {
        Self(value.into())
    }

    pub fn expose_for_transport(&self) -> &str {
        &self.0
    }

    #[cfg(target_os = "linux")]
    fn digest(&self) -> Sha256Digest {
        Sha256Digest(Sha256::digest(self.0.as_bytes()).into())
    }
}

impl fmt::Debug for SecretToken {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("SecretToken([REDACTED])")
    }
}

impl PartialEq for SecretToken {
    fn eq(&self, other: &Self) -> bool {
        let left = self.0.as_bytes();
        let right = other.0.as_bytes();
        let mut difference = left.len() ^ right.len();
        for index in 0..left.len().max(right.len()) {
            let left_byte = left.get(index).copied().unwrap_or(0);
            let right_byte = right.get(index).copied().unwrap_or(0);
            difference |= usize::from(left_byte ^ right_byte);
        }
        difference == 0
    }
}

impl Eq for SecretToken {}

/// The canonical display path and already-opened directory capability.
pub struct PhysicalRoot {
    pub(crate) path: PathBuf,
    #[cfg(target_os = "linux")]
    pub(crate) directory: Dir,
    pub(crate) identity: FileIdentity,
}

impl PhysicalRoot {
    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn identity(&self) -> FileIdentity {
        self.identity
    }
}

impl fmt::Debug for PhysicalRoot {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("PhysicalRoot")
            .field("path", &self.path)
            .field("identity", &self.identity)
            .finish()
    }
}

/// Device/inode identity captured from an opened directory handle.
#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub struct FileIdentity {
    device: u64,
    inode: u64,
}

impl FileIdentity {
    pub fn device(self) -> u64 {
        self.device
    }

    pub fn inode(self) -> u64 {
        self.inode
    }
}

/// Stable root classification selected by attestation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RootKind {
    Topic,
    Vendored,
    Direct,
    Standalone,
}

impl RootKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Topic => "topic",
            Self::Vendored => "vendored",
            Self::Direct => "direct",
            Self::Standalone => "standalone",
        }
    }
}

/// Stable root-selection precedence.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RootPrecedence {
    ExplicitGit,
    Resolver,
}

impl RootPrecedence {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::ExplicitGit => "explicit-git",
            Self::Resolver => "resolver",
        }
    }
}

/// Where the child handoff token is carried.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum HandoffTransport {
    ParentLocalFile,
    Stdin,
    Descriptor,
}

impl HandoffTransport {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::ParentLocalFile => "parent-local-file",
            Self::Stdin => "stdin",
            Self::Descriptor => "descriptor",
        }
    }

    #[cfg(target_os = "linux")]
    pub(crate) fn from_str(value: &str) -> Option<Self> {
        match value {
            "parent-local-file" => Some(Self::ParentLocalFile),
            "stdin" => Some(Self::Stdin),
            "descriptor" => Some(Self::Descriptor),
            _ => None,
        }
    }
}

/// Storage class bound into a handoff token.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum HandoffStorage {
    ParentLocalFile,
    Pipe,
}

impl HandoffStorage {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::ParentLocalFile => "parent-local-file",
            Self::Pipe => "pipe",
        }
    }
}

/// Permission/transport mode bound into a handoff token.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum HandoffMode {
    PrivateFile0600,
    Pipe,
}

impl HandoffMode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::PrivateFile0600 => "0600",
            Self::Pipe => "pipe",
        }
    }
}

/// Untrusted root and identity inputs for one attestation.
#[derive(Clone, Debug)]
pub struct AttestationRequest {
    pub cwd: PathBuf,
    pub explicit_root: Option<PathBuf>,
    pub source_root: Option<PathBuf>,
    pub clone_root: Option<PathBuf>,
    pub topic_marker: Option<PathBuf>,
    pub gitmodules: Option<PathBuf>,
    pub owner_evidence: Option<PathBuf>,
    pub expected_remote: Option<String>,
    pub expected_module_digest: Option<Sha256Digest>,
    pub child_handoff_token: Option<SecretToken>,
    pub purpose: NonEmptyTrimmedString,
    pub nonce: Nonce128,
}

/// Input for issuing one purpose-bound child token.
#[derive(Clone, Debug)]
pub struct ChildHandoffRequest {
    pub parent_root: PathBuf,
    pub source_root: Option<PathBuf>,
    pub clone_root: Option<PathBuf>,
    pub audience: NonEmptyTrimmedString,
    pub ttl: Duration,
    pub transport: HandoffTransport,
}

impl ChildHandoffRequest {
    pub fn new(parent_root: impl Into<PathBuf>, audience: NonEmptyTrimmedString) -> Self {
        Self {
            parent_root: parent_root.into(),
            source_root: None,
            clone_root: None,
            audience,
            ttl: DEFAULT_HANDOFF_TTL,
            transport: HandoffTransport::ParentLocalFile,
        }
    }
}

/// Metadata and secret token produced for one child handoff.
#[derive(Clone, Debug)]
pub struct ChildHandoffReceipt {
    pub token_version: String,
    pub audience: NonEmptyTrimmedString,
    pub parent_root: PathBuf,
    pub source_root: Option<PathBuf>,
    pub clone_root: Option<PathBuf>,
    pub issued_at: f64,
    pub expires_at: f64,
    pub nonce: Nonce128,
    pub payload_sha256: Sha256Digest,
    pub storage: HandoffStorage,
    pub mode: HandoffMode,
    pub validation: String,
    pub transport: HandoffTransport,
    token: SecretToken,
}

impl ChildHandoffReceipt {
    pub fn token(&self) -> &SecretToken {
        &self.token
    }
}

/// Handoff evidence that can only be constructed after signature and replay checks.
#[derive(Clone, Debug)]
pub struct VerifiedChildHandoff {
    pub token_version: String,
    pub audience: NonEmptyTrimmedString,
    pub issued_at: f64,
    pub expires_at: f64,
    pub nonce: Nonce128,
    pub payload_sha256: Sha256Digest,
    pub storage: HandoffStorage,
    pub mode: HandoffMode,
    pub validation: String,
    pub transport: HandoffTransport,
    token_digest: Sha256Digest,
}

impl VerifiedChildHandoff {
    pub fn token_digest(&self) -> Sha256Digest {
        self.token_digest
    }
}

/// A validated file mode admitted by atomic parent-owned replacement.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum FileMode {
    Private0600,
}

/// A sealed capability snapshot for one file beneath an attested owner root.
#[derive(Clone, Debug)]
pub struct ParentOwnedPathReceipt {
    lexical_path: PathBuf,
    physical_path: PathBuf,
    #[cfg(target_os = "linux")]
    owner: OwnerRoot,
    #[cfg(target_os = "linux")]
    owner_path: PathBuf,
    #[cfg(target_os = "linux")]
    owner_identity: FileIdentity,
    #[cfg(target_os = "linux")]
    purpose: NonEmptyTrimmedString,
    #[cfg(target_os = "linux")]
    token_digest: Option<Sha256Digest>,
    #[cfg(target_os = "linux")]
    parent_components: Vec<ComponentIdentity>,
    #[cfg(target_os = "linux")]
    target: Option<TargetIdentity>,
    #[cfg(target_os = "linux")]
    lexical_snapshot: Option<LexicalSnapshot>,
}

impl ParentOwnedPathReceipt {
    pub fn lexical_path(&self) -> &Path {
        &self.lexical_path
    }

    pub fn physical_path(&self) -> &Path {
        &self.physical_path
    }
}

#[cfg(target_os = "linux")]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum OwnerRoot {
    Parent,
    GitCommon,
}

#[cfg(target_os = "linux")]
#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct ComponentIdentity {
    pub(crate) name: OsString,
    pub(crate) identity: FileIdentity,
}

#[cfg(target_os = "linux")]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum EntryKind {
    File,
    Directory,
    Symlink,
    Other,
}

#[cfg(target_os = "linux")]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct TargetIdentity {
    pub(crate) identity: FileIdentity,
    pub(crate) kind: EntryKind,
}

#[cfg(target_os = "linux")]
#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct LexicalSnapshot {
    pub(crate) parent_path: PathBuf,
    pub(crate) parent_components: Vec<ComponentIdentity>,
    pub(crate) parent_identity: FileIdentity,
    pub(crate) entry: Option<LexicalEntrySnapshot>,
}

#[cfg(target_os = "linux")]
#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct LexicalEntrySnapshot {
    pub(crate) name: OsString,
    pub(crate) identity: FileIdentity,
    pub(crate) kind: EntryKind,
    pub(crate) symlink_target: Option<PathBuf>,
}

/// Root and Git-common-directory identity established by attestation.
pub struct AttestedParent {
    pub(crate) parent_root: PhysicalRoot,
    pub(crate) parent_identity: FileIdentity,
    pub(crate) git_common_dir: PhysicalRoot,
    pub(crate) git_common_identity: FileIdentity,
    pub(crate) source_root: Option<PhysicalRoot>,
    pub(crate) clone_root: Option<PhysicalRoot>,
    pub(crate) root_kind: RootKind,
    pub(crate) precedence: RootPrecedence,
    pub(crate) purpose: NonEmptyTrimmedString,
    pub(crate) handoff: Option<VerifiedChildHandoff>,
    token_digest: Option<Sha256Digest>,
}

impl AttestedParent {
    pub fn parent_root(&self) -> &PhysicalRoot {
        &self.parent_root
    }

    pub fn parent_identity(&self) -> FileIdentity {
        self.parent_identity
    }

    pub fn git_common_dir(&self) -> &PhysicalRoot {
        &self.git_common_dir
    }

    pub fn git_common_identity(&self) -> FileIdentity {
        self.git_common_identity
    }

    pub fn source_root(&self) -> Option<&PhysicalRoot> {
        self.source_root.as_ref()
    }

    pub fn clone_root(&self) -> Option<&PhysicalRoot> {
        self.clone_root.as_ref()
    }

    pub fn root_kind(&self) -> RootKind {
        self.root_kind
    }

    pub fn precedence(&self) -> RootPrecedence {
        self.precedence
    }

    pub fn purpose(&self) -> &NonEmptyTrimmedString {
        &self.purpose
    }

    pub fn handoff(&self) -> Option<&VerifiedChildHandoff> {
        self.handoff.as_ref()
    }

    pub fn verify_live_identity(&self) -> Result<(), AuthorityError> {
        platform::verify_live_identity(self)
    }

    pub fn token_digest(&self) -> Option<Sha256Digest> {
        self.token_digest
    }

    pub fn resolve_parent_owned_path(
        &self,
        candidate: &Path,
        purpose: NonEmptyTrimmedString,
    ) -> Result<ParentOwnedPathReceipt, AuthorityError> {
        platform::resolve_parent_owned_path(self, candidate, purpose)
    }

    pub fn read_parent_owned_file(
        &self,
        receipt: &ParentOwnedPathReceipt,
    ) -> Result<Vec<u8>, AuthorityError> {
        platform::read_parent_owned_file(self, receipt)
    }

    pub fn atomic_replace_parent_owned_file(
        &self,
        receipt: &ParentOwnedPathReceipt,
        bytes: &[u8],
        mode: FileMode,
    ) -> Result<ParentOwnedPathReceipt, AuthorityError> {
        platform::atomic_replace_parent_owned_file(self, receipt, bytes, mode)
    }

    pub fn write_parent_owned_file(
        &self,
        candidate: &Path,
        bytes: &[u8],
        purpose: NonEmptyTrimmedString,
    ) -> Result<ParentOwnedPathReceipt, AuthorityError> {
        platform::write_parent_owned_file(self, candidate, bytes, purpose)
    }
}

impl fmt::Debug for AttestedParent {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("AttestedParent")
            .field("parent_root", &self.parent_root)
            .field("parent_identity", &self.parent_identity)
            .field("git_common_dir", &self.git_common_dir)
            .field("git_common_identity", &self.git_common_identity)
            .field("source_root", &self.source_root)
            .field("clone_root", &self.clone_root)
            .field("root_kind", &self.root_kind)
            .field("precedence", &self.precedence)
            .field("purpose", &self.purpose)
            .field("handoff", &self.handoff)
            .field("token_digest", &self.token_digest)
            .finish()
    }
}

/// Native authority owner. Durable handoff state is rooted under the selected repository.
#[derive(Clone, Copy, Debug, Default)]
pub struct ParentRootAttestor;

impl ParentRootAttestor {
    pub fn new() -> Self {
        Self
    }

    /// Attest exactly the roots, bindings, purpose, nonce, and token in `request`.
    ///
    /// This low-level operation does not construct a request from process environment.
    /// Callers that intentionally consume a child handoff use `reattest_child` after
    /// supplying its token and all request bindings explicitly.
    pub fn attest(&self, request: &AttestationRequest) -> Result<AttestedParent, AuthorityError> {
        platform::attest(request)
    }

    pub fn issue_child_handoff(
        &self,
        request: &ChildHandoffRequest,
    ) -> Result<ChildHandoffReceipt, AuthorityError> {
        platform::issue_child_handoff(request)
    }

    /// Reattest an explicitly populated child request and consume its handoff token.
    pub fn reattest_child(
        &self,
        request: &AttestationRequest,
    ) -> Result<AttestedParent, AuthorityError> {
        #[cfg(not(target_os = "linux"))]
        {
            let _ = request;
            Err(AuthorityError::new(
                ParentRootReject::UnsupportedPlatform,
                "native parent-root authority currently requires Linux",
            ))
        }
        #[cfg(target_os = "linux")]
        {
            if request.child_handoff_token.is_none() {
                return Err(AuthorityError::new(
                    ParentRootReject::HandoffInvalid,
                    "child handoff token was dropped",
                ));
            }
            self.attest(request)
        }
    }
}

#[cfg(target_os = "linux")]
mod platform {
    pub(crate) use super::linux::{
        atomic_replace_parent_owned_file, attest, issue_child_handoff, read_parent_owned_file,
        resolve_parent_owned_path, verify_live_identity, write_parent_owned_file,
    };
}

#[cfg(not(target_os = "linux"))]
mod platform {
    pub(crate) use super::unsupported::{
        atomic_replace_parent_owned_file, attest, issue_child_handoff, read_parent_owned_file,
        resolve_parent_owned_path, verify_live_identity, write_parent_owned_file,
    };
}

#[cfg(target_os = "linux")]
pub(crate) fn digest_bytes(bytes: &[u8]) -> Sha256Digest {
    Sha256Digest(Sha256::digest(bytes).into())
}

#[cfg(target_os = "linux")]
pub(crate) fn digest_hex(bytes: &[u8]) -> String {
    digest_bytes(bytes).to_hex()
}

pub(crate) fn encode_hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        output.push(char::from(HEX[usize::from(byte >> 4)]));
        output.push(char::from(HEX[usize::from(byte & 0x0f)]));
    }
    output
}

fn hex_nibble(value: u8) -> Option<u8> {
    match value {
        b'0'..=b'9' => Some(value - b'0'),
        b'a'..=b'f' => Some(value - b'a' + 10),
        b'A'..=b'F' => Some(value - b'A' + 10),
        _ => None,
    }
}
