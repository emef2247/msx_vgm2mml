# Structured macro follow-up on five fixtures (2026-10-03)

## Method

Converted exactly es59, es56, Alest202, FRAY02 and SORCER02 through the conventional default pipeline with pass dumps. Enhanced those same merged MML files, without duration normalization, structural-loop experimental overrides or allocation overrides. Compared exact expanded timed-command streams. Compiled both variants with local mgsc-js 2.0.0 / MGSC 1.11. Complete outputs/logs remain private in Codex `outputs/structured-macro-followup`.

| Input | Baseline characters | Enhanced characters | Reduction | Baseline compilation | Enhanced compilation |
| --- | ---: | ---: | ---: | --- | --- |
| es59 | 28807 | 22645 | 21.4% | Track buffer full | Track buffer full |
| es56 | 91612 | 80861 | 11.7% | Source too long | Source too long |
| Alest202 | 23633 | 19390 | 18.0% | Track buffer full | Track buffer full |
| FRAY02 | 42769 | 34200 | 20.0% | Track buffer full | Track buffer full |
| SORCER02 | 52659 | 51859 | 1.5% | Source too long | Source too long |

All enhanced variants preserve their baseline's expanded timed commands, but none passes compilation under unchanged allocation/settings. Character savings therefore do not meet the full acceptance objective yet. This is not an audio roundtrip or source-VGM fidelity certification.

`Source too long` is the installed mgsc-js wrapper's pre-compiler check on Shift-JIS encoded input above 49152 bytes. It must be distinguished from MGSC's per-track buffer exhaustion. SORCER02 remains above this threshold; the 32-definition bounded macro allocation gives only a small source reduction. Improving source macros alone does not necessarily reduce compiled track bytes.

## Discovered long-definition formatting defect

Initial enhanced es59 gave Undefined Macro rather than the underlying capacity failure. Some definitions occupied more than 255 characters on one physical line. Reformatting definition whitespace to lines <=120 characters removed the Undefined Macro diagnostic; compilation then reached Track buffer full. Do not infer the precise MGSC line limit from this experiment alone.

`structured_macros.emit` now wraps definitions at word boundaries. A regression test verifies both line length and expanded macro call contents. Existing generated definitions have single spaces, so substituting separator spaces with newlines preserves character count exactly. All five selected artifacts were reformatted using that rule, equal counts and expanded streams were asserted, and all compiler logs were refreshed. No expensive search rerun was needed because the complete candidate cost remains unchanged by this wrapping.

## es59/es56 reference MML analysis

The user restored the original MML alongside each VGM. Both original MML files compile successfully. Original syntax counts are:

| Reference | Characters | Macros | Physical loop brackets | Channel loop instances | Maximum depth |
| --- | ---: | ---: | ---: | ---: | ---: |
| es59 | 3061 | 3 | 44 | 74 | 2 |
| es56 | 3535 | 5 | 50 | 76 | 3 |

Grouped track declarations share source text. Each has one outer infinite loop applied to 12 tracks, counted as 12 channel instances. es59 has 62 finite channel loop definitions; es56 has 64. The reference macros are compact drum articulations reused under changing default lengths, octave/volume and instrument/envelope controls. es56 includes inner short rhythms inside larger repeated phrases. Common finite body lengths include 96/192 score steps in es59 and 192/768 in es56 (quarter=48). A local score audit resolved macro_offset aliases and inspected one pass of infinite loops; it does not certify timing or audio equivalence.

Enhanced es59 and es56 both exhaust the current 32 macro slots. Their physical track-plus-definition loop counts are 241 and 1607, versus baseline 258 and 1463; maximum physical depth remains 2. These are syntax counts, not musical quality measures: macro extraction moves or duplicates stored bracket syntax, and effective nesting through macro calls differs from written bracket nesting. Source references use grouped tracks, musical defaults, performance controls and outer infinite loops; captured finite VGM events are not equivalent source syntax. Comparing raw character ratios alone cannot isolate missing authored loops.

## Separate pre-existing fidelity limitation

Both references use #opll_mode 0 and all nine OPLL melody tracks 9..h. Current target renderer iterates range(6), and merged output declares #opll_mode 1. Both baseline and enhanced outputs contain only six OPLL melody tracks 9..e. Segment CSVs retain channels 6..8, with key_on_edge totals es59=489/489/381 and es56=463/463/537, so these are active source channels omitted during MML projection. The macro enhancer preserves this existing incomplete baseline; its equality check cannot prove source fidelity.

Nine-channel non-rhythm projection should be addressed separately before using these fixtures as complete listening references. This follow-up did not alter voice allocation, channel routing or rhythm mode. Source references were not injected into conversion.

## Next implications

Better macros give meaningful source savings on four fixtures, but richer phrase loops and target performance-control representation remain important for compiled capacity. Before optimizing es59/es56 further, distinguish their missing channels from compression. SORCER02's limited exact reuse is a useful stress case for later selective loop expansion and alternative macro allocation; a larger search alone is not established as the solution.
