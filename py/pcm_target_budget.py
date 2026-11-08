"""Explicitly lossy byte-budget coverage using existing immutable PCM assets.

This target policy never modifies source samples, encoded bytes or event times.
Distances are coarse capacity diagnostics, not perceptual similarity guarantees.
"""
import math


def _features(sample):
    audio = sample['amplitudes']
    size = len(audio)
    envelope = []
    for index in range(20):
        low, high = index * size // 20, (index + 1) * size // 20
        count = min(64, high - low)
        values = [float(audio[low + j * (high-low) // count]) for j in range(count)]
        envelope.append(math.sqrt(sum(x*x for x in values) / max(1,count)))
    norm = math.sqrt(sum(x*x for x in envelope)) or 1
    envelope = [x/norm for x in envelope]
    count = min(2048,size)
    probe = [float(audio[j * size // count]) for j in range(count)]
    crossings = sum((a < 0) != (b < 0) for a,b in zip(probe,probe[1:]))
    seconds = size / sample['rate_hz']
    crossing_hz = crossings / max(seconds,1e-12)
    return tuple(envelope + [math.log2(max(seconds,1e-9))*.25,
                             math.log2(1+crossing_hz)*.15])


def fit_bank(samples, usage, byte_budget):
    """Return (source-to-representative mapping, selected IDs, diagnostics).

    First cover weighted demand with one feasible existing representative;
    then greedily add the greatest weighted distance improvement that fits.
    Ties use sample identity, independently of caller order. No slot cap applies.
    """
    if not isinstance(byte_budget,int) or byte_budget < 0:
        raise ValueError('PCM byte budget must be a nonnegative integer')
    records = {sample['sample_id']:sample for sample in samples}
    if len(records) != len(samples):
        raise ValueError('Duplicate PCM candidate identity')
    ids = sorted(records)
    costs = {sid:len(records[sid]['encoded']) for sid in ids}
    weights = {sid:max(1,int(usage.get(sid,0))) for sid in ids}
    for sample in samples:
        if not math.isfinite(sample['rate_hz']) or sample['rate_hz'] <= 0:
            raise ValueError('PCM candidate rate must be finite and positive')
    total = sum(costs.values())
    diagnostics = dict(selection_method='weighted_facility_coverage',byte_budget=byte_budget,
        input_sample_count=len(ids),input_bytes=total,output_sample_count=0,output_bytes=0,
        forced_sample_count=0,forced_playback_count=0,playback_count=sum(usage.get(sid,0) for sid in ids),
        omitted_playback_count=0,similarity_bounds_enforced=False,slot_limit=None,
        mappings=[],max_distance=0.,weighted_distance=0.)
    if total <= byte_budget:
        diagnostics.update(selection_method='identity_within_budget',output_sample_count=len(ids),output_bytes=total,
            mappings=[dict(sample_id=sid,target_sample_id=sid,distance=0.,forced=False,
                           playback_count=usage.get(sid,0)) for sid in ids])
        return {sid:sid for sid in ids},ids,diagnostics
    candidates = [sid for sid in ids if costs[sid] <= byte_budget]
    if not candidates:
        raise ValueError('PCM budget has no existing independently playable candidate within the byte limit')
    active = {sid:bool(records[sid]['amplitudes']) and max(records[sid]['amplitudes'])>min(records[sid]['amplitudes']) for sid in ids}
    onset = {sid:bool(records[sid]['amplitudes'][:64]) and max(records[sid]['amplitudes'][:64])>min(records[sid]['amplitudes'][:64]) for sid in ids}
    first_candidates = candidates
    if any(onset.values()):
        first_candidates = [sid for sid in candidates if onset[sid]]
    elif any(active.values()):
        first_candidates = [sid for sid in candidates if active[sid]]
    if not first_candidates:
        raise ValueError('PCM budget has no bounded representative preserving an active sample onset')
    features = {sid:_features(records[sid]) for sid in ids}
    distance = {sid:{rep:math.sqrt(sum((a-b)**2 for a,b in zip(features[sid],features[rep])))
                     for rep in candidates} for sid in ids}
    def eligible(sid,rep):
        return (not active[sid] or active[rep]) and (not onset[sid] or onset[rep])
    def score(sid,rep):
        return distance[sid][rep] if eligible(sid,rep) else float('inf')
    first = min(first_candidates,key=lambda rep:(sum(weights[sid]*score(sid,rep) for sid in ids),rep))
    selected = [first]
    remaining = byte_budget-costs[first]
    nearest = {sid:score(sid,first) for sid in ids}
    while True:
        feasible = [rep for rep in candidates if rep not in selected and costs[rep] <= remaining]
        if not feasible:
            break
        gains = {rep:sum(weights[sid]*max(0.,nearest[sid]-score(sid,rep))
                        for sid in ids if eligible(sid,rep)) for rep in feasible}
        choice = min(feasible,key=lambda rep:(-gains[rep],rep))
        if gains[choice] <= 0:
            break
        selected.append(choice)
        remaining -= costs[choice]
        nearest = {sid:min(nearest[sid],score(sid,choice)) for sid in ids}
    selected.sort()
    mapping = {}
    for sid in ids:
        eligible_ids = [rep for rep in selected if eligible(sid,rep)]
        mapping[sid] = sid if sid in eligible_ids else min(eligible_ids,key=lambda rep:(distance[sid][rep],rep))
    rows = [dict(sample_id=sid,target_sample_id=mapping[sid],distance=distance[sid][mapping[sid]],
                 forced=sid!=mapping[sid],playback_count=usage.get(sid,0)) for sid in ids]
    diagnostics.update(output_sample_count=len(selected),output_bytes=sum(costs[sid] for sid in selected),
        forced_sample_count=sum(row['forced'] for row in rows),
        forced_playback_count=sum(row['playback_count'] for row in rows if row['forced']),mappings=rows,
        max_distance=max(row['distance'] for row in rows),
        weighted_distance=sum(weights[row['sample_id']]*row['distance'] for row in rows))
    return mapping,selected,diagnostics
