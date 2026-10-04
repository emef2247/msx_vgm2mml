# OPM Segment to MDX MML and roundtrip validation

This target consumes native `OpmSegment` objects and writes MDX-dialect MML
on tracks A..H (ch0..7). The default structured notation combines ordinary
notes, reconstructed tone definitions and reversible finite loops with explicit
`y<register>,<data>` controls wherever ordinary notation cannot safely describe
the source. PCM/PDX output and cross-chip voice translation are not implemented.
MGSDRV conversion remains a separate PSG/SCC/OPLL path.

## Compaction before macros

MDX output does not yet extract macros. After source-loop projection, the
renderer removes redundant voice, volume, pan, gate, detune and octave setters.
Every track has its own target state. A raw operator/algorithm write invalidates
voice/volume/pan reuse: the same voice number may be needed to restore the tone.
The first setters inside a loop are retained, since the incoming first-pass
state need not equal the state at the loop's back edge.

Long rests can be encoded as finite repetitions of the compiler's 128-tick
rest chunks. Long sustained notes can similarly repeat identical 256-tick
note-and-tie pairs. The tie stays **inside** the body, e.g. `[c%256 &]4 c%17`,
so the compiler's lookahead disables KeyOff on each held chunk. Untied notes,
different pitches and intervening raw controls are not merged into a sustain.
This reduces compiled bytes without changing the ordered duration chunks.
`--no-loops` disables these new duration loops as well as source-loop emission;
redundant setter removal remains active. New duration brackets are skipped at
the external compiler's 64-level nesting limit; source-loop discovery is not capped.

The native source-loop plan and integrated Segment CSV remain unchanged.
OPM, like OPLL, distinguishes new Key edges from held-note updates before target
rendering; OPM also retains individual operator masks. PSG/SCC software-envelope
selection is a separate path, whose default builds source structure before
selecting envelopes. This MDX compaction does not add software envelopes or
infer new note boundaries.

With `--dump-passes`, `.mdx.structure.uncompacted.mml` retains the source-loop
projection before compaction and `.mdx.structure.compaction.csv` explains every
omission/rewrite. Its token indices address the original track body, excluding
the `A @t255` header initialization. `.units.csv` still contains the original
commands and source membership. The timing summary separates source-loop count,
total emitted loops, omitted setters, duration compactions and estimated binary
bytes saved. `.plain.mml` remains the original flat baseline. A longer rest-loop
spelling may save binary bytes even when its individual text token grows.

## Generate MDX MML

```bash
python scripts/opm_to_mdx_mml.py \
  tests/fixtures/public/opm/from_mdx/held_controls/held_controls.vgm \
  --outdir outputs/opm/mdx/held_controls
```

By default, this leaves only `<stem>.mdx.mml` in a fresh output directory.
The converter still builds native Segments; its internal trace files are kept
in a temporary directory and removed after reading. Existing files from an
earlier dump run are not deleted.

To retain inspectable raw/state/Segment CSVs and the target projection, add
`--dump-passes`:

```bash
python scripts/opm_to_mdx_mml.py \
  tests/fixtures/public/opm/from_mdx/held_controls/held_controls.vgm \
  --outdir outputs/opm/mdx/held_controls --dump-passes
```

This keeps the native raw/state/Segment CSVs plus:

| File | Contents |
|---|---|
| `<stem>.mdx.mml` | UTF-8 hybrid MDX MML notes, tones, loops and required register controls |
| `<stem>.mdx.controls.csv` | Source event/Segment IDs, source samples, target tick, projected samples, timing error, register/data, ch and MDX track |
| `<stem>.mdx.timing.json` | Timing projection, track layout, collapsed intervals and nonchanging source-write counts |

The renderer consumes Segments, not a raw VGM command copy. Shared-register
writes affecting eight channels are deduplicated by their source event ID;
all associated Segment IDs remain in the controls CSV. Source order stays intact
in the source evidence and projection CSV. Within each track, partial operator
keys, same-time off/on and held-note parameter changes keep their order.
Unchanged writes omitted by Segment construction cannot be recovered by this
target; they remain available in the raw/state CSVs. Retained test/timer writes
are not removed merely because their register value repeats.

