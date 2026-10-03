# Default compression, OPLL layout and title encoding (2026-10-03)

## Default policy

The CLI now enables structural OPLL source-loop projection and enhanced macros. --legacy-loops and --legacy-macros independently restore prior compression. The rhythm/channel correctness fix and CP932 output remain active under those options. --enhance-macros remains a compatibility alias for the new default. Batch forwards legacy controls. Duration normalization remains opt-in; its nine-channel renderer and loop selection follow the selected policy too.

The macro allocator's ancestor-overlap check now indexes selected parent ranges rather than scanning every earlier occurrence. Reconstructed es59 output is byte-identical after this change. This improves search cost without changing selection. Its full nine-channel macro comparison still took about 204 seconds locally; large regression cases may need an explicit --timeout value above the batch default of 300 seconds.

## OPLL mode correction

Infer the static MGSDRV layout from trace rhythm activity and final mode state. A startup-only enable followed by disable (es59/es56) does not mean the composition uses rhythm. No-rhythm output uses mode0 with nine melody channels; rhythm output uses mode1 with six melodies plus rhythm. High-channel voice assignment, target rendering, diagnostics, normalization, macros and allocation now include channels f/g/h when appropriate.

A synthetic nine-channel VGM passed conversion and MGSC compilation, with all nine tracks present. sample remained mode1, both new default (4913 chars) and legacy compression (6333 chars) compiled successfully and expanded timed commands agreed. es59 now includes all twelve sounding PSG/OPLL tracks and has 50150 characters; mgsc-js's 49152-byte input cap still prevents compilation. Do not compare this size directly with the previous incomplete six-channel output as a compression regression.

MGSDRV chooses one static mode in its header. Arbitrary audible mid-song alternation between nine melodies and rhythm remains a separate representation problem; this update corrects whole-song layout selection and transient initialization.

## Title investigation

Inspected the saved outputs/mgs/opll binaries. FRAY01, FRAY12, ThBSMS02/03/04 and YsSMS01/02 contain UTF-8 title bytes. The newer, correctly displayed FHAWK01/02 (under FIREHAWK locally) and SORCER01/03 contain CP932 title bytes. Older normalize-lengths binaries for even the good fixtures also contain UTF-8. The observed distinction is generation history, not an unsupported source-specific character.

For all eleven sources, generated current GD3 titles, wrote CP932 MML, and compiled minimal one-note probes with local MGSC1.11. Every MGS title, extracted from offset8 to the CRLF terminator, exactly equals the intended CP932 byte string. These are metadata probes, not full-song conversions or MSX hardware display tests. Detailed private report/artifacts are in Codex outputs/default-compression-mode/titles.

Existing title conversion code was already correct and was not changed. Regenerate old MML and MGS using the current batch path; avoid editing binary headers in place because title length precedes the binary payload. The upcoming regression should replace earlier UTF-8 artifacts.

## Validation

Target, normalization (including channel h and structural loops), mode inference, macro, batch forwarding, GD3, public conversion baseline and rhythm-pipeline tests passed. Default/legacy sample command equivalence and real compiler checks passed. No full local catalog regression was run; the user will run it next.
