"""OPLL key-on count differences; no timing comparison or quality score."""
from collections import Counter


def compare_keyons(reference, actual):
    """Sum per-channel shortages/excesses, not time-matched missing events.

    Same-channel missing and extra events can cancel in counts. This is an
    inventory check, not proof that individual attacks or audible notes match.
    """
    ref = Counter(e['ch'] for e in reference if e['keyon'])
    act = Counter(e['ch'] for e in actual if e['keyon'])
    channels = ref.keys() | act.keys()
    return dict(reference_keyon=sum(ref.values()), actual_keyon=sum(act.values()),
                missing_keyon=sum(max(0, ref[ch] - act[ch]) for ch in channels),
                extra_keyon=sum(max(0, act[ch] - ref[ch]) for ch in channels))
