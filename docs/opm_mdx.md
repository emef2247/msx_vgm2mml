## Historical MDX tooling scope

MDX tool commands below are retained as historical/reference context. These
scripts and their external toolchain are no longer shipped here; use
x68k_vgm2mml for MDX generation, compilation and inspection.

# Musical OPM Segment to MDX MML

The default native OPM target builds musical notes from Key edges, retains each
note's complete pitch/volume/control trajectory, and emits channel tracks A..H.
It uses the shared MGSDRV `SourceLoopPlan` / `LoopStructure` machinery before
removing redundant target setters. Native traces and the integrated Segment CSV
are unchanged; interpreted units belong to the target stage.

## Conversion and compatibility

```bash
python scripts/opm_to_mdx_mml.py \
  tests/fixtures/public/opm/from_mdx/held_controls/held_controls.vgm \
  --outdir outputs/opm/musical/held_controls --dump-passes
```

A fresh output directory contains only `<stem>.mdx.mml` without `--dump-passes`.
Dumping keeps the raw/state/Segment evidence and every new target pass described
below. Existing artifacts are not deleted. Inputs are never overwritten.

`--notation structured` is the new default. `--notation legacy` retains the
previous fixed-@t255 hybrid renderer, and `--notation registers` retains raw
register replay. `--no-loops` disables source/target bracket emission in either
musical renderer while retaining conservative setter compaction.

This native path requires one 4 MHz YM2151. Unsupported clocks, YM2164 and dual
instances are reported explicitly; the source reader still analyzes them. It
projects OPM only, even when an input also contains PCM/PDX or other chips.
The PSG/SCC-to-OPM conversion in `psg_scc_to_mdx.py` is a separate target path;
this native renderer rebuild does not replace that path or change MGSDRV output.

## Musical interpretation

`py/opm_mdx_music.py` groups a complete rising operator mask through its complete
terminal KeyOff into one note. Internal KC/KF, level and parameter changes stay
inside the note rather than creating new attacks. Notes/rests use standard and
dotted lengths when exact; `%N` remains available for other durations.

A tone definition contains the four operators, algorithm, feedback and operator
mask. Uniform attenuation of carrier operators becomes channel `@v` volume;
relative carrier levels and modulator levels remain in the tone. An independent
operator edit remains an explicit control. Volume inference must reproduce all
four TL values, not merely an estimated loudness. Tone IDs are assigned by the
target; original MDX voice numbers are not recovered.

Same-time pitch/tone setup immediately before an attack can be absorbed into
the note and tone definition. Its source IDs, register order and complete state
remain in the unit CSV. Pan, modulation, test/timer effects and unrepresentable
parameter changes retain explicit controls. Shared controls are emitted once on
A; channel/operator/KC/KF/Key controls belong to A..H, and noise to H.

Only actual held continuations use ties. Ties may be needed around an internal
control update or to encode a note longer than MDX's 256-tick note limit; they
never join independent source attacks. Partial or reserved Key transitions,
zero-duration attacks, unknown tones/pitches, active noise and missing terminal
KeyOff, and post-Key setup on the same projected tick retain explicit controls
with a named fallback reason. These are visible
exceptions, not a silent whole-song fallback.

## Reversible structure and compaction

Each track's source-derived equality keys include complete native state,
relative projected times, ordered retained controls and note/release identity. Outer
phrases and internal held/released trajectories are structured with the shared
MGSDRV loop planner. Source detection does not use target text lengths and has
no artificial nesting cap. Unique source leaves and periodic regions use exact
separators/closed forms with the same full candidate catalog and selected tree;
these are computation reuse, not search restrictions. Rendered commands must
still agree before a bracket
is emitted, and expanding every emitted loop must reproduce the unlooped tokens.

Source structure precedes target compaction. Redundant voice/volume/pan/gate/
detune/octave setters are omitted conservatively. Raw operator writes invalidate
voice-related reuse; first setters at loop entries are retained for back edges.
Long rest chunks and tied note chunks can become finite duration loops. Target
repeat counts are split at 255; the external compiler's nesting limit is distinct
from source structure. No events are dropped to fit the MDX offset limit.

Named phrase macros and software LFO parameter recovery are not implemented in
this pass. MDX MML dialects such as NOTE support named macros, but the selected
mmlx 0.2.0 grammar supports bracket repeats without named macro definitions or
calls. Macro extraction and compiler-dialect support are separate next stages;
current output is structured loops followed by conservative compaction.
Observed modulation remains a source-linked trajectory, with internal loops
where exact repetition exists. This is structured score reconstruction, not a
claim to recover the author's exact MML syntax or original editing decisions.

## Timing and metadata

Source `vgmticks` remain absolute integer samples at 44100 Hz. A target clock
candidate has period `256 * multiplier` microseconds and emits
`@t(256-multiplier)`. A coarser clock is accepted only when **every** observed
control boundary and the common song end stays within the existing six-sample
fine-clock resolution, and no positive observed interval is collapsed.

