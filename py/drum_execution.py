"""Lower accepted inferred percussion into musical events, not MML text."""
from dataclasses import replace
from musical_plan import MusicalControl, MusicalUnit

INSTRUMENTS = ('BD', 'SD', 'TOM', 'CYM', 'HH')
BITS = (16, 8, 4, 2, 1)


def add_overlay(plan, groups, end, summary, decisions, *, timing):
    additions = []
    for group in groups:
        sample = timing.step_sample(group.tick) if timing.applied else timing.sample(group.tick)
        for hit in group.hits:
            if hit.channel == -1:
                additions.append((sample, hit))
    if not additions:
        return plan
    units, controls = list(plan.units), list(plan.controls)
    base = plan.ordered_controls()
    native_percussion = any(c.kind == 'rhythm_register' and c.value[0] == 14
                            and c.value[1] & 31 for c in base)
    if not native_percussion:
        # Measured MGSDRV rhythm initialization, not invented source evidence.
        # Zero-frequency reset values would make new BD/TOM parts ineffective.
        at = min(sample for sample, _ in additions)
        for index, (register, value) in enumerate(((0x16, 32), (0x17, 80), (0x18, 192),
                                                  (0x26, 5), (0x27, 5), (0x28, 1))):
            controls.append(MusicalControl(at, 'opll', None, 'rhythm_register',
                (register, value), 1999999980 + index, origin='target_percussion_initialization'))
    for number, (at, hit) in enumerate(additions):
        instrument = INSTRUMENTS.index(hit.instrument)
        bit = BITS[instrument]
        native = 0
        for control in base:
            if control.sample > at:
                break
            if control.kind == 'rhythm_register' and control.value[0] == 0x0e:
                native = control.value[1] & 31
        if native & bit:
            summary['added_hits'] -= 1
            summary['omitted_hits'] += 1
            summary['instruments'][hit.instrument] -= 1
            for decision in decisions:
                if (decision['status'] == 'added' and decision['instrument'] == hit.instrument
                        and decision['target_tick'] == next(g.tick for g in groups if hit in g.hits)):
                    decision.update(status='omitted', reason='native_rhythm_already_held')
                    break
            continue
        duration = (timing.step_sample(max(1, timing.tempo // 75)) if timing.applied else 735)
        following = [sample for sample, later in additions if sample > at and later.instrument == hit.instrument]
        stop = min(at + duration, min(following)) if following else at + duration
        native_attacks = [c.sample for c in base if c.sample > at and c.kind == 'rhythm_register'
                          and c.value[0] == 0x0e and c.value[1] & bit]
        if native_attacks:
            stop = min(stop, min(native_attacks))
        uid = f'opll:inferred_rhythm:{number}'
        source = round(hit.source_time * 44100)
        volume = 15 - int(hit.state[0])
        units.append(MusicalUnit(uid, 'opll', 6 + min(instrument, 2), at, stop, False,
            'inferred_percussion', source_start=source, source_end=source,
            parameters=(('instrument', hit.instrument), ('volume', volume), ('heuristic', True))))
        for sample, gate, order in ((at, 1, 2000000000 + number * 2 + 1),
                                    (stop, 0, 2000000000 + number * 2)):
            controls.append(MusicalControl(sample, 'opll', None, 'percussion', (instrument, volume, gate),
                order, uid, source, origin='accepted_inferred_percussion'))
    end_sample = max(plan.end_sample, max((c.sample for c in controls), default=0))
    clocks = dict(plan.chip_clocks)
    clocks.setdefault('opll', 3579545)
    return replace(plan, units=tuple(units), controls=tuple(controls), end_sample=end_sample,
        chip_clocks=tuple(sorted(clocks.items())),
        decisions=plan.decisions + tuple(('inferred_drum', tuple(sorted(row.items()))) for row in decisions))
