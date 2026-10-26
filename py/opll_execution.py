"""Accepted OPLL musical units and ordered controls, independent of target text.

Melodic pitch is the same semitone decision as the MML renderer. Native fine
pitch remains provenance. Custom-patch and rhythm writes remain global,
ordered observations because YM2413 has one shared user-patch register bank.
"""
import struct
from dataclasses import replace
from musical_plan import MusicalControl, MusicalPlan, MusicalUnit
from melody_patterns import analyze
from opll_note_units import group_notes
from opll_target import read_patch_updates, segment_decisions, note_pitch, target_note
from vgm_timing import command_times


class _DefaultTiming:
    plan = None

    @staticmethod
    def sample(tick):
        return int(tick) * 735

    @staticmethod
    def source_sample(sample):
        from mml_utils import get_ticks
        return get_ticks(sample / 44100) * 735


def _original(seg, end=False):
    value = getattr(seg, 'vgmticks_end' if end else 'vgmticks', None)
    return int(value) if value is not None else int(seg.tick_end if end else seg.tick_start) * 735


def _source_globals(raw):
    """Retain source-ordered patch writes and rhythm-mode shared register writes."""
    if raw is None:
        return (), {}, None
    controls, channel_orders = [], {}
    rhythm, end = False, 0
    registers = [0] * 64
    for ordinal, event in enumerate(command_times(raw)):
        end = max(end, event.vgmticks + event.wait_samples)
        if event.command != 0x51:
            continue
        reg, value = raw[event.address + 1:event.address + 3]
        if reg < len(registers):
            registers[reg] = value
        if reg <= 7:
            controls.append((event.vgmticks, ordinal, 'patch_write', reg, value))
        elif reg == 0x0e:
            controls.append((event.vgmticks, ordinal, 'rhythm_register', reg, value))
            rhythm = bool(value & 32)
        elif rhythm and reg in (0x16, 0x17, 0x18, 0x26, 0x27, 0x28, 0x36, 0x37, 0x38):
            controls.append((event.vgmticks, ordinal, 'rhythm_register', reg, value))
        if 0x10 <= reg <= 0x18 or 0x20 <= reg <= 0x28 or 0x30 <= reg <= 0x38:
            ch = reg & 15
            high, voice = registers[0x20 + ch], registers[0x30 + ch]
            state = (registers[0x10 + ch] | ((high & 1) << 8), (high >> 1) & 7,
                     int(bool(high & 16)), voice >> 4, voice & 15, (high >> 5) & 1)
            channel_orders.setdefault((event.vgmticks, ch), []).append((ordinal, state))
    return tuple(controls), channel_orders, end


