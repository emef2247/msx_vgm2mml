"""Annotate generated melodic MGSDRV MML at shared musical-time boundaries.

The clock is the target MML clock: %48 is a quarter note. Source ticks and
Segment analysis are not changed. This is not a general MGSDRV compiler.
"""
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
import re



_TRACK = re.compile(r'^([1-9a-hA-H])\s+(.*)$')
_TOKEN = re.compile(
    r'\s+|\[|\]\d*|\*\d+|@[a-z#\\]?[-+]?\d+|@f|'
    r'l(?:%\d+|\d+)\.*|h[ofi]|[sk][of]|'
    r'[a-gr][+#-]?(?:%\d+|\d+)?\.*|'
    r'[ovqktpmnsy/\\][-+]?\d+(?:,[-+]?\d+)*|[<>&]|[()]\d*', re.I)
_NOTE = re.compile(r'[a-gr][+#-]?(%\d+|\d+)?(\.*)', re.I)


@dataclass
class TimedToken:
    text: str
    start: int
    end: int
    children: tuple = ()


def _parse(body):
    """Keep finite loop structure; reject unsupported syntax rather than miscount."""
    root, stack = [], []
    current = root
    position = 0
    for match in _TOKEN.finditer(body):
        if match.start() != position:
            raise ValueError(f'Unsupported MML near {body[position:position + 24]!r}')
        position = match.end()
        token = match.group()
        if token.isspace():
            continue
        if token == '[':
            stack.append(current)
            current = []
        elif token.startswith(']'):
            if not stack:
                raise ValueError('Unmatched MML loop end')
            count = int(token[1:] or 2)
            if count == 0:
                raise ValueError('Infinite MML loops have no finite sync timeline')
            children, current = current, stack.pop()
            current.append((children, count))
        else:
            current.append(token)
    if position != len(body) or stack:
        raise ValueError('Unsupported or incomplete MML')
    return root


def _text(node):
    if isinstance(node, str):
        return node
    children, count = node
    return '[' + ' '.join(map(_text, children)) + ']' + str(count)


def _duration(length, dots, default):
    if not length:
        value = default
    elif length.startswith('%'):
        value = int(length[1:])
    else:
        denominator = int(length)
        if denominator <= 0:
            raise ValueError('MML note divisor must be positive')
        value = 192 // denominator
    addition = value
    for _ in dots:
        addition //= 2
        value += addition
    return value


def _time(nodes, state, macros, expanding=()):
    result = []
    for node in nodes:
        start = state['step']
        if isinstance(node, tuple):
            body, count = node
            children = []
            for _ in range(count):
                children.extend(_time(body, state, macros, expanding))
            result.append(TimedToken(_text(node), start, state['step'], tuple(children)))
            continue
        if node.startswith('*'):
            name = node[1:]
            if name in expanding or name not in macros:
                raise ValueError(f'Undefined or recursive MML macro *{name}')
            children = _time(macros[name], state, macros, expanding + (name,))
            result.append(TimedToken(node, start, state['step'], tuple(children)))
            continue
        state['tokens'] += 1
        if state['tokens'] > 3000000:
            raise ValueError('MML sync analysis exceeds 3 million expanded tokens per track')
        if node.lower().startswith('l'):
            match = re.fullmatch(r'l(%\d+|\d+)(\.*)', node, re.I)
            state['default'] = _duration(*match.groups(), state['default'])
        else:
            match = _NOTE.fullmatch(node)
            if match:
                state['step'] += _duration(*match.groups(), state['default'])
        result.append(TimedToken(node, start, state['step']))
    return result


def _leaves(nodes):
    for node in nodes:
        if node.children:
            yield from _leaves(node.children)
        else:
            yield node


def analyze_mml(text):
    """Return timed tracks, their safe boundaries, and the untouched header."""
    bodies, header = {}, []
    brace_depth = 0
    for line in text.splitlines():
        code = line.split(';', 1)[0]
        match = _TRACK.match(code) if brace_depth == 0 else None
        if match:
            bodies.setdefault(match[1].lower(), []).append(match[2])
        else:
            # Drop only timing annotations from the previous output format.
            if not re.match(r'^\s*;\s*(?:tick count:|ch[1-9a-h]\s+(?:start|end:)|ch[1-9a-h]\s+--- step|sync marks|sync points:)', line, re.I):
                header.append(line)
        brace_depth += code.count('{') - code.count('}')
    macros = {m.group(1): _parse(m.group(2)) for m in
              re.finditer(r'^\*(\d+)\s*=\s*\{([^}]*)\}', text, re.M)}
    tracks, boundaries = {}, {}
    for channel, lines in bodies.items():
        state = dict(step=0, default=48, tokens=0)
        nodes = _time(_parse(' '.join(lines)), state, macros)
        bounds = {0}
        for node in _leaves(nodes):
            if node.end > node.start:
                bounds.add(node.end)
            if node.text == '&':
                bounds.discard(node.start)
        if state['step'] > 0:
            tracks[channel] = nodes
            boundaries[channel] = bounds
        else:
            # Zero-duration setup commands still belong to their track.
            header.extend(f'{channel} {line}' for line in lines)
    return tracks, boundaries, header


