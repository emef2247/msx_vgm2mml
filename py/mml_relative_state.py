"""Target-only octave/volume canonicalization before shared macro selection."""
from functools import lru_cache
import re

from mml_sync import _parse, analyze_mml, _leaves


ABSOLUTE = re.compile(r'(?<![a-z@])[ov](?:[bsmch])?[-+]?\d+', re.I)


def relative_body(words):
    """Absolute state belongs to callers, including setters inside nested loops."""
    return not ABSOLUTE.search(' '.join(words))


def _freeze(nodes):
    return tuple(( _freeze(n[0]), n[1]) if isinstance(n, tuple) else n for n in nodes)


def _domain(key):
    return (None, *range(1, 9)) if key == 'o' else (None, *range(16))


def _step(token, key, value):
    absolute = re.fullmatch(key+r'([-+]?\d+)', token, re.I)
    if absolute:
        number = int(absolute[1])
        return number if number in _domain(key)[1:] else None
    delta = 0
    if key == 'o' and token in ('<', '>'):
        delta = 1 if token == '>' else -1
    elif key == 'v' and re.fullmatch(r'[()]\d*', token):
        delta = int(token[1:] or 1) * (1 if token[0] == ')' else -1)
    if not delta:
        return value
    changed = None if value is None else value+delta
    return changed if changed in _domain(key)[1:] else None


@lru_cache(maxsize=4096)
def _table(nodes, key):
    """Finite transfer table: preserve unknown/out-of-range state conservatively."""
    domain = _domain(key)
    values = list(domain)
    for node in nodes:
        if isinstance(node, tuple):
            body, count = node
            transfer = dict(zip(domain, _table(body, key)))
            # Compose powers, rather than expanding nested repeats.
            while count:
                if count & 1:
                    values = [transfer[v] for v in values]
                transfer = {v: transfer[transfer[v]] for v in domain}
                count >>= 1
        else:
            values = [_step(node, key, v) for v in values]
    return tuple(values)


def _end(nodes, state):
    frozen = _freeze(nodes)
    return {key: dict(zip(_domain(key), _table(frozen, key)))[value]
            for key, value in state.items()}


def normalize(text, audit=None):
    """Expand generated macros; separate entry setters from relative gestures.

    Loop bodies start with unknown state so their first absolute reset survives
    every iteration. Macro selection must leave those reset tokens outside bodies.
    """
    from structured_macros import parts_from, emit
    parts, rhythm = parts_from(text)
    states = {}
    hw_states = {}
    def walk(nodes, state, path, hw):
        result = []
        for index, node in enumerate(nodes):
            location = path+(index,)
            if isinstance(node, tuple):
                body, count = node
                rewritten, _, _ = walk(body, dict(o=None, v=None), location, None)
                result.append((rewritten, count))
                state = _end([node], state)
                # The body's last shape/volume command decides the exit mode;
                # without transfer tables for it, stay conservative.
                hw = None
                continue
            match = re.fullmatch(r'([ov])([-+]?\d+)', node, re.I)
            if match:
                key, value = match[1].lower(), int(match[2])
                previous = state[key]
                emitted = node
                if previous is not None and value in _domain(key)[1:]:
                    delta = value-previous
                    # A v command also leaves hardware-envelope mode, so a
                    # numerically redundant v is still observable while that
                    # mode is (or may be) active. Only drop it when the
                    # channel is known to be in fixed-volume mode.
                    if not (key == 'v' and delta == 0 and hw is not False):
                        emitted = (('>' if delta > 0 else '<') if key == 'o'
                                   else (')' if delta > 0 else '(')) * abs(delta)
                if emitted:
                    # Separate tokens allow both state evaluation and macro matching.
                    result.extend(_parse(emitted))
                if audit is not None:
                    audit.append(dict(location=str(location), parameter=key,
                                      previous=previous, absolute=value, emitted=emitted))
                if key == 'v':
                    hw = False
            else:
                result.append(node)
                if re.fullmatch(r's\d+', node, re.I):
                    hw = True
                elif re.fullmatch(r'[()]\d*', node):
                    hw = False
            state = {key: _step(node, key, value) for key, value in state.items()}
        return result, state, hw
    for index, part in enumerate(parts):
        if not isinstance(part, list):
            continue
        channel, nodes = part
        if rhythm and channel == 'f':
            continue
        part[1], states[channel], hw_states[channel] = walk(
            nodes, states.get(channel, dict(o=None, v=None)), (index,),
            hw_states.get(channel, False))
    return emit(parts, [])


