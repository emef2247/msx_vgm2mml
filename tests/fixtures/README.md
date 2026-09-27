# Test fixtures

Public, redistributable fixtures for converter checks.

## Layout

Each public case looks like this:

    tests/fixtures/public/<chip>/<case>/
      <case>.vgm
      reference/
        <case>.mml
      expected/
        <profile>/
          output.mid
          domino.mid
          user_voices.json

- `<case>.vgm` is the converter input.
- `reference/` is human context. Tests must not require it.
- `expected/<profile>/` holds baselines for one converter option set.

The current OPLL profile name is `tx802_default_rx21`.
It means `--target=tx802 --melody_mode=default --rhythm_mode=rx21`.

A case may omit an expected file that cannot yet be asserted.
Do not place expected files directly under `expected/`.

## Expected files

- `output.mid` is the direct converter output. Use this for automated comparisons.
- `domino.mid` is the desired MIDI after Domino CC-macro expansion. Treat it as a target artifact. CI cannot currently regenerate it.
- `user_voices.json` is the user-voice definition file emitted by the converter for that case.

Keep these three filenames stable. Do not prefix them with the case name.
Add another `<profile>/` directory only when a different option set has its own baseline.

## Naming

- One case per directory.
- The VGM filename matches the directory name.
- Case names describe the behavior under test, not a commercial track title.

## What belongs here

- Small original or otherwise redistributable VGMs
- Short MML used to explain the intended pattern
- Small expected files for those public cases

## What does not belong here

- Extracted commercial-game VGM, WAV, MGS, or MIDI
- Large recordings
- Generated outputs used only as local regression baselines

Private fixtures stay outside git. If `fixtures.local.toml` exists, local tests may read that directory. If it does not exist, skip private cases.