All safe candidates are retained in `score_clock_inference`. Conventional note
values and proximity to quarter=120 choose notation among safe candidates;
they cannot waive an inaccurate boundary. Tempo is inferred, not asserted to be
the original score marking. Absolute projection avoids accumulated gap error.
The fine @t255 fallback retains ordered sub-tick controls and reports collapses.
There is no optional length normalization or source timestamp rewrite here.

A single inferred clock need not recover original tempo changes. Multiple score
clocks can describe the same performance; original MDX tempo-byte equality is
therefore reported separately from projected performance correctness.

Title comes from Japanese/English GD3 track metadata, or the filename when absent.
`--title "..."` overrides it. Reference MML/MDX is never read by conversion to
fill absent metadata, choose tempo, construct voices or discover phrases. A
reference title cannot be recovered from a VGM that does not contain it.

## Inspectable passes

| Artifact | Meaning |
|---|---|
| `<stem>_trace.opm_regs.csv`, `<stem>_trace.opm.csv` | Ordered source writes and reconstructed native state |
| `<stem>.opm.segments.csv` | All channels together; unchanged native cells plus `mdx_music_unit_ids` |
| `<stem>.mdx.controls.csv` | Source IDs/samples, target ticks, projected samples, errors, registers and track ownership |
| `<stem>.mdx.structure.units.csv` | Note/rest/control units, native and target boundaries, complete trajectory, source membership, folded/unlooped commands and outer loop paths |
| `<stem>.mdx.structure.voices.csv` | Effective tone definitions in native bank order |
| `<stem>.mdx.structure.<track>.loops*` | Source structural plans, all members and target fold decisions |
| `<stem>.mdx.structure.inner_loops.csv` | Internal trajectory repeat decisions with parent unit and track |
| `<stem>.mdx.structure.plain.mml` | Flat musical spelling before any loop emission or setter compaction |
| `<stem>.mdx.structure.uncompacted.mml` | Source-loop projection before setter/duration compaction |
| `<stem>.mdx.structure.compaction.csv` | Every target omission/rewrite and reason |
| `<stem>.mdx.timing.json` | Clock evidence, timing error, note/fallback/voice/loop counts and MML sizes |

Unit trajectories retain observed states and timestamps, including zero-time
setup. Released means KeyOff, not proven acoustic silence. Native event IDs
remain the bridge from output commands back to the integrated source CSV.

## Independent roundtrip validation

Build the development-only mmlx/soundlog helper if needed:

```bash
cargo build --release --locked --manifest-path scripts/mdx_fixture_generator/Cargo.toml
python scripts/verify_opm_mdx_roundtrip.py tests/fixtures/local_only/opm \
  --reference-mml-only --outdir outputs/opm/regression/musical_reference
```

`--reference-mml-only` selects inputs with a same-stem MML under `reference/`.
It does not use that MML as a conversion oracle. Remove it for a complete catalog
scan. `--generator /path/to/mdx-fixture-generator` selects an external binary.

The verifier retains MML, compiled MDX, returned VGM, both native analyses,
compiler logs, per-case comparisons and incrementally updated results CSV/JSON.
Compiler failures/timeouts retain generated MML and diagnostics. Its replay
budget derives from the projected song end, rather than clipping long inputs.

Structured verification checks ordered rising/falling masks and projected times
per channel, missing/extra Key counts, all source-known raw/decoded states at the
union of source/returned boundaries, and exact projected end. Unknown fields
remain unknown. Multiple writes at one target tick are compared by their final
state; this is not an exact same-time register-order or waveform test.
The compiler's separately measured zero-time non-Key initializer is accounted
for explicitly. `--notation registers` keeps the stricter retained-write test.

### External reference MDX metadata audit

Build/install `mdxdump` from [mdxtools](https://github.com/vampirefrog/mdxtools)
separately, then add `--mdxdump /path/to/mdxdump` to the verifier. Its external
stdout/stderr is retained for both original reference MDX and generated MDX.
`metadata/metadata.json` reports title, PDX name, encoded tempo commands and
command categories, plus whether generated title/tempo are visible in the MML.

An individual audit is also available:

```bash
python scripts/audit_mdx_metadata.py reference.mdx returned.mdx generated.mml \
  --mdxdump /path/to/mdxdump --outdir outputs/opm/metadata
```

Reference-title and tempo-byte differences are separate fields, not a weighted
quality score. Encoded command counts are not expanded note/performance counts:
for example, an explicit volume trajectory may replace a software volume-LFO
command. Metadata-tool failure is recorded separately from compilation and Key/
state comparison. PCM/PDX is outside this OPM projection even when the reference
MDX contains it.

These checks establish inspectable target behavior, not acoustic equivalence or
MMDSP display behavior. User listening and hardware checks remain independent.
Earlier register/channel/hybrid experiments are recorded in the dated
2026-10-04 and 2026-10-05 OPM field notes. The musical rebuild and reference-set
results are in `field_notes/2026-10-07_mdx_musical_output.md`.
