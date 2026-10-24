# Inferred OPLL drum enhancement

`--enhance-drums` adds a heuristic OPLL rhythm accompaniment inferred from PSG
and SCC performance IR. It is disabled by default. Original PSG/SCC parts,
Segments, software envelopes and waveforms are preserved.

```sh
python scripts/export_mgs.py input.vgm --outdir outputs/drum_trial --enhance-drums --dump-passes --skip-keyon-counts
```

The same switch is accepted by `vgm2mml.py` and `scripts/batch_vgm_to_mgs.py`.
The export entry retains its 24 ms FM-state and 8 ms timing-correction defaults.
This enhancement does not apply either threshold to PSG/SCC control curves.
Compile-only trials can use `--skip-keyon-counts`; added percussion is an
intentional target augmentation, so source/output equivalence is not its oracle.

## Inference

The input is the immutable PSG/SCC PerformanceIR, before target projection.
Source-audibility gates can be subdivided at strong volume rises, hardware-
envelope resets or transitions into noise. Arbitrary pitch writes do not split
hits. Same-sample setup is kept with its effective sounding state. Unknown source
sample timing causes abstention rather than invented timing.

The initial experimental classifier uses these hypotheses:

- Short PSG noise gestures: HH up to 80 ms, SD up to 220 ms, CYM up to 350 ms.
- Monotonic downward pitch sweeps of at least three semitones, with a decrease of
  at least three fixed-volume levels, lasting at most 250 ms: BD for a low-pitched final
  tone (period at least 512), otherwise TOM. This is a period heuristic, not a
  clock-independent physical drum specification.
- SCC: such a pitch sweep, or a decaying broadband waveform. A cached 32-sample
  DFT evaluates spectral flatness and upper-harmonic energy; broadband material
  must cover at least half the observed positive duration. A waveform alone or
  an ordinary decaying pitched note is insufficient.

Long gestures and insufficient evidence remain rejected candidates in the
catalog. PSG hardware-envelope register levels are not observed amplitude
curves and cannot establish tonal decay. Short noise with a hardware envelope
can still qualify; this uncertainty is recorded. Target volume is approximately
2/3 of the peak source level, limited to 1..15. This is an additional level
proxy, not calibrated acoustic loudness. No channel is hard-coded as drums.

These labels are guesses for listening and refinement. A candidate onset is an
inferred gesture boundary, never an observed PSG/SCC Key-On. Effects and noise
melodies can be false positives; actual drums can be missed.

## Target projection

The existing OPLL group/repeat renderer and MGSDRV rhythm track `f` are reused.
Native rhythm has priority over an inferred hit of the same instrument at the
same target time. Duplicate inferred hits retain the stronger level with a
deterministic tie-break. Every omission remains traceable to its candidate.

A static OPLL rhythm layout consumes the last three melody channels. Any native
Key-On with a nonzero frequency on channels 6..8 blocks the whole addition,
including zero-length or muted states as a conservative guard. `--force` does
not override this. Native OPLL rendering is completed first. The mode switches
to rhythm only when projected additional hits actually remain. If every hit is
rejected or blocked, the native mode and target MML remain unchanged.

After accepted timing normalization, additional hits follow actual projected
PSG/SCC note boundaries, not a separately snapped beat grid. Source-time errors
are checked against the same correction tolerance; unmatched boundaries and
unrepresentable intervals are omitted explicitly. Native rhythm uses its
existing retiming/collision policy. All group gaps are rebuilt after merging;
positive final durations and renderer minimum lengths remain enforced.

## Inspection

The option always writes:

- `<stem>.drums.candidates.csv`: accepted and rejected hypotheses, source chip,
  channel, Segment indices, sample/tick bounds, features and reasons.
- `<stem>.drums.projection.csv`: target onset, source timing shift, target boundary
  reference and adopted/omitted/blocked decisions.
- `<stem>.drums.json`: counts, instrument distribution, mode and status.

`--dump-passes` also retains `.drums.before.target.mml` and
`.drums.after.target.mml`, alongside ordinary performance and native pass dumps.
The conversion/batch reports include the enhancement summary. Reruns remove
known old enhancement artifacts so a disabled or failed run cannot expose a
previous addition as current output.

See [performance IR](psg_scc_performance.md), [software envelopes](software_envelopes.md)
and [native OPLL rhythm](opll_rhythm.md).
