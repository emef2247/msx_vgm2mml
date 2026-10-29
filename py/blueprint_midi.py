"""Write an editable blueprint as SMF type 1 using only the standard library.

Input is the same finite, projected score used for blueprint MML. Native chip
curves, synthesis and PCM are not translated into MIDI control streams.
"""
from collections import defaultdict
from fractions import Fraction
import struct

PPQN = 480
VELOCITY = 96


def _vlq(value):
    if type(value) is not int or not 0 <= value <= 0x0fffffff:
        raise ValueError('SMF variable length value must fit 28 unsigned bits')
    result = [value & 127]
    value >>= 7
    while value:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(reversed(result))


def _meta(kind, data):
    return bytes((255, kind)) + _vlq(len(data)) + data


def _text(kind, value):
    return _meta(kind, value.encode('utf-8'))


def _track(events, end):
    body = bytearray()
    previous = 0
    for tick, order, data in sorted(events, key=lambda event: event[:2]):
        if type(tick) is not int or not previous <= tick <= end:
            raise ValueError('MIDI score event has invalid absolute time')
        body.extend(_vlq(tick - previous));body.extend(data)
        previous = tick
    body.extend(_vlq(end - previous));body.extend(b'\xff\x2f\x00')
    if len(body)>0xffffffff:raise ValueError('SMF track exceeds its 32-bit chunk size')
    return b'MTrk' + struct.pack('>I', len(body)) + body


def render(report, title='Blueprint'):
    """Return SMF bytes plus track/channel provenance for this MML page."""
    tempo = report['tempo']
    if type(tempo) is not int or not 1 <= tempo <= 255:
        raise ValueError('Invalid blueprint tempo')
    end = report['end_step']
    if type(end) is not int or end < 0:
        raise ValueError('Invalid blueprint end step')
    # SMF tempo is a 24-bit microsecond value. Very slow scores require an
    # explicit metric scale while retaining their physical event timing.
    scale = max(1, (60000000 + tempo*0xffffff - 1) // (tempo*0xffffff))
    microseconds = round(Fraction(60000000, tempo*scale))
    ticks_per_step = PPQN // 48 * scale
    end_tick = end*ticks_per_step
    conductor = [(0, 0, _text(3, title)),
        (0, 1, _meta(0x51, microseconds.to_bytes(3, 'big'))),
        (0, 2, _text(1, f'Score tempo {tempo}; metric scale {scale}; fixed velocity {VELOCITY}; source timbres/volume curves omitted'))]
    groups = defaultdict(list)
    for note in report['score_notes']:
        start, stop, pitch = note['step_start'], note['step_end'], note['midi_note']
        if (type(start) is not int or type(stop) is not int or not 0 <= start < stop <= end
                or type(pitch) is not int or not 0 <= pitch <= 127):
            raise ValueError('Invalid blueprint MIDI note')
        groups[(note['source_device'], note['source_section'], note['track'])].append(note)
    tracks = [_track(conductor, end_tick)]
    mappings = []
    melodic = 0
    for identity, notes in sorted(groups.items()):
        percussion = all(note['percussion'] for note in notes)
        if percussion:
            port, channel = 0, 9
        else:
            port, slot = divmod(melodic, 15)
            channel = slot if slot < 9 else slot+1
            melodic += 1
        if port > 127:
            raise ValueError('Blueprint exceeds the supported MIDI port count')
        label = f'{identity[0]} / {identity[1]} -> blueprint track {identity[2]}'
        events = [(0, -4, _text(3, label)), (0, -3, _meta(0x21, bytes((port,))))]
        if not percussion:events.append((0, -2, bytes((0xc0 | channel, 0))))
        spans=[]
        for note in sorted(notes,key=lambda row:(row['step_start'],row['step_end'])):
            if (not percussion and spans and not note['attack'] and
                    spans[-1]['unit_id']==note['unit_id'] and
                    spans[-1]['midi_note']==note['midi_note'] and
                    spans[-1]['step_end']==note['step_start']):
                spans[-1]['step_end']=note['step_end']
            else:
                spans.append(dict(note))
        for note in spans:
            pitch = note['midi_note']
            events.append((note['step_end']*ticks_per_step, 0, bytes((0x80 | channel, pitch, 0))))
            events.append((note['step_start']*ticks_per_step, 1, bytes((0x90 | channel, pitch, VELOCITY))))
        tracks.append(_track(events, end_tick))
        mappings.append(dict(source_device=identity[0],source_section=identity[1],
            blueprint_track=identity[2],midi_track=len(tracks)-1,midi_port=port,
            midi_channel=channel+1,percussion=percussion,note_count=len(notes)))
    if len(tracks) > 65535:raise ValueError('Too many SMF tracks')
    header = b'MThd' + struct.pack('>IHHH', 6, 1, len(tracks), PPQN)
    return header+b''.join(tracks), dict(format=1,ppqn=PPQN,score_tempo=tempo,
        microseconds_per_quarter=microseconds,metric_scale=scale,
        ticks_per_score_step=ticks_per_step,end_tick=end_tick,velocity=VELOCITY,
        note_count=sum(len(notes) for notes in groups.values()),tracks=mappings,
        notes='finite score; same-pitch retriggers retained; UTF-8 documentary track names')
