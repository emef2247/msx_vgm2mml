# Project knowledge consolidation

## Scope and authority

Compared the user's slimmed `docs/project_knowledge.md` with
`docs/project_knowledge_legacy_2026-10-05.md`. The new document is the principles
source of truth. Both files are left unchanged; this is selective preservation
of useful details, not restoration of the old document.

Only documentation is added. No code, tests, fixtures, generated artifacts or
handoff files are changed by this task. Existing uncommitted OPM implementation
work is separate. No compiler, conversion or regression is run for this review.
Historical measurements below are carried forward with their original scope.

## Knowledge worth extracting

| Legacy material | Destination and reason |
| --- | --- |
| OPLL target voice/note correction; octave and voice-number verification | [MGSDRV melodic projection](../docs/mgs_melodic_projection.md): register decoding, WF/comment trap, ROM versus MML IDs and octave convention were not adequately documented elsewhere. |
| Relative melody notation | Same document: emitted-state basis, rest deferral and one-step relative setters are useful implementation constraints. |
| Continuous OPLL target gate spelling | Same document: preserves the `&` plus `q0`/`q8` compiler observation; links existing key/envelope evidence rather than duplicating its investigation. |
| Long-envelope preference and shared selection | [Software envelopes](../docs/software_envelopes.md): shared bank, priority, exact observed-prefix reuse, inline fallback and report paths. Existing pattern docs already cover Segment assignment IDs. |
| Grider export-tail observation | Retained below as a scoped playback observation, not a converter rule. |

Current code was read only to distinguish implemented behavior from old proposals.
For example, the envelope policy is duration-first, not an implemented optimal
saved-byte allocator, and structural/default reports differ from legacy-bank
reports. The new documents label those limits explicitly.

## Already adequately recorded: no duplicate migration

| Topic omitted from the new principles document | Existing record |
| --- | --- |
| PSG/SCC Segment fields, SCC five-channel handling and header offset correction | [PSG/SCC Segments](../docs/psg_scc_segments.md); [SCC clock observation](2026-09-26_scc_fixture_clock.md) |
| Proposed common/optional semantic fields and MS2/source-target separation | [Intermediate requirements](../docs/segment_intermediate_format.md); new principles sections 3, 5, 9, 13 and 16 |
| Shared synchronization boundaries, loop preservation and spacing | [MML synchronization](../docs/mml_sync.md); [macro compression measurement](2026-09-29_macro_compression.md) |
| Rhythm edges, groups, pattern equality, notation, tails and collision approximation | [OPLL rhythm](../docs/opll_rhythm.md); [zero-length events](2026-09-30_opll_zero_length_events.md) |
| Driver-frame measurement versus 60 Hz assumptions | [MGSDRV/libkss timing](2026-09-28_mgsdrv_libkss_timing.md) |
| Melody/performed patterns and integrated pattern/envelope IDs | [Melody patterns](../docs/melody_patterns.md) |
| PSG/SCC actual periods, tuning and signed detune | [Register-period review](2026-09-29_psg_scc_periods.md); [pitch roundtrip](../docs/pitch_roundtrip.md) |
| Key edges versus inferred onset; maximum attenuation and rejected coalescing | [OPLL key/envelope review](2026-10-01_opll_key_and_envelope.md); [Alest202 evaluation and withdrawal](2026-10-01_alest202_retrigger_check.md) |
| Key-On totals and count-comparison limits | [Key-On counts](../docs/opll_keyon_counts.md) |
| Declared VGM loops, gzip signature, offsets and shared wait clock | [VGM loop metadata](../docs/vgm_loop.md); [loop observations](2026-10-01_vgm_loop_metadata.md); [VGM timing](../docs/vgm_timing.md) |
| Source-inferred duration normalization and reference repetition audits | [Note normalization](../docs/note_normalization.md); [sample timing audit](2026-10-02_sample_vgmticks.md); [normalization benchmark](2026-10-02_note_normalization_benchmark.md) |
| Reversible source structure, overlapping alternatives and unrestricted detection depth | [Melody patterns](../docs/melody_patterns.md); [reversible structure](2026-10-03_reversible_loop_structure.md); [depth validation](2026-10-03_gra2_005_unrestricted_depth_validation.md) |
| Default/legacy compression, static OPLL layouts and stale UTF-8 titles | [Compression/mode/title findings](2026-10-03_default_compression_opll_mode_titles.md); [structured macros](../docs/structured_macros.md); [batch usage](../docs/batch_mgs.md) |
| PSG/SCC loop-first selection and continuous OPLL inner loops | [Melody patterns](../docs/melody_patterns.md); [pre-envelope experiment](2026-10-03_psg_scc_pre_envelope_structure.md); [OPLL inner-loop validation](2026-10-03_opll_inner_loop_validation.md) |
| Native OPM input and first MDX control projection | [OPM Segments](../docs/opm_segments.md); [MDX projection](../docs/opm_mdx.md); [native input findings](2026-10-04_opm_native_segments.md); [initial roundtrip](2026-10-04_opm_mdx_roundtrip.md) |

The recent [OPM source-loop record](2026-10-05_opm_source_loops.md) also documents
the current per-channel MDX structure. It supersedes the legacy statement that
OPM musical notation and compression are future work; that stale statement is
not transferred as current guidance.

## Historical playback-tail observation

The earlier grider reference ended in an infinite repeat without an explicit
fade. Its inspected VGM had no declared loop and ended at 121.948390 seconds,
19 samples after the last chip write. A user screenshot suggested a fade or
release tail in an exported WAV, but did not establish its source.

This is a historical observation about that capture, not a general export rule
or an acoustic diagnosis. Export/player end handling remains a possible cause.
No automatic fade or inferred tail padding was justified. If the question
returns, inspect captured end time and playback/export policy separately before
changing Segment durations or target gates.

## Material intentionally left in the archive

- General principles and workflow examples already covered by the new source
  of truth are not copied into another principles document.
- The approximate OPLL volume-step/dB remark lacks sufficient provenance in
  the legacy text to establish a calibrated cross-chip loudness mapping. Source
  attenuation semantics are retained in the new principles; this estimate is
  not promoted to a conversion formula.
- Old test totals and intermediate-stage completion claims are not current
  acceptance criteria. Relevant benchmark records remain in their existing notes.
- The old two-level nesting cap, six-melody-only OPLL target limit and
  identical-state-only rhythm-collision rule were superseded. They remain
  historical evidence, not instructions for restoring those restrictions.
- Proposed base-volume envelope families and compiled-byte-optimal selection
  are not claimed as implemented. Preserve such questions as proposals, not
  production behavior.

The legacy backup remains available for archaeology. Future implementation work
should start with the slim principles and the relevant focused document, rather
than treating every dated legacy paragraph as equally authoritative.