def signature(text):
    """Timed observable commands plus octave/volume/HW-envelope state.

    Setter spelling is ignored, but a v command is not a pure volume
    setter: it also leaves hardware-envelope mode, so that mode is part
    of the observable state at every timed command.
    """
    result = {}
    rhythm = bool(re.search(r'^#opll_mode\s+1\b', text, re.M))
    for channel, nodes in analyze_mml(text)[0].items():
        state = dict(o=None, v=None)
        hw = False
        rows = []
        for token in _leaves(nodes):
            word = token.text
            if not (rhythm and channel == 'f') and re.fullmatch(r'[ov][-+]?\d+|[<>]|[()]\d*', word, re.I):
                state = {key: _step(word, key, value) for key, value in state.items()}
                if re.fullmatch(r'v[-+]?\d+|[()]\d*', word, re.I):
                    hw = False
            else:
                if re.fullmatch(r's\d+', word, re.I):
                    hw = True
                rows.append((word, token.start, token.end, state['o'], state['v'], hw))
        result[channel] = (tuple(rows), state['o'], state['v'], hw)
    return result


def compact_callers(text):
    """Use absolute spelling for >=3 consecutive relative steps outside macros."""
    definitions = {m[1]: m[2] for m in re.finditer(r'^\*(\d+)\s*=\s*\{([^}]*)\}', text, re.M)}
    states = {}; parts = []; braces = 0
    rhythm = bool(re.search(r'^#opll_mode\s+1\b', text, re.M))
    def expand(nodes):
        result = []
        for node in nodes:
            if isinstance(node, tuple):
                result.append((expand(node[0]), node[1]))
            elif node.startswith('*'):
                result.extend(expand(_parse(definitions[node[1:]])))
            else:
                result.append(node)
        return result
    def walk(nodes, state):
        output = []; index = 0
        while index < len(nodes):
            node = nodes[index]
            if isinstance(node, tuple):
                body, _ = walk(node[0], dict(o=None, v=None))
                output.append((body, node[1]))
                state = _end(expand([node]), state)
            elif node in ('<', '>', '(', ')'):
                stop = index+1
                while stop < len(nodes) and nodes[stop] == node:
                    stop += 1
                key = 'o' if node in ('<', '>') else 'v'
                after = _end(nodes[index:stop], state)
                if stop-index >= 3 and after[key] is not None:
                    output.append(f'{key}{after[key]}')
                else:
                    output.extend(nodes[index:stop])
                state = after; index = stop; continue
            else:
                output.append(node)
                state = _end(expand([node]), state)
            index += 1
        return output, state
    for line in text.splitlines():
        code, separator, comment = line.partition(';')
        match = re.fullmatch(r'([1-9a-h])\s+(.*)', code, re.I) if braces == 0 else None
        if match:
            channel = match[1].lower()
            if parts and isinstance(parts[-1], list) and parts[-1][0] == channel:
                parts[-1][1] += ' '+match[2]
            else:
                parts.append([channel, match[2]])
            if separator:
                parts.append(';'+comment)
        else:
            parts.append(line)
        braces += code.count('{')-code.count('}')
    for part in parts:
        if not isinstance(part, list):continue
        channel, body = part
        percussion = rhythm and channel == 'f'
        nodes = _parse(body, rhythm=percussion)
        if percussion:
            part[1] = nodes
        else:
            part[1], states[channel] = walk(nodes, states.get(channel, dict(o=None, v=None)))
    from structured_macros import emit
    return emit(parts, [])
