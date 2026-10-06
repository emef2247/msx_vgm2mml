"""Declarative PSG square-tone projection using OPM FM and feedback.

The two-operator AL4/FB7 profile is compatible with the published vgm-conv
mapping parameters. This module contains independently written target rules;
no external converter code is incorporated or required at runtime.
"""
from dataclasses import dataclass
import math

# Fixed PSG levels expressed as OPM attenuation steps, before tone headroom.
LEVEL_TL = (127, 62, 56, 52, 46, 42, 36, 32, 28, 24, 20, 16, 12, 8, 4, 0)


@dataclass(frozen=True)
class FmVoice:
    identity: str = 'psg_fm_feedback'
    model: str = 'fm'
    algorithm: int = 4
    feedback: int = 7
    # Native register-bank order: M1, M2, C1, C2.
    operator_muls: tuple = (2, 1, 1, 1)
    operator_tl: tuple = (27, 127, None, 127)


def tone_tl(volume, gain):
    """Apply gain only to the carrier, retaining the modulator's timbre."""
    if not 0 <= volume <= 15:
        raise ValueError('PSG fixed volume must be in 0..15')
    if not math.isfinite(gain) or not 0 < gain <= 1:
        raise ValueError('FM PSG gain must be positive and at most 1')
    if not volume:
        return 127
    gain_steps = -20 * math.log10(gain) / .75
    return min(127, max(0, int(math.floor(LEVEL_TL[volume] + 8 + gain_steps + .5))))