The first target accepts one **4 MHz YM2151**. Different clocks, YM2164 and dual
instances are explicitly rejected rather than silently changing pitch or
merging channels. This does not restrict the native reader's wider analysis.

## Channel ownership and scheduling

The default `--track-layout channels` assigns channel controls, all four
operator register banks, KC/KF and Key masks to the corresponding A..H track.
Every used track begins at the common VGM origin and retains its final tail.
Noise register 0x0f belongs to ch7 and is emitted on H. LFO/test/timer and other
chip-wide controls are emitted once on A; this is a target scheduling lane,
not a claim that those controls belong to physical ch0.

MDX processes tracks A..H in order at a tick. Independent cross-channel
writes sharing a projected tick can therefore change their relative order.
The verifier explicitly predicts this target schedule, reports
`source_write_order_preserved`, and still checks source-known state at every
retained control. It does not waive state mismatches caused by shared controls.
For a source with coupled same-tick controls that cannot pass these checks,
`--notation registers --track-layout conductor` retains the original one-track
control order.
Both conversion and verification commands accept these explicit compatibility
options; structured notation requires channel tracks.

The raw trace and target controls CSV now expose `ch`; chip-wide controls use
an empty field. The target CSV additionally exposes `mdx_track`, so physical
channel ownership and the shared-control scheduling lane remain distinct.

## Time projection

Source `vgmticks` remain absolute integer 44100 Hz sample positions. MDX output
uses `@t255`: one playback tick is 256 microseconds, or 7056/625 VGM samples.
Each absolute source position is rounded to the nearest target tick; individual
gap errors do not accumulate. `r%N` advances each track independently and does not imply
that all physical channels are acoustically silent. Notes retain absolute
projected gate durations; no musical-length normalization is applied.

The current external playback represents each resulting sample position by
integer truncation. The source-to-target difference is at most six samples.
Positive source intervals may collapse to one target tick; their within-channel write order
and Key edges remain intact, and the timing JSON reports the number of such
intervals. Zero-duration events are never discarded. Final time is projected
from the real VGM end, preserving a trailing sustained/released interval.

## External compilation and replay

The compiler/player is a development-only helper using mmlx 0.2.0 and soundlog
0.15.0. It is not required by the Python engine or committed-fixture tests.

```bash
cargo build --release --locked --manifest-path scripts/mdx_fixture_generator/Cargo.toml
python scripts/verify_opm_mdx_roundtrip.py tests/fixtures/public/opm \
  --outdir outputs/opm/mdx_roundtrip/public_all
```

Use `--generator /path/to/mdx-fixture-generator` for a binary built elsewhere.
A single input VGM can replace the input directory. Directory scans include
`.vgm`/`.vgz` case-insensitively and exclude `reference/` and `mdx_roundtrip/`
expected replay material. Header preflight classifies unsupported source clocks,
variants and dual chips as `unsupported_target` before building large traces;
it does not retune or rewrite source evidence.

The tool writes generated
MML, MDX, returned VGM, both native analyses, compile logs, per-case comparison
JSON and aggregate `results.csv`/`results.json`. Both aggregate files are updated
after each input, and successful artifacts have absolute MML/MDX/VGM paths in
the results. Failed inputs retain `conversion.log`; compiler stdout/stderr and
timeout output are retained in `returned.compile.log`. A compiled MDX is saved
before replay so it survives a later player failure. Compilation can fail when
uncompressed tracks exceed MDX's 16-bit offset capacity; no events
are clipped or dropped to make it fit.

This validation tool always
retains intermediate evidence; the regular conversion command saves it only
with `--dump-passes`. Neither tool overwrites inputs.
Source files containing a VGM loop are inspected through their first traversal;
recovering a target song loop is separate work.

The external player's tick budget is derived from the projected source end.
At this fine clock, a fixed 100000-tick default covers only 25.6 seconds and
would reject longer cases. The budget permits completion without clipping the
source or relaxing comparison. Compiler timeout/failure is reported with logs.

With `--notation registers`, comparison requires:

- Exact register/data sequence for every retained Segment control under the
  predicted A..H target scheduling.
