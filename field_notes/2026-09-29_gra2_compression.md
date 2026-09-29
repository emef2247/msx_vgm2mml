# gra2_005 compression investigation

The current converter output compiles with MGSC 1.11. Measured used bytes
(including track 0 definitions) are 7859 versus 1755 for the supplied reference.
This is not a like-for-like compression ratio: the reference has macros,
nested loops and infinite song loops, whereas the captured VGM is finite.

| Track | Current used bytes | Note-unit experiment | Reference used bytes |
|---|---:|---:|---:|
| definitions (0) | 553 | 553 | 287 |
| 2 | 887 | 775 | 145 |
| 3 | 2633 | 2274 | 151 |
| 5 | 829 | 829 | 290 |
| 6 | 1016 | 1034 | 280 |
| 7 | 988 | 998 | 324 |
| 8 | 953 | 941 | 278 |
| Total | 7859 | 7404 | 1755 |

The current main pipeline processes SCC before PSG. SCC consumes all 32
shared envelope slots (0..31); PSG uses only the constant @e0 definition.
This makes direct volume changes, particularly PSG track 3, expensive.
Exact duplicate curves already reuse IDs. The problem is not demonstrated
unbounded allocation of identical envelopes from expanded loop copies.

Current Segment-loop candidates are too fine-grained: 1253 SCC candidates
and 125 PSG candidates are rejected at extracted-note boundaries. Blindly
forcing those boundaries before envelope extraction could fragment real notes.

A scratch experiment searches exact repeats of complete extracted-note units
(duration, next-note advance, chip settings, rest state, volume runs). It uses
the same guard that only identical emitted command strings become loops.
It preserves the complete expanded command/time timeline and compiles, reducing
final text 19551 -> 18575 characters and used bytes 7859 -> 7404. Individual
tracks can grow in bytes despite shorter text, demonstrating the need for a
compiled-size cost model. This experiment is not integrated into the converter.

Recommended order:
1. Preserve native Segments and derive complete attack/continuation groups.
2. Detect candidate loops on those groups; select musically safe boundaries.
3. Extract envelope candidates within the selected boundaries; retain source IDs.
4. Allocate the shared bank across PSG/SCC by estimated byte saving, independent
   of chip processing order. Count loop-compressed uses, not just expanded uses.
5. Finalize state-safe loops, then assess nested repeats and optional macros.

Do not automatically infer infinite loops or import the ROM reconstruction as
if its control flow were directly observable in the VGM. gra2_001 was not
changed or analyzed in this first short-fixture investigation.
