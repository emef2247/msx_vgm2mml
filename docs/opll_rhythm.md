# OPLL rhythm Segment inspection

Run the usual converter with `--dump-passes`. The additional
`<stem>.opll.segments.csv` records all native Segment fields before target
voice assignment. Existing trace files and `.opll.pass0.csv` are preserved.
This change does not add rhythm MML or change segmentation.

Channels 9, 10, 11, 12 and 13 identify BD, SD, TOM, CYM (`tc`) and HH.
These are internal channels, not target MML track identifiers.

- `time` is the source event time in seconds; `ticks`, `tick_start` and
  `tick_end` use the existing 60 Hz analysis clock.
- For `rhythm_expand`, `keyon` is the rising-edge result for that channel.
  The five `bd/sd/tom/tc/hh` fields retain source flags, not five independent
  triggers. Only the instrument associated with the channel is emitted.
- PASS4 also contains non-trigger rows; rhythm Segment construction retains
  rhythm-mode-enabled rows with `keyon=1`.
- `tick_end` records the existing analysis interval, not measured acoustic
  decay. `vol` is native OPLL attenuation. Raw FNUM/BLOCK and channel state
  remain available; no common frequency/pan schema is introduced here.
- Unset native attributes are blank. Target voice identifiers have not yet
  been assigned in this dump.

`tests/test_opll_rhythm.py` compares freshly generated trace/register CSVs
and PASS1-4 against optional `reference/vgm2tx802` files. It also compares
the exported rhythm Segment timing, keyon, pitch registers, volume and flags
with reference PASS4 trigger rows. Missing reference fixtures are skipped.
Local-only fixture contents must not be committed.

Synthetic tests independently check held bits, same-tick off/on edges,
simultaneous instruments and volume-only writes at the expansion stage.
These do not establish full-pipeline behavior for every synthetic edge case,
mode transition or acoustic release. Reference parity likewise does not prove
the reference converter handles every chip behavior correctly.

Next stages are complete-pipeline edge-case coverage, explicit state/trigger
separation for a shared schema, and finally MGSDRV rhythm rendering.

## Tick groups and exact patterns

`--dump-passes` additionally writes three independent analysis tables:

- `<stem>.opll.rhythm.groups.csv`: one group per occupied 60 Hz tick. `hits`
  is a JSON list with instrument, native attenuation and pitch state. Each
  hit has `channel` and zero-based `segment_index`, referencing that channel's
  rows in `.opll.segments.csv`. Source timestamps and duplicate same-instrument
  hits are retained; sharing a tick does not imply the same source timestamp.
- `<stem>.opll.rhythm.patterns.csv`: pattern definitions, one relative step
  per row, with exact outgoing gap and hit signatures.
- `<stem>.opll.rhythm.occurrences.csv`: ordered pattern IDs, starting group
  and absolute tick, unit group count, and adjacent repetition count.

The final group's `gap_ticks` is blank: the interval to a next trigger is
unknown. No acoustic release or song-end rest is inferred. Initial silence
is represented by the first absolute tick. Segment interval lengths and
shared pitch-register state participate in equality, as well as instruments,
volumes, multiplicity and outgoing gaps. IDs and absolute timestamps do not.
Reordering different instruments at one tick is not modeled as a new pattern;
the original timestamps remain in group hits and native Segments.

Extraction chooses the adjacent repeat saving the most groups at the current
position, preferring shorter units on ties. Unmatched groups become single-step
definitions, which can also be reused. Pattern IDs are deterministic for an
input but are not persistent across edits. This is an exact, greedy analysis,
not bar/phrase detection or optimal compression. A one-tick difference prevents
a match. No source Segment is modified and no MML loop is emitted yet.

The grouping stage preserves every eligible input Segment, including duplicate
same-tick triggers. It cannot recover events discarded by earlier passes or
represent volume-only writes absent from the input Segments. Existing raw and
state CSVs remain the evidence for those future investigations.
