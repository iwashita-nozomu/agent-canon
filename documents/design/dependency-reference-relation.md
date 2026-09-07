# Dependency `reference` Relation

`reference` is a repository-contained evidence edge. It is reachable and must resolve, but it is never an authority or parent edge.

```text
reference(edge)
  => target exists
  => target is repository-contained
  => target contributes to evidence_paths
  => target does not contribute to parent_paths
  => target does not become a design or contract owner
```

Both `upstream reference <path> <reason>` and `downstream reference <path> <reason>` are valid. Missing targets, absolute paths, root escape, unknown directions, and unknown kinds remain failures. This relation adds no aliases such as `memo`, `citation`, or `report`.
