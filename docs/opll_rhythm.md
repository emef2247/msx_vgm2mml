# OPLL rhythm Segment inspection

Run the usual converter with `--dump-passes`. The additional
`<stem>.opll.segments.csv` records all native Segment fields before target
voice assignment. Existing trace files and `.opll.pass0.csv` are preserved.
Segment dumping does not change segmentation. Rhythm rendering is described below.

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
a match. No source Segment is modified; the target renderer can consume these repeats.

The grouping stage preserves every eligible input Segment, including duplicate
same-tick triggers. It cannot recover events discarded by earlier passes or
represent volume-only writes absent from the input Segments. Existing raw and
state CSVs remain the evidence for those future investigations.

## MGSDRV rhythm output

The main converter now uses `rhythm_mml.py` to append track `f` to a new
`.opll.target.mml` projection. The merged output selects that projection;
legacy melodic variants remain available for regression checks. Target MML
is retained with --dump-passes or --debug and removed otherwise.

BD/SD/TOM/CYM/HH map to b/s/m/c/h, with combined hits in one timed token.
Native attenuation maps to vb/vs/vm/vc/vh using 15 - attenuation. Exact
adjacent repeats become finite loops (maximum 255 repetitions per loop).
Each pattern unit initializes the volumes it needs so loop iterations are
independent of incoming volume state. Sync annotation may expand loops when
a shared marker falls inside them. Allocation includes the emitted f text.

Timing remains one source tick per target step at tempo 75 in raw mode, or
three target steps at tempo 225 normally. No 735.77-sample timing profile is
applied. Long gaps use a single attack followed by rests, avoiding artificial
retriggering. The final attack is encoded through the latest Segment end,
with a one-source-tick minimum. This positive length is a target requirement,
not inferred acoustic decay. Source CSVs remain unchanged.

Duplicate same-instrument triggers at the same tick raise an explicit error
rather than silently dropping an attack or moving it in time. The current
projection uses ordinary MGSDRV rhythm instruments; source pitch-register
variation and volume-only changes absent from trigger Segments are not
projected. They remain inspectable in source traces.

Sync parsing distinguishes rhythm track f under #opll_mode 1 from melodic f
under mode 0. It supports emitted compound hits, explicit lengths, default
length colons and instrument volume commands. This is not a general parser
for arbitrary hand-authored rhythm MML (e.g. last-iteration loop exits).

Validation: 47 unittest methods passed, including onset/volume equivalence
before and after sync, raw/normal output, long gaps, repeat initialization,
silent tracks and duplicate-trigger rejection. Six supplied fixtures were
converted in both modes; all emitted rhythm attacks matched group CSVs.
MGSC 1.11 via mgsc-js 2.0.0 compiled all eight isolated rhythm outputs from
the four rhythm fixtures. Full sample output compiled in both modes; other
full-song outputs can still exceed source-length or melodic allocation
limits. Compiler success does not establish audio equivalence.

Rhythm tail correction: target end includes the latest OPLL trace tick as
well as Segment ends. Attack-only rhythm Segments omit the final key-off;
using their ends alone truncated the last cymbal in rhythm_only_test02.
The fixture now ends at tick 77 rather than 41, retaining its tick-40 attack.
This does not reconstruct unlogged trailing VGM waits or acoustic decay.
Seven rhythm renderer tests pass, including normal/raw tail checks.