- No missing/extra channel attack, operator KeyOn or operator KeyOff, counted
  per channel before summing so opposing channel errors cannot cancel.
- Matching source-known raw and decoded state at each retained control, including
  KC/KF, operators, pan, modulation, noise and timer controls. Unwritten source
  parameters stay unknown and are not treated as default-value expectations.
- Exact projected target times and end; source timing differences at most six
  samples, separately reported rather than hidden in a score.

The external player inserts initialization controls. A separate minimal MML
is compiled to identify that initializer, which must contain only zero-time
non-Key controls and exactly match the returned VGM prefix before exclusion.
Source controls are never stripped. This explicitly tolerates additional known
compiler defaults where the source state is unknown; it is not a blanket
exemption for any mismatch at time zero.

These checks verify control/state preservation, not waveform equality. Native
Segments do not simulate envelope phase, acoustic level, timer expiry or
CSM-generated attacks; preserved controls do not prove these sound identical.

## Committed regression evidence

Nine newly authored public fixtures have externally generated replay VGMs in
`tests/fixtures/public/opm/mdx_roundtrip/`. Unit tests compare these returned
Segments without requiring Rust, including negative cases for missing/extra
keys, wrong pitch, timing, operator state and compiler initialization.

```bash
python -m unittest discover -s tests -p 'test_opm*.py' -v
```

For the initial register-replay measurements and limits, see
[the roundtrip record](../field_notes/2026-10-04_opm_mdx_roundtrip.md).

## Local listening validation (2026-10-04)

The user-requested catalog run and listening files are under
`outputs/opm/mdx_roundtrip/listening_20261004/`. `public/` and `local_only/`
contain per-case evidence and independent result indexes. `listen/` contains
copies of successful MML/MDX/VGM with the original stem as filename, grouped
by the source directory, for manual listening. These generated files and all
private source/returned content remain outside git.

See [the catalog validation record](../field_notes/2026-10-04_opm_catalog_roundtrip.md)
for counts and remaining limits. Clock-incompatible sources have diagnostics,
not misleading playable conversions. VGM song loops still cover one traversal;
MDX replay preserves the OPM controls, not other chips or external PCM samples.

## Channel-separated validation (2026-10-04)

The current default A..H target passed independent replay for all 38 public
inputs plus two short local MSXGRA2S cases, with no missing/extra Key edges or
source-known state differences. Generated MML/MDX/VGM and CSV evidence remain
under `outputs/opm/channel_tracks_20261004/`. See
[the channel-separation record](../field_notes/2026-10-04_opm_mdx_channel_tracks.md)
for scope, counts, scheduling details and remaining limits.

## Structured notes, tones and loops (2026-10-04)

Structured notation is now the default for `opm_to_mdx_mml.py` and the verifier.
Use `--notation registers` to retain the previous register replay output.
`--no-loops` disables finite loop emission while retaining the hybrid note/voice
projection; this allows a comparison with identical notation and line wrapping.

```bash
python scripts/opm_to_mdx_mml.py \
  tests/fixtures/public/opm/from_mdx/nested_phrase_loops/nested_phrase_loops.vgm \
  --outdir outputs/opm/structured/nested_phrase_loops --dump-passes
```

An isolated attack from cleared gates to a fixed operator mask, followed by
an explicit complete KeyOff with no intervening channel controls, can become
an ordinary note. Its four-operator tone must be fully known and losslessly
encodable. Staggered partial Keys, zero-duration pulses, held parameter changes,
missing tone fields, enabled noise, unencodable/reserved bits and unreleased
tails retain register commands. This is a local representability decision,
not a whole-song score or silent fallback to a different timing model.

`@N` definitions deduplicate effective tone/operator-mask snapshots; IDs are
new target IDs, not recovered original MDX voice numbers. The source's current
TL values are stored in the tone, and `@v127` applies zero added attenuation.
Pan comes directly from the original control byte. Native operator bank order
M1/M2/C1/C2 is reordered to MDX text's M1/C1/M2/C2 when writing a tone.

