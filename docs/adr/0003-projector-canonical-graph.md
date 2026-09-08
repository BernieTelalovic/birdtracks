# ADR 0003: Canonical projector graphs

## Decision

Projector equality and hashing use a colored graph canonical form computed by
the BLISS implementation in `igraph`. External boundary labels are fixed by
distinct vertex colors. Node-local and internal strand labels are omitted from
the graph colors, so they behave as dummy names.

Directed, typed relations are represented by colored path gadgets because
BLISS operates on simple undirected colored graphs. Symmetrisers,
antisymmetrisers, permutation nodes, input ports, and output ports have
distinct structural colors. Disjoint node sequence order is therefore not
part of the canonical form.

The canonical coefficient records the parity needed to move antisymmetriser
ports to the canonical ordering. An odd graph automorphism makes the diagram
identically zero. The displayed/collapse coefficient remains separate so
canonicalization cannot change the represented operator.

The four complete two-factor permutation absorption identities are normalized
before graph-key comparison. General local absorption inside a larger graph
remains the responsibility of the simplification engine.

## Consequences

- Dummy relabeling and harmless internal reordering compare and hash equally.
- Boundary labels remain semantic and cannot be renamed by canonicalization.
- `ProjectorSum` collects canonically equivalent diagrams with exact signs.
- Canonical labeling is structural and does not expand S/A nodes into their
  factorial permutation sums.
- `igraph>=0.11,<2` is a required runtime dependency.
