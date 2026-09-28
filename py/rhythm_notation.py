"""Shorten emitted rhythm notation without discovering or changing patterns."""
import re
from mml_sync import _parse, _text, _duration


_VOLUME = re.compile(r'v([bsmch])(\d+)$')
_HIT = re.compile(r'([bsmch]+|r)(%\d+|\d+)(\.*)$')


def _final_volumes(nodes, incoming):
    state = dict(incoming)
    for node in nodes:
        if isinstance(node, tuple):
            state = _final_volumes(node[0], state)
        else:
            match = _VOLUME.fullmatch(node)
            if match:
                state[match[1]] = int(match[2])
    return state


def _volumes(nodes, incoming):
    state, output = dict(incoming), []
    for node in nodes:
        if isinstance(node, tuple):
            body, count = node
            final = _final_volumes(body, state)
            # A loop body must work both on first entry and after its own end.
            entry = state if count == 1 else {
                key: value for key, value in state.items() if final.get(key) == value}
            shortened, _ = _volumes(body, entry)
            output.append((shortened, count))
            state = final
        else:
            match = _VOLUME.fullmatch(node)
            if match:
                key, value = match[1], int(match[2])
                if state.get(key) == value:
                    continue
                state[key] = value
            output.append(node)
    return output, state


def _lengths(nodes, default):
    output = []
    for node in nodes:
        if isinstance(node, tuple):
            output.append((_lengths(node[0], default), node[1]))
        else:
            match = _HIT.fullmatch(node)
            if match and _duration(match[2], match[3], 48) == default:
                # A colon terminates a compound rhythm hit; rests need none.
                node = match[1] + ('' if match[1] == 'r' else ':')
            output.append(node)
    return output


def optimize(text, raw_ticks=False):
    """Accept only the explicit absolute commands emitted by rhythm_mml."""
    if not text.strip():
        return text
    body = ' '.join(line.split(' ', 1)[1] for line in text.splitlines() if line.startswith('f '))
    nodes, _ = _volumes(_parse(body, rhythm=True), {})
    def spelling(items):
        return ' '.join(_text(item) for item in items)
    best = spelling(nodes)
    candidates = set()
    def collect(items):
        for node in items:
            if isinstance(node, tuple):
                collect(node[0])
            else:
                match = _HIT.fullmatch(node)
                if match:
                    candidates.add(_duration(match[2], match[3], 48))
    collect(nodes)
    for length in sorted(candidates):
        suffix = str(192 // length) if not raw_ticks and 192 % length == 0 else f'%{length}'
        trial = f'l{suffix} ' + spelling(_lengths(nodes, length))
        if len(trial) < len(best):
            best = trial
    return '\nf ' + best + '\n'
