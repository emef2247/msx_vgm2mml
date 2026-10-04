# Known Mistakes and Traps

These are specific failure modes and prevention checks. They supplement
[AGENTS.md](AGENTS.md) and the authoritative
[project principles](docs/project_knowledge.md); they do not replace them.

For the OPM/MDX incident, the confirmed primary mistake was misreading the
requested transformation stage. Test overfitting was a concern raised during
the discussion, not an established cause. The test-related warning below is
a preventive guard; it must not be read as a finding that overfitting occurred.

## Do not reshape intermediate representations just to pass tests

A regression test or expected artifact is evidence, not the specification.

Do not split, merge, normalize, or otherwise reshape Segments or earlier
intermediate representations merely because doing so makes an expected output
or regression test pass.

When a test fails, first determine which layer owns the discrepancy:

- source/state reconstruction
- musical interpretation / Segment construction
- target projection
- test expectation

Preserve source evidence and inspect intermediate outputs before changing their
semantics.

A passing test does not justify violating the project's transformation
boundaries.

This is not a ban on correcting source analysis or improving an intermediate
schema. A justified change must explain the source semantics, the affected
information and its traceability, rather than use cleaner output or a passing
test as its sole rationale.

## Do not confuse target tracks with source CSV organization

During the OPM-to-MDX work, a request to separate MML into channel tracks was
misinterpreted as a reason to partition source analysis into musical/control
streams and additional CSVs. That source-stream partition was withdrawn.
The established integrated Segment CSV was already the intended input.

Before changing a representation, identify which stage the request concerns:
Raw, State/trace, Segment, source-structure analysis or target projection.
For an MML track request, first inspect how existing Segment channel information
is mapped to output tracks. Do not redesign earlier stages merely to mirror
the target's track layout.

Keep all channels of a chip together in its integrated Segment CSV. Rows must
retain enough native state and provenance to inspect events by time or channel
without joining separate channel/control files. This does not require identical
schemas or one combined CSV for different chip families.

Target musical/control organization and auxiliary analysis dumps are allowed
when useful. They must not replace or fragment the established source inspection
view. Append derived IDs or mappings without obscuring original fields, and
distinguish source channels, target tracks and shared-control ownership.

## Do not use final roundtrip agreement to justify unexplained interpretation

The early OPM loop experiment compared generated MDX commands. That can support
target-text compression, but does not establish that a repeated source phrase
was independently identified. The adopted source-structure path instead defines
its units and equality from native Segments before projecting target commands.

For source-structure work, explain boundaries, equality fields and handling of
zero-duration events using source evidence. Retain the original members and
mapping to every candidate. Then check target expansion and an independent
roundtrip within their stated scopes.

Distinguish a detected source candidate, a safely mapped target boundary and an
actually emitted loop. Matching final state, Key-On totals or compiler output
does not prove that intermediate event order, attacks, timing or human
inspectability were preserved. A source interpretation must have a reason
independent of the result it is being tested against.

Exact source-sample equality is the current OPM baseline, not an always-on rule
for every future matcher. A tolerant or musical comparison needs its own
explicit, justified criteria while retaining native evidence; roundtrip success
alone does not supply those criteria.

The implementation history and validation scope are recorded in
[the OPM source-loop note](field_notes/2026-10-05_opm_source_loops.md).
