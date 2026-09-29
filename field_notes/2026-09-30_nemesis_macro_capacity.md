# NEMESIS2 generated MML: macro capacity experiment

Measured the user's existing outputs/vgmrips.net/NEMESIS2/gen files with
MGSC 1.11 via mgsc-js 2.0.0. These are supplied outputs, not freshly regenerated
converter results: GRA2_03 still contains the previously fixed m0 command.
Do not interpret these numbers as measurements of the latest converter.

17 originals: 9 compile, 4 fail track capacity (04/08/09/10), 3 exceed wrapper
source length (01/13/16), and 03 fails invalid parameter. All five supplied mod
files compile, but their channel timelines are shortened. They are not lossless
compression references.

Using the previous bounded prototype (32 macros, 4..24 complete nodes,
definitions <=180 characters), tested 01/04/08/09/10. Expanded token text and
start/end steps match compact input for every track. No source material changed.

| Song | Compact characters (LF) | Macro characters (LF) | Track bytes, both |
| --- | ---: | ---: | ---: |
| 01 | 55644 | 36243 | 42444 |
| 04 | 24454 | 17142 | 19258 |
| 08 | 19364 | 11519 | 13245 |
| 09 | 27810 | 18193 | 19009 |
| 10 | 20892 | 12923 | 14808 |

Byte totals were measured by compiling tracks individually with allocation
15000, preserving definitions and macro definitions. They exclude definition
track 0. Every individual track's used bytes are identical before/after macros.
Macros help source length, but did not solve compiled track capacity here.

08 and 10 successfully compile as COMPLETE songs after changing ONLY #alloc
in the original gen text, preserving the 15000 total track allocation. Allocate
each track its measured usage, then distribute remaining bytes evenly.
08 uses 13937 total bytes including 692 definition bytes; 10 uses 15591 total
including 783 definition bytes. The user budget is 15000 for tracks, with the
separate default 1016 definition allocation, consistent with existing output.

Next implementation priority: compiled-byte-aware allocation (08/10 demonstrate
avoidable failures), followed by actual byte savings for 01/04/09. Retain macro
compression as a source-size/readability option, not a buffer-full remedy.
Regenerate with the current converter before selecting further optimization
targets. Do not remove musical content or increase the track budget silently.

Local experiment artifacts are in the Codex workspace work/nemesis-audit:
baseline.json, macro-results.json, compact/macro MML and logs, and complete
GRA2_08.reallocated.mml / GRA2_10.reallocated.mml. Private MML is not committed.