def sync_points(tracks, boundaries, min_gap=0):
    """All still-playing channels must have a boundary; ended tracks are silent."""
    if min_gap < 0:
        raise ValueError('Minimum sync gap must be nonnegative')
    totals = {ch: nodes[-1].end for ch, nodes in tracks.items()}
    if not totals:
        return {}
    end = max(totals.values())
    votes = Counter(step for bounds in boundaries.values() for step in bounds)
    marks = {0: 'start'}
    previous = 0
    for step in sorted(votes):
        if not 0 < step < end:
            continue
        required = sum(total >= step for total in totals.values())
        if votes[step] == required and step - previous >= min_gap:
            marks[step] = f'token-boundary {required}/{required}ch'
            previous = step
    marks[end] = 'end'
    return marks


def _split_nodes(nodes, marks):
    """Keep complete loops/macros; expand only ones crossed by a sync mark."""
    for node in nodes:
        index = bisect_right(marks, node.start)
        crosses = index < len(marks) and marks[index] < node.end
        if node.children and crosses:
            yield from _split_nodes(node.children, marks)
        else:
            yield node


def proportional_allocations(usage, total=15000):
    """Distribute the pool by estimated MML size, resolving rounding exactly."""
    active = {ch: used for ch, used in usage.items() if used > 0}
    weight = sum(active.values())
    if not weight:
        return {}
    result = {ch: total * used // weight for ch, used in active.items()}
    remaining = total - sum(result.values())
    order = sorted(active, key=lambda ch: -(total * active[ch] % weight))
    for ch in order[:remaining]:
        result[ch] += 1
    return result


def _has_sound(nodes):
    volume = 8
    for node in _leaves(nodes):
        token = node.text.lower()
        if re.fullmatch(r'v[-+]?\d+', token):
            volume = int(token[1:])
        elif token.startswith('('):
            volume = max(0, volume - int(token[1:] or 1))
        elif token.startswith(')'):
            volume = min(15, volume + int(token[1:] or 1))
        elif node.end > node.start and token[0] != 'r' and volume > 0:
            return True
    return False


def annotate_sync_points(text, line_width=120, min_gap=0, drop_silent=False):
    """Replace local tick counts with shared step comments without retiming notes."""
    tracks, boundaries, header = analyze_mml(text)
    if drop_silent:
        tracks = {ch: nodes for ch, nodes in tracks.items() if _has_sound(nodes)}
        boundaries = {ch: bounds for ch, bounds in boundaries.items() if ch in tracks}
        header = [line for line in header if not _TRACK.match(line)]
        if not any(ch in tracks for ch in '9abcdefgh'):
            cleaned = []
            in_voice = False
            for line in header:
                if re.match(r'^@v\d+\s*=', line):
                    in_voice = '}' not in line
                    continue
                if in_voice:
                    if '}' in line:
                        in_voice = False
                    continue
                if 'OPLL part' in line or 'OPLL Voice Table' in line or line.startswith(';@voice') or line.startswith('; ================='):
                    continue
                cleaned.append(line)
            header = cleaned
    # PSG and SCC share the envelope bank; emit shared definitions only once.
    seen_envelopes = set()
    unique_header = []
    for line in header:
        if re.match(r'^@e\d+\s*=', line):
            if line in seen_envelopes:
                continue
            seen_envelopes.add(line)
        unique_header.append(line)
    header = unique_header
    marks = sync_points(tracks, boundaries, min_gap=min_gap)
    ordered_marks = sorted(marks)
    rendered, allocations = [], {}
    for channel, nodes in tracks.items():
        pending, pending_size = [], 0
        emitted = set()
        body = []

        def flush():
            nonlocal pending_size
            if pending:
                body.append(f'{channel} ' + ' '.join(pending))
                pending.clear()
                pending_size = 0

        for node in _split_nodes(nodes, ordered_marks):
            if node.start in marks and node.start not in emitted:
                flush()
                body.append(f'; ch{channel} --- step {node.start} : {marks[node.start]} ---')
                emitted.add(node.start)
            if pending and pending_size + len(node.text) + 1 > line_width:
                flush()
            pending.append(node.text)
            pending_size += len(node.text) + 1
        flush()
        total = nodes[-1].end
        if total in marks and total not in emitted:
            body.append(f'; ch{channel} --- step {total} : {marks[total]} ---')
        # Textual size estimate of the emitted track (not its playback duration).
        used = sum(len(re.sub(r'\s', '', line.split(' ', 1)[1]))
                   for line in body if not line.startswith(';'))
        allocations[channel] = used if _has_sound(nodes) else 0
        rendered.extend(body + [''])

    # Replace old per-chip allocations with one shared budget.
    clean_header = []
    in_alloc = False
    for line in header:
        if line.lstrip().startswith('#alloc'):
            in_alloc = '{' in line and '}' not in line
            continue
        if in_alloc:
            if '}' in line:
                in_alloc = False
            continue
        clean_header.append(line)
    shares = proportional_allocations(allocations)
    header = clean_header
    if shares:
        header.append('#alloc { ' + ', '.join(f'{ch}={value}' for ch, value in shares.items()) + ' }')
    note = '; sync marks: all active channels at token boundaries; clock: %48 = quarter'
    # Extracting track lines leaves their separators in the header. Keep only
    # one blank line between the remaining definitions and comments.
    compact_header = []
    for line in header:
        if line.strip():
            compact_header.append(line)
        elif compact_header and compact_header[-1]:
            compact_header.append('')
    return '\n'.join(compact_header).rstrip() + '\n' + note + '\n\n' + '\n'.join(rendered)
