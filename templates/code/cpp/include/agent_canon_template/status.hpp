// @dependency-start
// contract template
// responsibility Declares a minimal C++ status interface for a consumer-owned include path.
// upstream design ../../../../../documents/design/cpp-build-layout.md production path and consumer graph ownership
// @dependency-end
#pragma once

namespace agent_canon_template {

enum class Status { ready };

Status status() noexcept;

}  // namespace agent_canon_template
