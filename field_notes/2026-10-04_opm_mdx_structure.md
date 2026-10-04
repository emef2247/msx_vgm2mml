# OPM MDX notes, reversible loops and logical streams

Date: 2026-10-04. Implementation/measurement record; not an acoustic equivalence
claim or a cross-chip voice conversion rule.

## Output and preservation policy

After channel separation, the default MDX output now combines ordinary notes,
reconstructed `@N` tone definitions and exact nested loops with raw `y` controls
where ordinary notation cannot preserve source behavior. Fixed-mask attacks
with complete known tones and an explicit isolated KeyOff are eligible. Held
parameter changes, partial Keys, zero-duration pulses, unknown patches,
reserved/unencodable bits, enabled noise and unreleased tails retain controls.
Long notes use explicit tied chunks of at most 256 MDX ticks to avoid compiler
splitting into extra attacks. Tone text uses M1/C1/M2/C2 rather than native
bank order M1/M2/C1/C2; source TL values and zero-added-attenuation `@v127`
preserve levels. KC/KF are inverted through the target note table, including
its fine-pitch bias. These are target choices; native timing/state is unchanged.

Existing reversible `SourceLoopPlan`/`LoopStructure` machinery is reused.
Expanding emitted loops must reproduce the original target command tokens.
There is no nesting cap, approximate phrase matching, length normalization or
macro extraction in this MDX path. A repeated delay prefix can be separated
from a combined final delay without changing total time, restoring a phrase
loop hidden by export's merged tail.

## Independent roundtrip results

The external existing mmlx-based helper compiled each generated MML to MDX,
played it to VGM, and the native reader rebuilt OPM state/Segments.

| Set | Cases passed | Channel attacks source/returned | Operator KeyOns source/returned | Operator KeyOffs source/returned |
|---|---:|---:|---:|---:|
| Public |38/38|357/357|1377/1377|1208/1208|
| Short local MSXGRA2S |2/2|125/125|440/440|424/424|

All missing/extra counts and source-known state mismatches were zero. Per-channel
ordered operator edge masks/times and projected end positions matched exactly.
Source-to-target time projection differed by at most 6 VGM samples for public
inputs and 0 for these local inputs. This is not sample-exact source timing.

Ordinary notes/tone selection generate extra raw writes: public controls grew
from 8572 retained source controls to 12234 returned controls; local controls
from 2625 to 6886. Thus structured validation uses an explicit separate effective
state/Key-edge comparator at the union of projected state boundaries. Within
one target tick it compares final known state, not every intermediate raw write
order. The strict register-replay comparator remains available unchanged with
`--notation registers`. There is no rendered waveform or hardware comparison.

| Example | Hybrid flat MML chars | With loops | Reduction |
|---|---:|---:|---:|
| Public nested_phrase_loops |1560|842|46.0%|
| Local M_G2_17S |10745|10426|3.0%|
| Local M_G2_18S |19956|11156|44.1%|

Size comparisons use identical hybrid notation and wrapping before/after loops.
The public authored `[[c d e g]2 r8]3` yields two physically emitted nested
loop commands and maximum depth 2. Projection-occurrence counts can include
multiple executions of an inner loop and must not be confused with physical
bracket counts. Local 17S has 108 note units/12 tones; local 18S remains raw
controls but can still use exact loops. A no-loop public roundtrip also passed.

Artifacts: `outputs/opm/structured_20261004/`, including per-case final MML,
plain MML, returned MDX/VGM, native state/Segment CSVs, target units/tones/loop
hierarchy CSVs, comparison/timing JSON and compiler logs. Source/reference
fixtures are unchanged; private fixture contents are not reproduced here.

## Superseded experiment

The proposed source-stream partition and extra streams.csv were withdrawn
after user clarification. The native Segment engine and integrated CSV are
the established input. Musical/control separation belongs to target structure;
it does not justify reorganizing the earlier source pipeline.

The loop comparison described above used generated target-command units.
It is superseded by independently defined Segment-derived phrase and inner
trajectory plans; see field_notes/2026-10-05_opm_source_loops.md. The earlier
measurements remain historical, not current source-loop compression figures.
Do not use successful final roundtrips to justify an unexplained source
interpretation. All-channel self-contained CSV inspection is a requirement.
