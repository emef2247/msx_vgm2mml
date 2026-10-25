"""Pure MGSDRV target compensation for uniform tied software-envelope notes.

Native evidence and musical curves are not changed. Refuse uncertain schedules
rather than compensating one shared envelope differently for different uses.
"""
import re

from mml_envelopes import envelope_data
from mml_sync import analyze_mml, _leaves

_DEFINITION = re.compile(r'(@e(\d+)\s*=\s*\{)([^}]*)(\})', re.I)
_NOTE = re.compile(r'([a-gr][+#-]?)(?:%\d+|\d+)?\.*', re.I)


def _curve(body):
    items = [item.strip() for item in body.split(',')]
    if len(items) < 3 or items[:2] != ['0', '0']:
        raise ValueError('Unsupported software envelope header')
    result = []
    for item in items[2:]:
        match = re.fullmatch(r'([0-9A-Fa-f])(?::(\d+))?', item)
        if not match:
            raise ValueError('Unsupported software envelope data')
        volume, length = int(match[1], 16), int(match[2] or 1)
        if not 1 <= length <= 255:
            raise ValueError('Software envelope hold must be 1..255')
        if result and result[-1][0] == volume:
            result[-1] = (volume, result[-1][1] + length)
        else:
            result.append((volume, length))
    return tuple(result)


def compensate(texts, *, tempo):
    """Return rewritten chip texts and evidence, or raise atomically if unsafe."""
    if tempo not in (75, 225):
        raise ValueError('Envelope tie compensation supports tempo 75 or 225 only')
    factor = tempo // 75
    interval = 255 // factor
    definitions = {}
    for text in texts.values():
        for clock in re.findall(r'^\s*#tempo\s+(\S+)', text, re.M | re.I):
            if clock != str(tempo):
                raise ValueError('Conflicting target tempo')
        for match in _DEFINITION.finditer(text):
            number = int(match[2]); curve = _curve(match[3])
            if number in definitions and definitions[number] != curve:
                raise ValueError(f'Conflicting envelope definition @e{number}')
            definitions[number] = curve
    usages = {}
    for name, text in texts.items():
        tracks = analyze_mml(text)[0]
        for channel, nodes in tracks.items():
            if any(re.fullmatch(r't[-+]?\d+(?:,[-+]?\d+)*', n.text.lower()) for n in _leaves(nodes)):
                raise ValueError('Dynamic target tempo is unsupported')
            if channel not in '12345678':
                continue
            env, hardware, volume, binding = 0, False, 0, 0
            chain = None; tied = False

            def active_varying(number, is_hardware, level):
                return not is_hardware and level > 0 and len(definitions.get(number, ())) > 1

            def finish():
                if chain is None or chain['hardware'] or chain['volume'] == 0:
                    return
                number = chain['env']
                if number not in definitions:
                    raise ValueError(f'Undefined software envelope @e{number}')
                curve = definitions[number]
                if len(curve) < 2:
                    return
                duration = chain['length']
                expected = list(range(interval, duration, interval))
                if chain['cuts'] != expected:
                    raise ValueError(f'Nonuniform tied continuations for @e{number}')
                usages.setdefault(number, []).append(dict(text=name, channel=channel,
                    start_step=chain['start'], duration_frames=duration,
                    tie_frames=list(chain['cuts'])))

            for node in _leaves(nodes):
                token = node.text.lower()
                if re.fullmatch(r't[-+]?\d+(?:,[-+]?\d+)*', token):
                    raise ValueError('Dynamic target tempo is unsupported')
                match = re.fullmatch(r'@e(\d+)', token)
                if match:
                    env = int(match[1]); hardware = False; binding += 1
                elif re.fullmatch(r'@\d+', token):
                    env = 0; binding += 1
                elif re.fullmatch(r'v\d+', token):
                    next_volume = int(token[1:])
                    if volume != next_volume:
                        binding += 1
                    volume = next_volume; hardware = volume == 16
                elif re.fullmatch(r'[()]\d*', token):
                    amount = int(token[1:] or 1)
                    next_volume = max(0, min(15, volume + (amount if token[0] == ')' else -amount)))
                    if next_volume != volume or hardware:
                        binding += 1
                    volume = next_volume; hardware = False
                elif re.fullmatch(r's\d+', token):
                    hardware = True; binding += 1
                elif token == '&':
                    if chain is None or tied:
                        raise ValueError('Unbound tied continuation')
                    tied = True
                elif node.end > node.start:
                    note = _NOTE.fullmatch(token)
                    if note is None:
                        raise ValueError('Unsupported timed target token')
                    rest = note[1] == 'r'
                    length = node.end - node.start
                    needs_compensation = (active_varying(env, hardware, volume)
                                          or tied and active_varying(chain['env'], chain['hardware'], chain['volume']))
                    if needs_compensation and (node.start % factor or length % factor):
                        raise ValueError('Fractional-frame target note is unsupported')
                    if tied:
                        needs_compensation = (active_varying(chain['env'], chain['hardware'], chain['volume'])
                                              or active_varying(env, hardware, volume))
                        if needs_compensation and (rest or chain['binding'] != binding
                                                   or chain['env'] != env or chain['hardware'] != hardware):
                            raise ValueError('Envelope binding changes across tied continuation')
                        chain['cuts'].append(chain['length'])
                        chain['length'] += length // factor
                    else:
                        finish()
                        chain = None if rest else dict(env=env, hardware=hardware,
                            volume=volume, binding=binding, start=node.start,
                            length=length // factor, cuts=[])
                    tied = False
                    if chain is not None and active_varying(env, hardware, volume) and length > 255:
                        raise ValueError('Target note exceeds 255-step encoding')
            if tied:
                raise ValueError('Incomplete tied continuation')
            finish()
    replacements = {}; rows = []
    for number, uses in sorted(usages.items()):
        curve = definitions[number]
        padded = []; cursor = 0; total_extra = 0
        # Every validated use follows the same score-step partition. Prefix uses
        # consume only the corresponding prefix of this compensated definition.
        full_end = sum(duration for _, duration in curve)
        cuts = range(interval, full_end, interval)
        for volume, duration in curve:
            extra = sum(cursor <= boundary < cursor + duration for boundary in cuts)
            padded.append((volume, duration + extra)); cursor += duration; total_extra += extra
        data = envelope_data(padded)
        if len(data) > 220:
            raise ValueError(f'Compensated @e{number} exceeds definition length budget')
        replacements[number] = ' 0, 0, ' + data + ' '
        rows.append(dict(envelope_id=number, original_curve=[list(run) for run in curve],
                         encoded_curve=[list(run) for run in padded],
                         tie_interval_frames=interval, tie_interval_steps=255,
                         padded_holds=total_extra, affected_usages=uses))
    rewritten = {name: _DEFINITION.sub(lambda match: match[1] +
                 replacements.get(int(match[2]), match[3]) + match[4], text)
                 for name, text in texts.items()}
    return rewritten, dict(tempo=tempo, definitions=rows,
                           affected_usages=sum(len(uses) for uses in usages.values()),
                           compensated_definitions=len(rows))
