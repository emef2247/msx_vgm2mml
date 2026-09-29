# PSG/SCC pitch roundtrip verification

Use existing reference `<stem>.psg.segments.csv` and `.scc.segments.csv` without
regenerating or editing them. The runner generates MML from the input VGM,
compiles with MGSC, exports VGM through libkss, and dumps actual Segments.

Install optional Node dependencies in a separate directory, for example:

```sh
npm install --prefix /tmp/mml-verifier mgsc-js@2.0.0 libkss-js@3.0.0
python scripts/verify_pitch_roundtrip.py path/to/song.vgm \
  --reference path/to/reference --outdir outputs/pitch/song \
  --mgsc-module /tmp/mml-verifier/node_modules/mgsc-js/dist/index.js \
  --libkss-module /tmp/mml-verifier/node_modules/libkss-js/dist/index.js
```

The tested local versions are MGSC-js 2.0.0 and libkss-js 3.0.0. They do not
prove identity with the deployed msxplay.com emulator version. Record versions
when sharing results; msxplay's public package currently specifies libkss ^2.2.1.

Outputs: `generated/`, `rendered/`, `actual/`, command logs, `summary.json`, and
`pitch_diff.csv`. CSV line numbers point back to the expected and actual Segment
files (header is line 1). Channels are zero-based chip channels. Differences are
reported over half-open tick intervals on the existing Segment 60 Hz timeline.

The comparator ignores silent pitch settings and PSG noise-only tone periods.
It checks audible tone periods, not noise frequency, envelope retriggers, volume,
waveform equivalence, or complete acoustic identity. Different segmentation with
equal per-tick periods compares equal. Missing sounding coverage is an error.
Silent trailing coverage may differ. Empty/missing reference input is an error.

Exit 0 means exact pitch/activity agreement, 1 means differences or execution
failure. Boundary differences within `--boundary-tolerance` (default 1 tick)
remain reported and do not silently pass. `pitch` indicates different periods at
the compared time, not necessarily an incorrect pitch formula: timing drift can
also produce this result. `activity` indicates tone versus silence, `coverage`
indicates absent sounding coverage. Compilation failure is never a successful
comparison and does not fall back to independently rendered tracks.

Use `--actual-dir outputs/pitch/song/actual` to compare existing dumps without
Node dependencies. `--offset-ticks N` explicitly compares reference tick t to
actual tick t+N. No automatic per-note alignment is performed: it could hide
missing notes or accumulating timing errors. Determine any global offset from
independent onset evidence and retain the zero-offset report as well.

## Reference tuning

Inspect original note settings independently of roundtrip timing:

```sh
python scripts/check_reference_pitch.py path/to/song.mml \
  --reference path/to/reference --outdir outputs/reference_pitch/song --loop-count 2
```

This requires an explicit source tuning table and uses the existing finite MML
parser. Grouped PSG/SCC track prefixes are expanded; `--loop-count` selects the
inspection count for `]0`. Unsupported syntax raises an error. The report
compares ordered audible tone-period changes, collapsing consecutive equal
periods, and retains source note, octave, detune, MML step and Segment CSV line.
It does not prove timing, retriggers, or equal-note repetition. Sequence alignment
can find a matching subsequence; inspect insert/delete/replace rows as differences.

Observed reference rule: `period = (tuning[note] >> (octave - 1)) - detune`
for both PSG and SCC, with no extra SCC decrement. gra2_002 matched all 310
pitch changes over 8 channels. gra2_008 with two loop iterations matched all
1391 reference changes; one extra observed PSG channel 3 change remains
(period 889, Segment CSV line 5320, tick 1940). Its cause is not established.
This is evidence for the mapping, not a claim of identical rendered audio.

The local gra2_002 and gra2_008 source MML explicitly contain the same custom
PSG tuning table. Validate this declared table against observed periods before
inferring one from note names. A source note name alone is insufficient: octave,
detune, pitch effects and playback state affect the resulting register value.
Reference-specific tables must not silently become a universal converter table.
