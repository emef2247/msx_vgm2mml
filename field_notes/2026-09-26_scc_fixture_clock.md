# Correction: SCC clock field

The previous version of this note incorrectly called 0xCC the K051649 clock
and concluded that all 13 public SCC fixtures declared no SCC. That conclusion
was wrong: 0xCC is the ES5503 clock. The converter and the initial refactoring
validation shared the same wrong assumption.

K051649/K052539 is at 0x9C-0x9F (32-bit little-endian). Twelve public SCC files
contain `4D 4F 1B 00` = 1789773 Hz; only `short_pulses` has zero there.
The production reader and test helper now use 0x9C. The original fixture bytes
remain unchanged. Header unit tests and an unmodified-fixture CLI test guard
against the original failure independently of output snapshots.

Reference:
https://raw.githubusercontent.com/vgmrips/vgmplay-legacy/master/VGMPlay/vgmspec171.txt

Future work: verify binary-format offsets against the specification, not comments
in the existing code. Identical old/new output can preserve an existing bug.
