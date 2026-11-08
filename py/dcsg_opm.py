"""Native DCSG musical units projected to OPM writes.

Ported from x68k_vgm2mml py/dcsg_opm.py (revision
cd5bf4bc44f92108ea1ca9fc62384f170d0247d9, the --emit-vgm
lineage; the file is unchanged at x68k main HEAD), with the
helper pieces it imports bundled here so the module stays
self-contained in this repository:

- the note extraction (Note, audible, settings, extract_notes)
  from x68k py/mml_envelopes.py, restricted to the 'psg' chip
  shape the DCSG views use;
- the note membership map from x68k py/psg_note_units.py;
- the PerformanceWrite/PerformancePlan records from x68k
  py/opm_performance.py, without build_performance and with a
  dump() that writes only the performance CSVs (the target-state
  trajectory audit is not ported; the variant serializer works
  from plan.writes directly).

Adaptations for the MSX variant route:

- the OPM clock is a parameter (``opm_clock``, default the
  X68000 4 MHz the law was derived at). At 4 MHz the projected
  stream is identical to x68k's own --emit-vgm output; the MSX
  layered composition passes the cartridge clock 3579545.
- interpretation views retain SN periods and attenuation order;
  they are not AY registers. OPM pitch, levels, oscillator
  phase and noise are explicitly projected approximations.
"""
import csv
from dataclasses import asdict, dataclass, field, replace
import json
import math
from pathlib import Path

from opm_mdx import mdx_tick
from psg_scc_opm import OPM_CLOCK, carrier_tl, opm_pitch, square_voice


# --- Note extraction, ported from x68k py/mml_envelopes.py ----

@dataclass
class Note:
    segment: object
    start: int
    length: int
    rest: bool
    runs: list = field(default_factory=list)
    envelope: int | None = None
    segment_indices: list = field(default_factory=list)


def _audible(segment):
    if segment.scale == 'r':
        return False
    return bool(segment.mode and (segment.volume or segment.envelope_enabled))


def _settings(segment):
    return (segment.tone_period, segment.octave, segment.scale,
            segment.mode, segment.noise_period if segment.mode & 2 else 0,
            segment.envelope_enabled,
            segment.envelope_period if segment.envelope_enabled else 0,
            segment.envelope_shape if segment.envelope_enabled else 0)


def extract_notes(segments):
    """Group per-channel segment views into notes (chip='psg' rules)."""
    result = {}
    pitch_events = {'fCA', 'fCB'}
    for ch, rows in segments.items():
        notes = []
        boundary = False
        for segment_index, seg in enumerate(rows):
            if seg.ev_type in pitch_events or seg.ev_type == 'evS':
                boundary = True
            if seg.l <= 0:
                continue
            rest = not _audible(seg)
            previous = notes[-1] if notes else None
            contiguous = previous is not None and previous.start + previous.length == seg.ticks
            same = contiguous and previous.rest == rest
            if same and not rest:
                same = (not boundary and _settings(previous.segment) == _settings(seg)
                        and seg.volume <= previous.runs[-1][0])
            if not same:
                notes.append(Note(seg, seg.ticks, 0, rest))
            note = notes[-1]
            note.segment_indices.append(segment_index)
            note.length += seg.l
            if not rest:
                if note.runs and note.runs[-1][0] == seg.volume:
                    volume, length = note.runs[-1]
                    note.runs[-1] = (volume, length + seg.l)
                else:
                    note.runs.append((seg.volume, seg.l))
            boundary = False
        if any(not n.rest for n in notes):
            result[ch] = notes
    return result


def membership(notes):
    """Map (channel, segment index) -> (note index, start, end, rest)."""
    return {(ch, row): (index, note.start, note.start + note.length, note.rest)
            for ch, items in notes.items() for index, note in enumerate(items)
            for row in note.segment_indices}


# --- Performance records, ported from x68k py/opm_performance.py

@dataclass(frozen=True)
class PerformanceWrite:
    write_id: int
    source_chip: str
    source_ch: int | None
    source_row: int | None
    vgmticks: int
    mdx_tick: int
    target_ch: int
    register: int
    data: int
    reason: str
    baseline_write_id: int | None
    performance_row_id: int | None
    inferred_key: bool