def build_opll(segments, voice_csv_path=None, *, source_raw=None, timing=None,
               clock_hz=3579545, source_end_sample=None, num_channels=9):
    """Build from reconstructed units; timing exposes sample/source_sample hooks.

    A normalized mapper may supply ``plan`` and ``step_sample``. Its accepted
    melody planner is shared with the normalized MML renderer.
    """
    timing = timing or _DefaultTiming()
    if getattr(timing, 'plan', None) is not None:
        plan = _normalized(segments, voice_csv_path, source_raw, timing,
                           clock_hz, source_end_sample, num_channels)
        return _respect_rhythm_mode(plan, source_raw, timing, segments, voice_csv_path)
    updates = read_patch_updates(voice_csv_path)
    analysis = analyze(segments, 'opll', voice_csv_path)
    globals_, orders, raw_end = _source_globals(source_raw)
    if source_raw is None:
        globals_ = tuple((tick * 735, ordinal * 8 + reg, 'patch_write', reg, value)
                         for ordinal, (tick, patch) in enumerate(updates) for reg, value in enumerate(patch))
    units, controls, patterns = [], [], []
    used_orders = {}
    def emit(sample, channel, kind, value, *, unit=None, source=None, indices=(), order=0, event=None, origin='interpreted'):
        controls.append(MusicalControl(int(sample), 'opll', channel, kind, tuple(value),
            order, unit, source, event, tuple(indices), origin))
    for ch in range(num_channels):
        rows = segments.get(ch, ())
        if not rows:
            continue
        decisions = segment_decisions(rows, updates)
        members, grouped = group_notes(rows, analysis[ch][0])
        for number, (member, grouped_unit) in enumerate(zip(members, grouped)):
            indices = tuple(member.segment_indices)
            first, last = rows[indices[0]], rows[indices[-1]]
            identity = f'opll:{ch}:{number}'
            units.append(MusicalUnit(identity, 'opll', ch, timing.sample(first.tick_start),
                timing.sample(last.tick_end), not bool(first.keyon), 'reconstructed_key_gate', indices,
                _original(first), _original(last, True), parameters=tuple(
                    (i, int(rows[i].fnum), int(rows[i].block), int(rows[i].inst), int(rows[i].vol), int(rows[i].sus))
                    for i in indices)))
            previous = {}
            for i in indices:
                seg, decision = rows[i], decisions[i]
                source = _original(seg)
                sample = timing.sample(seg.tick_start)
                native_orders = orders.get((source, ch), ())
                native_state = (int(seg.fnum), int(seg.block), int(bool(seg.keyon)),
                                int(seg.inst), int(seg.vol), int(seg.sus))
                minimum = used_orders.get((source, ch), -1)
                matches = [ordinal for ordinal, state in native_orders if state == native_state and ordinal >= minimum]
                event_id = matches[0] if matches else (native_orders[-1][0] if native_orders else None)
                if event_id is not None:
                    used_orders[(source, ch)] = event_id
                order = (event_id if event_id is not None else i) * 16
                fnum, block = note_pitch(decision.octave, decision.note)
                state = {'pitch': (fnum, block, int(seg.sus)),
                         'instrument': (int(seg.inst),), 'volume': (decision.volume,)}
                for offset, (kind, value) in enumerate(state.items()):
                    if previous.get(kind) != value:
                        emit(sample, ch, kind, value, unit=identity, source=source, indices=(i,), order=order+offset, event=event_id)
                        previous[kind] = value
                # Preserve explicit retriggers and zero-duration key-off/on rows.
                gate = int(bool(seg.keyon) and bool(seg.fnum))
                if decision.edge and previous.get('gate') == (1,):
                    emit(sample, ch, 'gate', (0,), unit=identity, source=source, indices=(i,), order=order+3, event=event_id)
                if previous.get('gate') != (gate,) or decision.edge:
                    emit(sample, ch, 'gate', (gate,), unit=identity, source=source, indices=(i,), order=order+4, event=event_id)
                previous['gate'] = (gate,)
            if grouped_unit.kind == 'note':
                emit(timing.sample(last.tick_end), ch, 'gate', (0,), unit=identity,
                     source=_original(last, True), indices=(indices[-1],), order=-1)
        for use in analysis[ch][2]:
            patterns.append(('opll', ch, use.pattern_id, use.group_start, use.repeats))
    _append_globals(controls, globals_, timing, observed=source_raw is not None)
    source_end = source_end_sample if source_end_sample is not None else (raw_end if raw_end is not None else
        max((_original(seg, True) for rows in segments.values() for seg in rows), default=0))
    end = max([timing.source_sample(source_end)] + [u.end_sample for u in units] + [c.sample for c in controls])
    plan = MusicalPlan(tuple(units), tuple(controls), end, source_end, (('opll', clock_hz),),
        song_loop_sample=_loop_sample(source_raw, timing), patterns=tuple(patterns),
        metadata=(('opll_pitch_profile', 'MGSDRV measured semitone FNUM table; native pitch retained in units'),))
    return _respect_rhythm_mode(plan, source_raw, timing, segments, voice_csv_path)