Note names invert the MDX KC table. `D` compensates its five-unit fine-pitch bias
and preserves the original KF byte; it does not invent hardware detuning or
change the source clock. Noncanonical KC or unused KF bits remain raw controls.
Long gates are emitted as explicitly tied notes of at most 256 ticks each;
a long plain `%N` note could otherwise compile into unwanted retriggers.

## Segment-derived source loops (2026-10-05)

Source structure is built before MDX note spelling, voice assignment or target
loop emission. `py/opm_loops.py` groups immutable native Segments per chip/ch.
A rising operator Key edge, held/released gate transition or source timing gap
delimits a musical unit. Released means gate-off, not proven silence. Every
original Segment stays a member; no source time/state is rewritten.

The source equality key includes exact sample duration, relative time, complete
operator/channel/shared state, explicit rising/falling Key masks and retained
reset/timer effects. Native IDs, absolute origin and target spelling do not
participate. Source `SourceLoopPlan`/`LoopStructure` finds outer phrases and
inner Segment trajectories without a default nesting cap.

Zero-duration released setup does not add a musical rest leaf. Its original
rows remain attached to the preceding unit (or initialization), with full
state keys in the inner plan. Outer held-note equality compares sounding
states and explicit end Key edges, rather than inactive same-sample pitch
setup. Zero-duration Key attacks remain distinct units. Test/reset/timer
controls are not absorbed by this setup grouping. Positive released intervals
retain complete state, including possible release tails.

Only afterward does projection map MDX units to source members. An ordinary
note may absorb same-time KC/KF setup and its terminal KeyOff. Mapping cannot
cross another source phrase/Key boundary; ambiguous mappings keep flat target
commands and report the reason. The target comparator can also decline a
source repeat when generated commands differ. Expanding every emitted bracket
must exactly reproduce the unlooped target tokens. Reference MML validates
structure but supplies no production phrase, tempo or tone choices.

No length normalization, macro extraction or source-tail inference is used.
For the authored `[[c d e g]2 r8]3` fixture, export merges the last phrase delay
with the song tail. The native outer intervals therefore differ at the end.
Source-derived output retains the inner repeat and two-level hierarchy but
emits a separate remaining region, rather than inventing a third identical
outer interval. This is inspectable in the integrated Segment loop paths.

With `--dump-passes`, additional artifacts are:

| Artifact | Meaning |
|---|---|
| `<stem>.mdx.structure.units.csv` | Track/unit ID, target times, kind, tone ID, note spelling, commands, source event/Segment IDs and loop path |
| `<stem>.mdx.structure.voices.csv` | Reconstructed tones in native bank order with operator mask |
| Native `<stem>.opm.segments.csv` | All channels together, with phrase IDs and complete source loop paths plus target mappings |
| `<stem>.mdx.structure.plain.mml` | Identical hybrid notation before bracket emission |

The native Segment CSV additionally appends `mdx_unit_ids`, `mdx_voice_ids` and
`mdx_loop_path`; existing source fields and sample boundaries remain unchanged.
Time-only target slices also point to the native intervals they cover. One
native Segment can consequently belong to multiple target units.

Ordinary notes and tone selection expand into additional register writes, so
structured validation uses a separate `hybrid_effective_state` comparison:

- Exact ordered rising/falling operator masks and projected times per channel;
  channel/operator Key counts and missing/extra counts remain separately reported.
- All source-known raw and decoded values at the union of projected source and
  returned target-time boundaries, including held intervals and released tails.
  Multiple controls within one target tick are compared by their final state.
- The same independently measured compiler initializer and exact projected end.

This deliberately permits duplicated tone/pitch writes and different coincident
control ordering. It is not an exact raw-write sequence test or waveform proof.
The stricter register-replay comparison remains available and unchanged for
`--notation registers`. State mismatches, missing/extra edges and retimed edges
are failures in the structured comparison; no weighted score hides them.

The 2026-10-05 source-driven version passed all 38 public inputs and two short
local inputs. This verifies projection after independently defined source
rules; passing final output alone is not the rationale for those rules.
Measurements and limitations: [source-loop record](../field_notes/2026-10-05_opm_source_loops.md).

Common MDX controls still merge once into A; channel-local controls stay on
A..H. Neither native traces nor the integrated Segment CSV are split into
control/channel streams. Target structural plans are internal objects.
