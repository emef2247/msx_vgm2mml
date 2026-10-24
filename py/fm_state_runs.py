"""Common FM short-state selection, inherited from MSX OPLL normalization.

Times are original 44.1kHz source samples. Adapters preserve attacks and ordered
side effects, project the retained states and report every omitted interval.
"""
FM_SHORT_STATE_SAMPLES = 44


def select_state_runs(runs, max_samples=FM_SHORT_STATE_SAMPLES, protected=()):
    """Return retained/dropped indices; never remove every state of an attack."""
    if not isinstance(max_samples, int) or max_samples < 0:
        raise ValueError('Short-state threshold must be a nonnegative sample count')
    runs = tuple(runs)
    protected = set(protected)
    if any(not 0 <= i < len(runs) for i in protected):
        raise ValueError('Protected state index is outside the attack')
    if any(b < a for a,b,_ in runs):
        raise ValueError('State interval has negative duration')
    dropped = [i for i,(a,b,_) in enumerate(runs)
               if b-a <= max_samples and len(runs)>1 and i not in protected]
    if len(dropped)==len(runs) and dropped:
        dropped.remove(len(runs)-1)
    dropped_set=set(dropped)
    return tuple(i for i in range(len(runs)) if i not in dropped_set), tuple(dropped)


def fm_short_state_samples(milliseconds=1):
    """Floor a positive configurable millisecond threshold at 44.1kHz."""
    from fractions import Fraction
    try:
        value=Fraction(str(milliseconds))*Fraction(441,10)
    except (ValueError,ZeroDivisionError) as exc:
        raise ValueError('FM short-state milliseconds must be finite and positive') from exc
    if value<1:
        raise ValueError('FM short-state milliseconds must span at least one source sample')
    return value.numerator//value.denominator