def _respect_rhythm_mode(plan, raw, timing, segments, voice_path):
    """Keep the shared 6..8 rhythm bank authoritative while rhythm is enabled.

    Entering rhythm restores retained native latent registers before mode-on;
    leaving it restores accepted melodic state. These are distinct hardware
    resources, not nine independent always-melodic channels.
    """
    if raw is None:
        return plan
    from bisect import bisect_right
    registers = [0] * 64
    modes, additions, restored_units = [], [], []
    previous = False
    for ordinal, event in enumerate(command_times(raw)):
        if event.command != 0x51:
            continue
        reg, value = raw[event.address + 1:event.address + 3]
        if reg < 64:
            registers[reg] = value
        if reg != 14:
            continue
        active = bool(value & 32)
        modes.append(((event.vgmticks, ordinal), active))
        sample = timing.source_sample(event.vgmticks)
        if active and not previous:
            for offset, address in enumerate((0x16, 0x17, 0x18, 0x26, 0x27, 0x28, 0x36, 0x37, 0x38)):
                additions.append(MusicalControl(sample, 'opll', None, 'rhythm_register',
                    (address, registers[address]), ordinal * 16 - 10 + offset,
                    source_sample=event.vgmticks, source_event_id=ordinal,
                    origin='retained_rhythm_bank_at_mode_entry'))
        elif previous and not active:
            for channel in (6, 7, 8):
                high, voice = registers[0x20 + channel], registers[0x30 + channel]
                native_fnum = registers[0x10 + channel] | ((high & 1) << 8)
                native_block, sustain = (high >> 1) & 7, (high >> 5) & 1
                pitch = note_pitch(*target_note(native_fnum, native_block))
                gate = int(bool(high & 16) and bool(native_fnum))
                identity = f'opll:{channel}:mode_exit:{ordinal}'
                following = [u for u in plan.units if u.channel == channel and u.start_sample >= sample]
                end = min((u.start_sample for u in following), default=plan.end_sample)
                if end > sample:
                    restored_units.append(MusicalUnit(identity, 'opll', channel, sample, end, not bool(gate),
                        'mode_exit_continuation', source_start=event.vgmticks,
                        parameters=(('native_fnum', native_fnum), ('native_block', native_block),
                                    ('instrument', voice >> 4), ('attenuation', voice & 15),
                                    ('source_mode_event', ordinal))))
                values = (('pitch', (*pitch, sustain)), ('instrument', (voice >> 4,)),
                          ('volume', (15 - (voice & 15),)), ('gate', (gate,)))
                for offset, (kind, payload) in enumerate(values):
                    additions.append(MusicalControl(sample, 'opll', channel, kind, tuple(payload),
                        ordinal * 16 + (channel - 6) * 4 + offset + 1,
                        unit_id=identity if end > sample else None,
                        source_sample=event.vgmticks, source_event_id=ordinal,
                        origin='accepted_melody_at_rhythm_exit'))
        previous = active
    if not modes:
        return plan
    mode_targets = [((timing.source_sample(key[0]), key[1] * 16), active) for key, active in modes]
    positions = [key for key, _ in mode_targets]

    def rhythm_at(control):
        index = bisect_right(positions, (control.sample, control.order)) - 1
        return mode_targets[index][1] if index >= 0 else False

    controls = [c for c in plan.controls if c.channel not in (6, 7, 8) or not rhythm_at(c)]
    # Units retain native provenance even when their melodic oscillator is
    # unavailable. Mark those intervals explicitly instead of claiming sound.
    boundaries = [(timing.source_sample(key[0]), active) for key, active in modes]
    units, unit_map = [], {}
    for unit in plan.units:
        if unit.channel not in (6, 7, 8) or unit.start_sample == unit.end_sample:
            units.append(unit)
            continue
        cuts = sorted({unit.start_sample, unit.end_sample,
                       *(sample for sample, _ in boundaries if unit.start_sample < sample < unit.end_sample)})
        for index, (start, end) in enumerate(zip(cuts, cuts[1:])):
            mode = next((active for sample, active in reversed(boundaries) if sample <= start), False)
            piece = replace(unit, unit_id=unit.unit_id if index == 0 else unit.unit_id + f':mode{index}', start_sample=start,
                end_sample=end, rest=unit.rest or mode,
                articulation='rhythm_resource' if mode else unit.articulation)
            units.append(piece)
            unit_map.setdefault(unit.unit_id, []).append(piece)
    controls = [replace(c, unit_id=next((u.unit_id for u in unit_map[c.unit_id]
                if u.start_sample <= c.sample < u.end_sample), unit_map[c.unit_id][-1].unit_id))
                if c.unit_id in unit_map else c for c in controls]
    for index, (key, active) in enumerate(modes):
        if not active:
            continue
        start = timing.source_sample(key[0])
        end = timing.source_sample(modes[index + 1][0][0]) if index + 1 < len(modes) else plan.end_sample
        if end > start:
            for channel in (6, 7, 8):
                if not any(u.channel == channel and u.start_sample <= start and u.end_sample >= end for u in units):
                    units.append(MusicalUnit(f'opll:{channel}:rhythm_resource:{key[1]}', 'opll', channel,
                        start, end, True, 'rhythm_resource', source_start=key[0],
                        parameters=(('source_mode_event', key[1]),)))
    return replace(plan, units=tuple(units + restored_units), controls=tuple(controls + additions),
                   metadata=plan.metadata + (('rhythm_shared_bank', 'native during rhythm; accepted melody restored at mode exit'),))


def _append_globals(controls, globals_, timing, *, observed=True):
    for source, ordinal, kind, reg, value in globals_:
        controls.append(MusicalControl(timing.source_sample(source), 'opll', None,
            kind, (reg, value), ordinal * 16, source_sample=source,
            source_event_id=ordinal if observed else None,
            origin='observed_global_register' if observed else 'patch_snapshot_projection'))


def _loop_sample(raw, timing):
    if raw is None or len(raw) < 0x20:
        return None
    offset = struct.unpack_from('<I', raw, 0x1c)[0]
    if not offset:
        return None
    address = 0x1c + offset
    for event in command_times(raw):
        if event.address == address:
            return timing.source_sample(event.vgmticks)
    raise ValueError('OPLL source loop does not land on a command boundary')


