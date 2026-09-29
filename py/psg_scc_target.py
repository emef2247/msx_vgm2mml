"""Explicit MGSDRV PSG/SCC period projection, independent of inferred note names."""
BASE_PERIODS = (3421, 3228, 3047, 2876, 2715, 2562, 2419, 2283, 2155, 2034, 1920, 1812)
SCALES = ('c', 'c+', 'd', 'd+', 'e', 'f', 'f+', 'g', 'g+', 'a', 'a+', 'b')
TUNING_HEADER = '#psg_tune { ' + ', '.join(map(str, BASE_PERIODS)) + ' }'


def period_detune(segment):
    base = BASE_PERIODS[SCALES.index(segment.scale)] >> (segment.octave - 1)
    # MGSDRV subtracts signed detune from the tone-period table entry.
    return max(-127, min(127, base - segment.tone_period))


def envelope_period_tokens(period):
    if period:
        return f'm{period}'
    # m0 is rejected by MGSC. Direct PSG writes retain the observed zero value.
    return 'y11,0 y12,0'


def rendered_period(segment):
    base = BASE_PERIODS[SCALES.index(segment.scale)] >> (segment.octave - 1)
    return base - period_detune(segment)
