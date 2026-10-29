# Python structure hash compatibility fixture

These fixtures freeze the pre-port extractor and public CLI output. Source inputs
use `.py.fixture` so repository discovery does not treat the fixture tree as
production Python; tests copy them to `.py` paths in a temporary root. The CRLF
fixture retains its original byte line endings.

Baseline provenance: CPython 3.12.3; extractor source
`d7b4cb1b13e12eb553cf12f4164ce7e32d42a23c` (source blob
`8327cdb50262c47b6058fd05ddd89693198270c2`); old Rust CLI source
`7d03fc03d198e2b525807c90a3deaf77f6bbdb2f` and binary SHA-256
`857902fc05a5122d17f46d0ad4d12bd37594b2fe47a42315d4983cbf17535330`.
The resident capture returned 21 blocks from four analyzed files, with 13
findings groups: eight duplicate groups, three single-caller findings, and two
single-callee findings. The excluded fixture is absent from the analyzed set.

`expected/extractor-output.json`, `expected/cli-json.stdout`, and
`expected/cli-text.stdout` are copied byte-for-byte from the retained capture.
The complete capture request, manifest, stderr, and resident receipt remain in
the task artifact directory; the hash values used by unit tests are recorded in
`expected/baseline-hashes.json`.