def _normalized(segments, voice_csv_path, source_raw, timing, clock_hz, source_end_sample, num_channels):
    from musical_timing import plan_melody
    melody = getattr(timing, 'melody', None) or plan_melody(segments, voice_csv_path, timing.plan,
                                                        num_channels=num_channels)
    units, controls = [], []
    globals_, orders, raw_end = _source_globals(source_raw)
    if source_raw is None:
        updates = read_patch_updates(voice_csv_path)
        globals_ = tuple((tick * 735, ordinal * 8 + reg, 'patch_write', reg, value)
                         for ordinal, (tick, patch) in enumerate(updates) for reg, value in enumerate(patch))
    for track in melody.tracks:
        rows = segments.get(track.channel, ())
        for note in track.notes:
            identity = f'opll:{track.channel}:{note.note_index}'
            start, end = timing.step_sample(note.start_step), timing.step_sample(note.end_step)
            units.append(MusicalUnit(identity, 'opll', track.channel, start, end, False,
                'accepted_normalized_key_gate', note.source_indices, note.source_start, note.source_end,
                parameters=tuple((i, int(rows[i].fnum), int(rows[i].block), int(rows[i].inst),
                    int(rows[i].vol), int(rows[i].sus)) for i in note.source_indices)))
            previous_gate_end = None
            for index, state in enumerate(note.states):
                octave, pitch, voice, volume, sustain, patch_hex = state.value
                fnum, block = note_pitch(octave, pitch)
                at = timing.step_sample(state.start_step)
                gate_end = timing.step_sample(state.gate_end_step)
                nominal_end = timing.step_sample(state.end_step)
                source_events = orders.get((state.source_start, track.channel), ())
                event_id = source_events[-1][0] if source_events else None
                base_order = event_id * 16 if event_id is not None else 0
                def emit(kind, value, sample=at, order=0):
                    controls.append(MusicalControl(sample, 'opll', track.channel, kind, tuple(value),
                        base_order + order, identity, state.source_start, source_event_id=event_id,
                        source_indices=state.source_indices,
                        origin='accepted_normalized_melody'))
                for order, (kind, value) in enumerate((('pitch', (fnum, block, int(sustain))),
                        ('instrument', (int(voice) + 1 if int(voice) < 15 else 0,)), ('volume', (int(volume),)))):
                    emit(kind, value, order=order)
                if index == 0 or previous_gate_end < at:
                    emit('gate', (1,), order=4)
                if gate_end < nominal_end or index == len(note.states) - 1:
                    emit('gate', (0,), gate_end, -1)
                previous_gate_end = gate_end
        # Preserve the whole instantaneous transition group, including its
        # positive-duration settling state. Replaying only a zero-length ON
        # could otherwise leave a phantom note sounding through the next rest.
        groups = {}
        for i, seg in enumerate(rows):
            groups.setdefault(_original(seg), []).append((i, seg))
        for source, members in groups.items():
            if not any(_original(seg) == _original(seg, True) for _, seg in members):
                continue
            used = -1
            for i, seg in members:
                native_state = (int(seg.fnum), int(seg.block), int(bool(seg.keyon)),
                                int(seg.inst), int(seg.vol), int(seg.sus))
                matches = [ordinal for ordinal, state in orders.get((source, track.channel), ())
                           if state == native_state and ordinal > used]
                event_id = matches[0] if matches else None
                if event_id is not None:
                    used = event_id
                controls.append(MusicalControl(timing.source_sample(source), 'opll', track.channel,
                    'gate', (int(bool(seg.keyon) and bool(seg.fnum)),),
                    (event_id if event_id is not None else i) * 16 + 4,
                    source_sample=source, source_event_id=event_id, source_indices=(i,),
                    origin='zero_duration_key_transition'))
    _append_globals(controls, globals_, timing, observed=source_raw is not None)
    source_end = source_end_sample if source_end_sample is not None else (raw_end if raw_end is not None else
        max((_original(seg, True) for rows in segments.values() for seg in rows), default=0))
    end = max([timing.source_sample(source_end)] + [u.end_sample for u in units] + [c.sample for c in controls])
    return MusicalPlan(tuple(units), tuple(controls), end, source_end, (('opll', clock_hz),),
        song_loop_sample=_loop_sample(source_raw, timing),
        decisions=tuple(('normalized_note', tuple(sorted(row.items()))) for row in melody.evidence),
        metadata=(('opll_pitch_profile', 'MGSDRV measured semitone FNUM table; native pitch retained in units'),
                  ('normalized', True)))