@dataclass(frozen=True)
class PerformancePlan:
    writes: tuple
    rows: tuple
    source_end: int
    settings: dict

    @property
    def end_tick(self):
        return mdx_tick(self.source_end)

    def scheduled_writes(self):
        return sorted(self.writes, key=lambda w: (w.mdx_tick, w.target_ch, w.write_id))

    def dump(self, out, stem):
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)

        def csv_file(suffix, rows, fields):
            with (out / (stem + suffix)).open('w', encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
                writer.writeheader()
                writer.writerows(rows)

        csv_file('.opm_performance.csv', self.rows, list(self.rows[0]) if self.rows else
                 ['performance_row_id', 'source_chip', 'source_ch', 'source_row',
                  'vgmticks', 'vgmticks_end', 'inferred_transition'])
        csv_file('.opm_performance.writes.csv', [asdict(w) for w in self.writes],
                 list(PerformanceWrite.__dataclass_fields__))


# --- DCSG projection, ported from x68k py/dcsg_opm.py ----------

@dataclass(frozen=True)
class _NoteView:
    ticks: int
    l: int
    tone_period: int
    volume: int
    scale: str
    ev_type: str
    mode: int
    noise_period: int
    octave: int = 0
    envelope_enabled: int = 0
    envelope_period: int = 0
    envelope_shape: int = 0


def musical_units(analysis):
    """Use native sample time and exact SN period identity for MSX note rules."""
    source, views = {}, {}
    for segment in analysis.segments:
        channel = segment.chip_instance * 4 + segment.ch
        source.setdefault(channel, []).append(segment)
        active = segment.audible and bool(segment.frequency_hz if segment.ch < 3
                                          else segment.noise_shift_hz)
        views.setdefault(channel, []).append(_NoteView(
            segment.start_sample, segment.length_samples, segment.period or 0,
            15 - segment.attenuation if segment.attenuation is not None else 0,
            'c' if active else 'r', 'dcsg_control', 1 if segment.ch < 3 else 2,
            (segment.noise_control or 0) + (segment.tone2_period or 0) * 8))
    notes = extract_notes(views)
    return source, notes, membership(notes)


def project(analysis, *, force=False, pitch_policy='clamp', gain=.125, terminate=True,
            opm_clock=OPM_CLOCK):
    """Return an inspectable PerformancePlan; native source evidence is untouched.

    Six tone lanes use A..F. White-noise intervals share H with deterministic
    lower-instance priority. Periodic, linked and overlapping noise need force omission.
    Mono/stereo routing and the nominal SN two-dB attenuation law are retained.
    """
    if pitch_policy not in ('clamp', 'error'):
        raise ValueError('DCSG OPM pitch policy must be clamp or error')
    if not math.isfinite(gain) or not 0 < gain <= .5:
        raise ValueError('DCSG additive gain must be positive and at most 0.5')
    if any(i['code'] == 'undeclared_dcsg_instance' for i in analysis.issues):
        raise ValueError('DCSG projection requires declared source clock and chip instances')
    source, notes, note_membership = musical_units(analysis)
    omissions, approximations, rows, writes = [], [], [], []
    settings = dict(target_clock=opm_clock, source_chip='dcsg', gain=gain,
        force_enabled=force, pitch_policy=pitch_policy,
        source_segments_retained=True, source_key_observed=False,
        key_origin='musical_attack_inferred', phase_preserved=False,
        sourcegate='inferred_from_source_musical_units',
        source_note_policy='shared MSX extract_notes; native sample periods and volume runs',
        tone_policy='four-harmonic additive square approximation; no oscillator-phase identity',
        channel_map={str(ch): (ch // 4 * 3 + ch % 4 if ch % 4 < 3 else
                               7) for ch in source},
        noise_owner_policy='interval allocation; lower instance wins overlap',
        noise_policy='one OPM7 white-noise lane; N0..30 nearest nominal shift rate',
        forced_omissions=omissions, approximations=approximations,
        source_issues=list(analysis.issues))

    def loss(segment, reason, action='omit_interval'):
        record = dict(source_chip='dcsg', source_ch=segment.chip_instance * 4 + segment.ch,
            chip_instance=segment.chip_instance, native_channel=segment.ch,
            source_row=segment.segment_id, start_vgmticks=segment.start_sample,
            end_vgmticks=segment.end_sample, action=action, count_kind='interval', reason=reason)
        if not force:
            raise ValueError(f"DCSG instance {segment.chip_instance} ch{segment.ch}: {reason}; use --force to omit")
        omissions.append(record)
        return reason

    source_writes = {write.event_id: write for write in analysis.writes}
    for issue in analysis.issues:
        code = issue['code']
        if code not in ('data_before_known_latch', 'stereo_write_on_mono_variant'):
            continue
        write = source_writes[issue['event_id']]
        if not force:
            raise ValueError(f'DCSG instance {write.chip_instance}: {code}; use --force to omit')
        omissions.append(dict(source_chip='dcsg', source_ch=None,
            chip_instance=write.chip_instance, native_channel=None, source_row=None,
            source_event_id=write.source_event_id, native_event_id=write.event_id,
            start_vgmticks=write.vgmticks, end_vgmticks=write.vgmticks,
            command=write.command, register=write.register, known_mask=write.known_mask,
            data=write.data, action='omit_uninterpreted_write', count_kind='write', reason=code))
        if code != 'data_before_known_latch':
            continue
        # Unknown destination can affect any channel, not an observed silent
        # reset. Bound each uncertain interval by that channel's first fully
        # observed state, without muting channels once their state is known.
        for native_ch in range(4):
            channel = write.chip_instance * 4 + native_ch
            stop = analysis.end_sample
            for segment in source.get(channel, ()):
                if segment.end_sample <= write.vgmticks:
                    continue
                known_level = segment.attenuation is not None
                known_muted = known_level and (segment.attenuation == 15 or not
                    (segment.stereo_left or segment.stereo_right))
                known_pitch = (segment.period_known_mask == 1023 if native_ch < 3 else
                    segment.noise_control is not None and (not segment.noise_tone2_coupled
                                                           or segment.tone2_period is not None))
                if known_muted or known_level and known_pitch:
                    stop = max(write.vgmticks, segment.start_sample)
                    break
            if stop > write.vgmticks:
                omissions.append(dict(source_chip='dcsg', source_ch=channel,
                    chip_instance=write.chip_instance, native_channel=native_ch,
                    source_row=None, source_event_id=write.source_event_id,
                    native_event_id=write.event_id, start_vgmticks=write.vgmticks,
                    end_vgmticks=stop, action='omit_unknown_source_state',
                    count_kind='interval', reason='unknown_destination_state_not_assumed_silent'))

    # Native rows and source musical units stay intact. Only the target-noise
    # allocation is split at both chips' boundaries, allowing the other chip
    # to resume as soon as the current owner becomes silent.
    note_by_segment = {segment.segment_id: note_membership.get((ch, index))
        for ch, segments in source.items() for index, segment in enumerate(segments)}
    noise_sources = {ch: segments for ch, segments in source.items() if ch % 4 == 3}
    cuts = sorted({edge for segments in noise_sources.values() for segment in segments
                   for edge in (segment.start_sample, segment.end_sample)})
    allocated = []
    cursors = {ch: 0 for ch in noise_sources}
    for start, stop in zip(cuts, cuts[1:]):
        present, candidates = [], []
        for ch, segments in sorted(noise_sources.items()):
            while cursors[ch] + 1 < len(segments) and segments[cursors[ch]].end_sample <= start:
                cursors[ch] += 1
            segment = segments[cursors[ch]]
            if not segment.start_sample <= start < segment.end_sample:
                continue
            piece = replace(segment, start_sample=start, end_sample=stop)
            present.append(piece)
            if not piece.audible:
                continue
            reason = ('t6w28_cross_chip_routing_not_interpreted' if analysis.config.t6w28 else
                      'unknown_noise_configuration' if piece.noise_control is None or not piece.noise_shift_hz else
                      'periodic_noise_not_supported' if not piece.noise_control & 4 else
                      'tone2_linked_noise_not_supported' if piece.noise_tone2_coupled else '')
            if reason:
                loss(piece, reason)
            else:
                candidates.append(piece)
        if candidates:
            allocated.append(candidates[0])
            for conflict in candidates[1:]:
                loss(conflict, 'opm_single_noise_owner_capacity')
        elif present:
            allocated.append(replace(present[0], audible=False))
    projected_source = {ch: segments for ch, segments in source.items() if ch % 4 < 3}
    if allocated:
        projected_source[3] = allocated

    for lane, segments in sorted(projected_source.items()):
        instance, native_ch = divmod(lane, 4)
        target = instance * 3 + native_ch if native_ch < 3 else 7
        is_noise = native_ch == 3
        channel = lane
        cache, gate, previous_note = {}, False, None
        sample, source_row, row_id = 0, None, None

        def emit(register, data, reason, *, key=False, always=False):
            if not always and cache.get(register) == data:
                return
            cache[register] = data
            writes.append(PerformanceWrite(len(writes), 'dcsg', channel, source_row,
                sample, mdx_tick(sample), target, register, data, reason, None, row_id, key))

        initialized = False
        for segment in segments:
            instance, native_ch = segment.chip_instance, segment.ch
            channel = instance * 4 + native_ch
            sample, source_row, row_id = segment.start_sample, segment.segment_id, len(rows)
            first = len(writes)
            reason = ''
            active = segment.audible
            if active and analysis.config.t6w28:
                reason = loss(segment, 't6w28_cross_chip_routing_not_interpreted')
            elif active and not is_noise and not segment.frequency_hz:
                reason = loss(segment, 'tone_dc_or_unknown_period_not_pitched')
            elif active and is_noise:
                if segment.noise_control is None or not segment.noise_shift_hz:
                    reason = loss(segment, 'unknown_noise_configuration')
                elif not segment.noise_control & 4:
                    reason = loss(segment, 'periodic_noise_not_supported')
                elif segment.noise_tone2_coupled:
                    reason = loss(segment, 'tone2_linked_noise_not_supported')
            active = bool(active and not reason)
            member = note_by_segment.get(segment.segment_id)
            note_id = (channel, member[0]) if member else None
            retrigger = gate and active and note_id != previous_note
            if gate and (not active or retrigger):
                emit(8, target, 'inferred musical release', key=True, always=True)
            if active and not initialized:
                emit(8, target, 'initial key off', always=True)
                emit(0x38 + target, 0, 'disable channel LFO')
                emit(0x28 + target, 0, 'initial pitch')
                emit(0x30 + target, 0, 'initial pitch')
                for bank in range(4):
                    for base, value in ((0x40, 1), (0x60, 127), (0x80, 31),
                                        (0xa0, 0), (0xc0, 0), (0xe0, 15)):
                        emit(base + target + bank * 8, value, 'additive voice setup')
                initialized = True
            kc = kf = actual = error = noise_n = noise_actual = ''
            frequency = segment.frequency_hz if active and not is_noise else None
            if active:
                if is_noise:
                    shift = segment.noise_shift_hz
                    _, noise_n, noise_actual = min((abs(math.log2(
                        opm_clock / (32 * (32 - n)) / shift)), n,
                        opm_clock / (32 * (32 - n))) for n in range(31))
                    emit(15, 128 | noise_n, 'nominal noise shift-rate approximation')
                    harmonics, amplitudes = (1,) * 4, (0., 0., 0., 1.)
                    approximations.append(dict(source_ch=channel, source_row=source_row,
                        start_vgmticks=sample, end_vgmticks=segment.end_sample,
                        action='approximate_noise', reason='LFSR phase/spectrum/reset not preserved',
                        source_rate_hz=shift, target_rate_hz=noise_actual,
                        rate_error_cents=1200 * math.log2(noise_actual / shift)))
                else:
                    kc, kf, actual = opm_pitch(frequency, opm_clock,
                                               clamp=pitch_policy == 'clamp')
                    error = 1200 * math.log2(actual / frequency)
                    if abs(error) > 100 / 128 + 1e-7:
                        approximations.append(dict(source_ch=channel, source_row=source_row,
                            start_vgmticks=sample, end_vgmticks=segment.end_sample,
                            action='clamp_pitch', reason='outside OPM KC/KF range',
                            source_rate_hz=frequency, target_rate_hz=actual,
                            rate_error_cents=error))
                    emit(0x28 + target, kc, 'native tone frequency projected to OPM KC')
                    emit(0x30 + target, kf, 'native tone frequency projected to OPM KF')
                    voice = square_voice()
                    harmonics, amplitudes = voice.harmonics, voice.amplitudes
                amplitude = gain * 10 ** (-segment.attenuation / 10)
                for bank, (multiple, level) in enumerate(zip(harmonics, amplitudes)):
                    emit(0x40 + target + bank * 8, multiple, 'selected square/noise harmonic')
                    emit(0x60 + target + bank * 8, carrier_tl(amplitude * level),
                         'nominal SN two-dB attenuation projected to carrier TL')
                pan = int(segment.stereo_left) * 0x80 | int(segment.stereo_right) * 0x40
                emit(0x20 + target, pan | 7, 'native output routing; additive algorithm')
                if not gate or retrigger:
                    emit(8, target | 0x78, 'inferred musical attack', key=True, always=True)
            transition = ('retrigger' if retrigger else 'attack' if active and not gate else
                          'release' if gate and not active else 'continuation' if active else 'rest')
            rows.append(dict(performance_row_id=row_id, source_chip='dcsg', source_ch=channel,
                chip_instance=instance, native_channel=native_ch, source_row=source_row,
                source_event_id=segment.source_event_id, vgmticks=sample,
                vgmticks_end=segment.end_sample, target_track=chr(65 + target),
                target_audible=active, gate_before=gate, gate_after=active,
                musical_note_id=member[0] if member else None, musical_note_start=member[1] if member else None,
                musical_note_end=member[2] if member else None,
                musical_volume_runs=json.dumps(notes[channel][member[0]].runs) if member else '[]',
                inferred_transition=transition, key_origin='musical_attack_inferred',
                source_key_observed=False, source_period=segment.period,
                source_attenuation=segment.attenuation, frequency_hz=frequency,
                target_kc=kc, target_kf=kf, target_frequency_hz=actual,
                pitch_error_cents=error, noise_n=noise_n, noise_target_rate_hz=noise_actual,
                omission_reason=reason, performance_write_ids=json.dumps(list(range(first, len(writes))))))
            gate, previous_note = active, note_id
        if initialized and terminate:
            sample, source_row, row_id = analysis.end_sample, None, None
            if gate:
                emit(8, target, 'terminal inferred release', key=True, always=True)
            emit(0x20 + target, 7, 'terminal mute')
            if is_noise:
                emit(15, 0, 'terminal noise disabled')
    return PerformancePlan(tuple(writes), tuple(rows), analysis.end_sample, settings)


def dump_projection(plan, outdir, stem):
    """Save native-row membership and all omissions/approximations separately."""
    folder = Path(outdir)
    folder.mkdir(parents=True, exist_ok=True)
    plan.dump(folder, stem)
    paths = {}
    for name in ('forced_omissions', 'approximations'):
        rows = plan.settings[name]
        path = folder / f'{stem}.dcsg_opm.{name}.csv'
        fields = list(dict.fromkeys(k for row in rows for k in row)) or ['source_ch', 'source_row', 'reason']
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        paths[name] = str(path)
    path = folder / f'{stem}.dcsg_opm.json'
    path.write_text(json.dumps(dict(plan.settings, source_end_vgmticks=plan.source_end,
        performance_rows=len(plan.rows), performance_writes=len(plan.writes), paths=paths),
        indent=2) + '\n', encoding='utf-8')
    return path


def console_lines(plan_or_report):
    settings = getattr(plan_or_report, 'settings', plan_or_report)
    omitted = settings.get('forced_omissions', ())
    approximated = settings.get('approximations', ())
    write_count = sum(row.get('count_kind') == 'write' for row in omitted)
    interval_count = len(omitted) - write_count
    lines = [f'DCSG OPM projection: {interval_count} omitted intervals / '
             f'{write_count} omitted writes; {len(approximated)} approximated intervals']
    counts = {}
    for row in omitted:
        kind = row.get('count_kind', 'interval')
        key = row['reason'], kind
        counts[key] = counts.get(key, 0) + 1
    lines.extend(f'  {reason}: {count} {kind}(s)' for (reason, kind), count in sorted(counts.items()))
    if approximated:
        lines.append('  Approximation details: DCSG target report (noise LFSR/phase and pitch clamp).')
    return lines
