//! Native parent-root attestation and authenticated child handoffs.
//!
//! This module is the authority foundation for later Rust-owned filesystem
//! effects. It deliberately exposes no raw-path mutation operation.

use cap_std::fs::Dir;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::env;
use std::ffi::{OsStr, OsString};
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Duration;

#[cfg(target_os = "linux")]
mod linux;
#[cfg(not(target_os = "linux"))]
mod unsupported;

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
        for (index, pair) in value.as_bytes().chunks_exact(2).enumerate() {
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

impl AttestationRequest {
    /// Capture established parent and child inputs without replacing typed bindings.
    ///
    /// The inherited runtime source root is deliberately not copied into `source_root`:
    /// that variable may differ from the source identity bound into a child handoff.
    fn capture_environment(
        &mut self,
        environment: &BTreeMap<OsString, OsString>,
    ) -> Result<(), AuthorityError> {
        if self.explicit_root.is_none() {
            if let Some(value) = environment.get(OsStr::new("AGENT_CANON_PARENT_ROOT")) {
                if let Some(text) = value.to_str() {
                    let trimmed = text.trim();
                    if !trimmed.is_empty() {
                        self.explicit_root = Some(PathBuf::from(trimmed));
                    }
                } else if !value.is_empty() {
                    self.explicit_root = Some(PathBuf::from(value.as_os_str()));
                }
            }
        }

        let child_purpose = environment_text(environment, "AGENT_CANON_CHILD_PURPOSE")?;
        let audience = environment_text(environment, "AGENT_CANON_HANDOFF_AUDIENCE")?;
        let token_in_environment = environment_text(environment, "AGENT_CANON_CHILD_HANDOFF")?;
        let child_markers = [
            "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
            "AGENT_CANON_PARENT_ROOT_DEV",
            "AGENT_CANON_PARENT_ROOT_INO",
            "AGENT_CANON_CHILD_PURPOSE",
            "AGENT_CANON_HANDOFF_AUDIENCE",
            "AGENT_CANON_CHILD_HANDOFF",
        ];
        let child_context = child_markers
            .iter()
            .any(|name| environment.contains_key(OsStr::new(name)));

        if let Some(token) = token_in_environment {
            if token.is_empty() {
                return Err(AuthorityError::new(
                    ParentRootReject::HandoffInvalid,
                    "inherited child handoff token is empty",
                ));
            }
            let token = SecretToken::from_untrusted(token);
            if self
                .child_handoff_token
                .as_ref()
                .is_some_and(|existing| existing != &token)
            {
                return Err(AuthorityError::new(
                    ParentRootReject::HandoffInvalid,
                    "inherited child handoff token conflicts with the request",
                ));
            }
            self.child_handoff_token = Some(token);
        }

        if child_context && self.child_handoff_token.is_none() {
            return Err(AuthorityError::new(
                ParentRootReject::HandoffInvalid,
                "child environment is missing its handoff token",
            ));
        }

        if self.child_handoff_token.is_some() {
            let inherited_purpose = audience.or(child_purpose);
            if let Some(purpose) = inherited_purpose {
                self.purpose = NonEmptyTrimmedString::new(purpose).map_err(|_| {
                    AuthorityError::new(
                        ParentRootReject::HandoffInvalid,
                        "inherited child handoff purpose is invalid",
                    )
                })?;
            }
        }
        Ok(())
    }
}

fn environment_text(
    environment: &BTreeMap<OsString, OsString>,
    name: &str,
) -> Result<Option<String>, AuthorityError> {
    environment
        .get(OsStr::new(name))
        .map(|value| {
            value.to_str().map(str::to_owned).ok_or_else(|| {
                AuthorityError::new(
                    ParentRootReject::HandoffInvalid,
                    "inherited child environment value is not UTF-8",
                )
            })
        })
        .transpose()
}

fn environment_path(environment: &BTreeMap<OsString, OsString>, name: &str) -> Option<PathBuf> {
    environment
        .get(OsStr::new(name))
        .and_then(|value| value.to_str())
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
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
    owner: OwnerRoot,
    owner_path: PathBuf,
    owner_identity: FileIdentity,
    purpose: NonEmptyTrimmedString,
    token_digest: Option<Sha256Digest>,
    parent_components: Vec<ComponentIdentity>,
    target: Option<TargetIdentity>,
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

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum OwnerRoot {
    Parent,
    GitCommon,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct ComponentIdentity {
    pub(crate) name: OsString,
    pub(crate) identity: FileIdentity,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum EntryKind {
    File,
    Directory,
    Symlink,
    Other,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct TargetIdentity {
    pub(crate) identity: FileIdentity,
    pub(crate) kind: EntryKind,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct LexicalSnapshot {
    pub(crate) parent_path: PathBuf,
    pub(crate) parent_components: Vec<ComponentIdentity>,
    pub(crate) parent_identity: FileIdentity,
    pub(crate) entry: Option<LexicalEntrySnapshot>,
}

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

    pub fn attest(&self, request: &AttestationRequest) -> Result<AttestedParent, AuthorityError> {
        platform::attest(request)
    }

    /// Attest a request after capturing the established process environment.
    ///
    /// Child markers are treated as a handoff context and cannot fall back to an
    /// ordinary parent-root attestation when their single-use token is absent.
    pub fn attest_from_process_environment(
        &self,
        request: &AttestationRequest,
    ) -> Result<AttestedParent, AuthorityError> {
        let environment = env::vars_os().collect::<BTreeMap<_, _>>();
        self.attest_with_environment(request, &environment)
    }

    /// Attest the explicit parent selected by the established parent-root environment.
    ///
    /// This convenience path models the legacy parent-owned writer request. Call
    /// [`Self::attest_from_process_environment`] with a fully populated request when
    /// source, clone, marker, or expected-identity bindings are required; handoffs with
    /// omitted bindings fail validation rather than dropping those token bindings.
    pub fn attest_parent_from_process_environment(
        &self,
        purpose: NonEmptyTrimmedString,
        nonce: Nonce128,
    ) -> Result<AttestedParent, AuthorityError> {
        let environment = env::vars_os().collect::<BTreeMap<_, _>>();
        self.attest_parent_with_environment(purpose, nonce, &environment)
    }

    fn attest_parent_with_environment(
        &self,
        purpose: NonEmptyTrimmedString,
        nonce: Nonce128,
        environment: &BTreeMap<OsString, OsString>,
    ) -> Result<AttestedParent, AuthorityError> {
        let configured_root = environment_path(&environment, "AGENT_CANON_PARENT_ROOT")
            .ok_or_else(|| {
                AuthorityError::new(
                    ParentRootReject::HandoffInvalid,
                    "explicit parent root is required",
                )
            })?;
        let parent_root = fs::canonicalize(configured_root).map_err(|_| {
            AuthorityError::new(
                ParentRootReject::RootMissing,
                "explicit parent root cannot be resolved",
            )
        })?;
        let request = AttestationRequest {
            cwd: parent_root.clone(),
            explicit_root: Some(parent_root),
            source_root: None,
            clone_root: None,
            topic_marker: None,
            gitmodules: None,
            owner_evidence: None,
            expected_remote: None,
            expected_module_digest: None,
            child_handoff_token: None,
            purpose,
            nonce,
        };
        self.attest_with_environment(&request, environment)
    }

    fn attest_with_environment(
        &self,
        request: &AttestationRequest,
        environment: &BTreeMap<OsString, OsString>,
    ) -> Result<AttestedParent, AuthorityError> {
        let mut request = request.clone();
        request.capture_environment(environment)?;
        let active_root = environment_path(environment, "AGENT_CANON_ACTIVE_REPOSITORY_ROOT");
        platform::attest_with_active_repository_root(&request, active_root.as_deref())
    }

    pub fn issue_child_handoff(
        &self,
        request: &ChildHandoffRequest,
    ) -> Result<ChildHandoffReceipt, AuthorityError> {
        platform::issue_child_handoff(request)
    }

    pub fn reattest_child(
        &self,
        request: &AttestationRequest,
    ) -> Result<AttestedParent, AuthorityError> {
        #[cfg(not(target_os = "linux"))]
        return Err(AuthorityError::new(
            ParentRootReject::UnsupportedPlatform,
            "native parent-root authority currently requires Linux",
        ));
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
        atomic_replace_parent_owned_file, attest, attest_with_active_repository_root,
        issue_child_handoff, read_parent_owned_file, resolve_parent_owned_path,
        verify_live_identity, write_parent_owned_file,
    };
}

#[cfg(not(target_os = "linux"))]
mod platform {
    pub(crate) use super::unsupported::{
        atomic_replace_parent_owned_file, attest, attest_with_active_repository_root,
        issue_child_handoff, read_parent_owned_file, resolve_parent_owned_path,
        verify_live_identity, write_parent_owned_file,
    };
}

pub(crate) fn digest_bytes(bytes: &[u8]) -> Sha256Digest {
    Sha256Digest(Sha256::digest(bytes).into())
}

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

#[cfg(test)]
mod environment_capture_tests {
    use super::*;

    fn environment(entries: &[(&str, &str)]) -> BTreeMap<OsString, OsString> {
        entries
            .iter()
            .map(|(key, value)| (OsString::from(key), OsString::from(value)))
            .collect()
    }

    fn request() -> AttestationRequest {
        AttestationRequest {
            cwd: PathBuf::from("/cwd"),
            explicit_root: None,
            source_root: Some(PathBuf::from("/source-binding")),
            clone_root: Some(PathBuf::from("/clone-binding")),
            topic_marker: Some(PathBuf::from("/marker.json")),
            gitmodules: Some(PathBuf::from("/.gitmodules")),
            owner_evidence: Some(PathBuf::from("/owner.json")),
            expected_remote: Some("https://example.invalid/repository.git".into()),
            expected_module_digest: Some(Sha256Digest::from_bytes([7; 32])),
            child_handoff_token: None,
            purpose: NonEmptyTrimmedString::new("inventory-parent").unwrap(),
            nonce: Nonce128::from_bytes([1; 16]),
        }
    }

    #[test]
    fn parent_root_precedence_and_existing_bindings_survive_capture() {
        let mut request = request();
        request.explicit_root = Some(PathBuf::from("/explicit-root"));
        let environment = environment(&[
            ("AGENT_CANON_PARENT_ROOT", "/environment-root"),
            ("AGENT_CANON_SOURCE_ROOT", "/runtime-source"),
        ]);

        request
            .capture_environment(&environment)
            .expect("capture parent-only environment");

        assert_eq!(request.explicit_root, Some(PathBuf::from("/explicit-root")));
        assert_eq!(request.source_root, Some(PathBuf::from("/source-binding")));
        assert_eq!(request.clone_root, Some(PathBuf::from("/clone-binding")));
        assert_eq!(request.topic_marker, Some(PathBuf::from("/marker.json")));
        assert_eq!(request.gitmodules, Some(PathBuf::from("/.gitmodules")));
        assert_eq!(request.owner_evidence, Some(PathBuf::from("/owner.json")));
        assert_eq!(
            request.expected_remote.as_deref(),
            Some("https://example.invalid/repository.git")
        );
        assert_eq!(
            request.expected_module_digest,
            Some(Sha256Digest::from_bytes([7; 32]))
        );
        assert_eq!(request.purpose.as_str(), "inventory-parent");
    }

    #[test]
    fn parent_root_environment_fills_only_an_unset_explicit_root() {
        let mut request = request();
        let environment = environment(&[("AGENT_CANON_PARENT_ROOT", "/environment-root")]);

        request
            .capture_environment(&environment)
            .expect("capture parent root from process environment");

        assert_eq!(
            request.explicit_root,
            Some(PathBuf::from("/environment-root"))
        );
    }

    #[test]
    fn child_markers_require_a_token_even_when_parent_root_is_set() {
        let mut request = request();
        let environment = environment(&[
            ("AGENT_CANON_PARENT_ROOT", "/parent"),
            ("AGENT_CANON_ACTIVE_REPOSITORY_ROOT", "/parent"),
            ("AGENT_CANON_CHILD_PURPOSE", "log-surface-inventory"),
            ("AGENT_CANON_HANDOFF_AUDIENCE", "inventory-parent"),
        ]);

        let rejected = request
            .capture_environment(&environment)
            .expect_err("child environment cannot fall back to parent-root attestation");

        assert_eq!(rejected.reject, ParentRootReject::HandoffInvalid);
    }

    #[test]
    fn handoff_audience_is_captured_without_replacing_source_bindings() {
        let mut request = request();
        let environment = environment(&[
            ("AGENT_CANON_CHILD_HANDOFF", "opaque-token"),
            ("AGENT_CANON_HANDOFF_AUDIENCE", "inventory-parent"),
            ("AGENT_CANON_CHILD_PURPOSE", "log-surface-inventory"),
            ("AGENT_CANON_SOURCE_ROOT", "/runtime-source"),
        ]);

        request
            .capture_environment(&environment)
            .expect("capture authenticated child context");

        assert_eq!(request.purpose.as_str(), "inventory-parent");
        assert_eq!(request.source_root, Some(PathBuf::from("/source-binding")));
        assert_eq!(request.clone_root, Some(PathBuf::from("/clone-binding")));
        assert_eq!(
            request.child_handoff_token.unwrap().expose_for_transport(),
            "opaque-token"
        );
    }
}
