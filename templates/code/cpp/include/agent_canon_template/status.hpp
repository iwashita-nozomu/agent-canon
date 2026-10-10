// @dependency-start
// contract template
// responsibility Declares a minimal C++ status interface for a consumer-owned include path.
// upstream design ../../../../../documents/design/cpp-build-layout.md production path and consumer graph ownership
// downstream implementation ../../src/status.cpp provides the corresponding definition.
// downstream implementation ../../../../../tests/agent_tools/test_agent_team_templates.py exercises generated include/src paths.
// @dependency-end
#pragma once

namespace agent_canon_template {

enum class Status { ready };

Status status() noexcept;

}  // namespace agent_canon_template
