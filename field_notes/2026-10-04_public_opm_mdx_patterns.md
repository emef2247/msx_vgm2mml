# Original public OPM MDX patterns (2026-10-04)

The user requested publishable test data independent of the private MDX
collection. Nine short original MDX MML scenarios and two original synthetic
operator-parameter tables were written for this repository. No commercial
music, extracted patch tables, private MML or PCM data was used. Sources and
generated data follow the repository MIT license.

Location: tests/fixtures/public/opm/from_mdx. Each case has its source MML,
compiled reference MDX and input VGM. The manifest records versions, hashes,
and authored attack expectations. The existing from_fm set is preserved.

Generation: mmlx0.2.0 compiles MDX MML; soundlog0.15.0 generates a 4MHz YM2151
VGM with one song traversal. A separate Rust helper and Python wrapper retain
this reproducible development workflow without adding compiler dependencies
to the Python conversion engine. No mml2vgm code was used.

Coverage: eight FM channels/pan, partial operator keys, held pitch/patch/TL
and pan changes, hardware LFO/sensitivity/reset/independent AMD and PMD,
channel7 noise, same-sample off/on/nochange, positive release gaps, individual
operator register banks, and two-level finite phrase repetition.

The nine cases contain 56 channel attack events and 212 operator KeyOns/
KeyOffs. Source/Segment Key counts and interval continuity agree. Twenty-two
OPM tests passed (nine new fixture checks plus thirteen previous checks).
All MML/MDX/VGM hashes stayed identical after regenerating the data a second
time. Generated traces/state/Segment CSVs and results are retained locally
in outputs/opm/from_mdx.

This validates observable source controls, not acoustic equivalence or
Segment-to-MML rendering. Shared hardware LFO/noise state is preserved but
its waveform/audio effects are not simulated. The future MDX MML output
stage can use these original sources for controlled roundtrip tests. Keep
chip-specific controls distinct from common note/phrase patterns when
adding OPN/OPNA fixtures.
