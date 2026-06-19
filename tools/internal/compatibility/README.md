<!--
@dependency-start
contract tool
responsibility Defines the target area for legacy compatibility wrappers.
upstream design ../../catalog.yaml structured tool audience and placement catalog
upstream design ../README.md internal tool placement policy
downstream implementation ../../agent_tools/tool_catalog.py validates compatibility-wrapper placement
@dependency-end
-->

# Compatibility Wrappers

Use this directory only for wrappers that preserve old callers while pointing
to a canonical command. A catalog entry with `status: compatibility_wrapper`
must use `placement: compatibility_wrapper`.
