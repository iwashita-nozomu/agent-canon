// @dependency-start
// contract template
// responsibility Defines the minimal C++ status interface from the sibling header.
// upstream design ../../../../documents/design/cpp-build-layout.md production path and consumer graph ownership
// upstream implementation ../include/agent_canon_template/status.hpp declares the interface.
// downstream implementation ../../../../tests/agent_tools/test_agent_team_templates.py exercises generated include/src paths.
// @dependency-end
#include "agent_canon_template/status.hpp"

namespace agent_canon_template {

Status status() noexcept { return Status::ready; }

}  // namespace agent_canon_template
