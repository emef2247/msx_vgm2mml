"""Executable accepted PSG/SCC notes, with source-ordered shared controls.

This adapter consumes PerformanceIR partitions; it never infers notes from raw
registers or expands descriptive loop metadata into a second performance.
"""
from dataclasses import dataclass
from musical_plan import MusicalControl, MusicalUnit, MusicalPlan
from psg_scc_target import rendered_period
from vgm_timing import command_times
from mml_utils import get_ticks


@dataclass(frozen=True)
class AcceptedNoteDecision:
    period: int | None
    hardware_envelope: bool
    volume_runs: tuple
    period_exact: bool


def accepted_note_decision(note, chip):
    """Pure renderer/execution agreement, after accepted score partitioning."""
    period = None if note.rest else rendered_period(note.segment)
    return AcceptedNoteDecision(period, not note.rest and chip == 'psg'
        and bool(note.segment.envelope_enabled), tuple(note.runs),
        period is None or period == note.segment.tone_period)


def build_psg_scc(performance, *, source_raw=None, timing=None, clock_hz=1789773):
    """Project accepted ScoreNotes and exact volume runs to 44100-Hz controls.

    timing.sample(tick) maps interpreted ticks; timing.source_sample(sample)
    optionally maps raw shared writes. A callable timing maps ticks only.
    Source times remain provenance, never substituted for accepted note times.
    """
    chip = performance.chip
    if chip not in ('psg', 'scc'):
        raise ValueError('Expected PSG/SCC performance')
    hz = performance.tick_clock_hz
    def sample(tick):
        method = getattr(timing, 'sample', timing)
        return int(method(tick)) if method is not None else round(tick * 44100 / hz)
    def source_sample(value):
        method = getattr(timing, 'source_sample', None)
        return int(method(value)) if method else sample(get_ticks(value / 44100) * hz / 60)
    units, controls, decisions = [], [], []
    source = dict(performance.source_segments)
    end = max((sample(s.ticks + s.l) for _, rows in performance.source_segments for s in rows), default=0)
    source_end = max((s.vgmticks_end or 0 for _, rows in performance.source_segments for s in rows), default=0)
    def add(at, kind, value, channel=None, unit=None, src=None, event=None,
            order=1000000000, indices=(), origin='accepted_score'):
        controls.append(MusicalControl(int(at), chip, channel, kind, tuple(value),
            order, unit, src, event, tuple(indices), origin))
    for channel, notes in performance.channels:
        boundary_method = getattr(timing, 'boundaries', None)
        ends = (boundary_method([n.start + n.length for n in notes],
                    [source[channel][n.segment_indices[-1]].vgmticks_end for n in notes])
                if boundary_method else tuple(sample(n.start + n.length) for n in notes))
        for index, note in enumerate(notes):
            first, last = source[channel][note.segment_indices[0]], source[channel][note.segment_indices[-1]]
            start = (ends[index-1] if index and notes[index-1].start + notes[index-1].length == note.start
                     else sample(note.start))
            stop = ends[index]
            end = max(end, stop)
            uid = f'{chip}:{channel}:note{index}'
            d = accepted_note_decision(note, chip)
            parameters = (('native_period', note.segment.tone_period),
                          ('accepted_period', d.period), ('volume_runs', d.volume_runs))
            if chip == 'scc':
                parameters += (('waveform_id', note.segment.waveform_id),
                               ('waveform_hex', note.segment.waveform_hex))
            else:
                parameters += (('mode', note.segment.mode),
                               ('noise_period', note.segment.noise_period),
                               ('native_envelope_enabled', bool(note.segment.envelope_enabled)),
                               ('hardware_envelope', d.hardware_envelope),
                               ('envelope_period', note.segment.envelope_period),
                               ('envelope_shape', note.segment.envelope_shape))
            units.append(MusicalUnit(uid, chip, channel, start, stop, note.rest,
                source_indices=note.segment_indices, source_start=first.vgmticks,
                source_end=last.vgmticks_end, gate_ids=note.gate_ids,
                parameters=parameters))
            if not d.period_exact:
                decisions.append((uid, 'period_approximated', note.segment.tone_period, d.period))
            source_default = object()
            def emit(at, kind, value, offset=0, source_time=source_default):
                control_channel = (None if kind in ('psg_noise', 'psg_envelope_period',
                                                    'psg_envelope_shape', 'wave_write') else channel)
                add(at, kind, value, control_channel, uid,
                    first.vgmticks if source_time is source_default else source_time,
                    order=1000000000 + index * 10 + offset, indices=note.segment_indices)
            if note.rest:
                emit(start, 'gate', (0,))
                continue
            emit(start, 'pitch', (d.period,))
            if chip == 'psg':
                emit(start, 'psg_mode', (note.segment.mode,))
                emit(start, 'psg_envelope_enable', (int(d.hardware_envelope),))
                if source_raw is None:
                    if note.segment.mode & 2:
                        emit(start, 'psg_noise', (note.segment.noise_period,))
                    if d.hardware_envelope:
                        emit(start, 'psg_envelope_period', (note.segment.envelope_period,))
                        previous = notes[index-1] if index else None
                        if previous is None or not previous.segment.envelope_enabled or note.segment.ev_type == 'evS':
                            emit(start, 'psg_envelope_shape', (note.segment.envelope_shape,))
            elif source_raw is None:
                waveform = tuple(bytes.fromhex(note.segment.waveform_hex))
                if len(waveform) != 32:
                    raise ValueError('Accepted SCC note lacks complete waveform')
                emit(start, 'waveform', waveform)
            emit(start, 'gate', (1,), 1)
            if d.hardware_envelope:
                emit(start, 'volume', (15,), 2)
            else:
                cursor = note.start
                for volume, length in d.volume_runs:
                    at = start + round((cursor - note.start) * 44100 / hz)
                    if at < stop:
                        native = next((source[channel][i] for i in note.segment_indices
                                       if source[channel][i].ticks == cursor), None)
                        emit(at, 'volume', (volume,), 2,
                             source_time=native.vgmticks if native is not None else None)
                    else:
                        decisions.append((uid, 'volume_run_clipped_at_accepted_end', cursor, at, stop))
                    cursor += length
            emit(stop, 'gate', (0,), 0, source_time=last.vgmticks_end)
    if source_raw is not None:
        env = [0, 0]
        articulation = []
        for event_id, event in enumerate(command_times(source_raw)):
            source_end = max(source_end, event.vgmticks + event.wait_samples)
            pos = event.address
            at = source_sample(event.vgmticks)
            def raw(kind, value):
                add(at, kind, value, src=event.vgmticks, event=event_id,
                    order=event_id, origin='ordered_source_shared_control')
            if chip == 'psg' and event.command == 0xa0:
                reg, value = source_raw[pos+1:pos+3]
                if reg == 7:
                    articulation.append((event.vgmticks, event_id, value & 63))
                if reg == 6:
                    raw('psg_noise', (value & 31,))
                elif reg in (11, 12):
                    env[reg-11] = value
                    raw('psg_envelope_period', (env[0] | env[1] << 8,))
                elif reg == 13:
                    raw('psg_envelope_shape', (value & 15,))
            elif chip == 'scc' and event.command == 0xd2:
                port, reg, value = source_raw[pos+1:pos+4]
                if port in (0, 4) and reg < 128:
                    raw('wave_write', (reg // 32, reg % 32, value))
                elif port == 3:
                    articulation.append((event.vgmticks, event_id, value & 31))
        end = max(end, source_sample(source_end))
        # Preserve observed, zero-width articulations only when the block returns
        # to its incoming native state. Positive source states remain interpreted
        # by accepted score units, not replayed over rests or simplified curves.
        incoming = 63 if chip == 'psg' else 0
        position = 0
        def state(mask, channel):
            return (((not bool(mask & (1 << channel))) |
                     ((not bool(mask & (1 << (channel + 3)))) << 1)) if chip == 'psg'
                    else int(bool(mask & (1 << channel))))
        while position < len(articulation):
            following = position + 1
            stamp = articulation[position][0]
            while following < len(articulation) and articulation[following][0] == stamp:
                following += 1
            block = articulation[position:following]
            final = block[-1][2]
            for channel in range(3 if chip == 'psg' else 5):
                previous = state(incoming, channel)
                restored = len(block) > 1 and state(final, channel) == previous
                for src, event_id, mask in block:
                    current = state(mask, channel)
                    if current != previous:
                        terminal = (not restored and src == source_end and current == 0
                                    and event_id == block[-1][1])
                        if restored or terminal:
                            add(end if terminal else source_sample(src),
                                'psg_mode' if chip == 'psg' else 'gate', (current,), channel,
                                src=src, event=event_id,
                                order=2000000000 + event_id if terminal else event_id,
                                origin='observed_terminal_off' if terminal else 'observed_zero_transition')
                    previous = current
            incoming = final
            position = following
    return MusicalPlan(tuple(units), tuple(controls), end, source_end,
        chip_clocks=((chip, int(clock_hz)),), decisions=tuple(decisions),
        metadata=(('adapter', 'accepted_psg_scc_performance'),
                  ('patterns_executable', False), ('volume_clock_hz', hz),
                  ('shared_control_source', 'raw_ordered' if source_raw is not None else 'segment_fallback'),
                  ('coincident_control_order', 'ordered_source_shared_before_accepted_unit_controls'),
                  ('zero_time_native_state', 'restored_same_sample_edges_executable_other_state_retained_by_performance')))

