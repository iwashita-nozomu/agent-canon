# Python Static Analysis
<!--
@dependency-start
contract tool
responsibility Documents Python static analysis entrypoints.
upstream design ../README.md language-organized static analysis index
upstream design ../../../../../documents/conventions/coding-conventions-python.md Python coding conventions
upstream implementation ../../config/basedpyright-explicit-any.json configures explicit Any diagnostics
upstream implementation ../../oop/python/readability.py scores Python OOP readability
@dependency-end
-->

Python review uses existing canonical tools rather than parallel wrappers.

Default commands:

```bash
./bootstrap.sh --control-parent-root <root> --runtime-root <runtime> \
  exec --root <target> -- basedpyright \
  --project /usr/local/share/agent-canon/runtime/tools/validation/code/config/basedpyright-explicit-any.json \
  <target>
```

Select either the standalone AgentCanon source or one project target before
running these checks. The tool does not discover a second repository.
