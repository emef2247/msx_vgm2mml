"""Target-only compaction of the MDX subset emitted by opm_mdx_structure.

Source units and source-loop plans are untouched. Raw writes are never removed.
Setter reuse is conservative at raw tone writes and every source-loop entry.
Duration loops retain the exact encoded rest/note chunk sequence, including
the trailing '&' inside each tied-note loop body (MDX compiler lookahead).
"""
import re

# External MDX MML compiler limit, not a limit on source-loop discovery.
MDX_REPEAT_DEPTH = 64


def tokens(text):
    return re.findall(r'\[|\]\d+|[^\s\[\]]+', text)


def compact(text, track, *, durations=True):
    """Return compact target text and an inspectable decision log.

    Token positions refer to the uncompacted track body, not source events.
    The original target units retain source event/Segment membership.
    """
    source = tokens(text)
    decisions = []
    # These are target interpreter/compiler settings, not native chip state.
    state = {}
    retained = []
    for index, token in enumerate(source):
        if token == '[':
            # The first pass and every back edge must execute the body's first
            # setter. An incoming value alone cannot justify deleting it.
            state = {}
        match = re.fullmatch(r'(@v|@|p|q|D|o)(-?\d+)', token)
        if match:
            kind, value = match.groups()
            if state.get(kind) == value:
                decisions.append(dict(track=track, token_index=index, action='omit_setter',
                                      before=token, after='', reason='unchanged target setting',
                                      bytes_saved=0 if kind == 'o' else 3 if kind == 'D' else 2))
                continue
            state[kind] = value
            if kind == '@':
                # Voice loading refreshes tone/TL/pan at the next note.
                # Keep the following volume/pan setter explicitly on a reload.
                state.pop('@v', None)
                state.pop('p', None)
        elif token.startswith('y'):
            register, _ = map(int, token[1:].split(','))
            # Raw writes bypass the MDX interpreter's cached voice/pan/volume.
            # Reloading the same voice may be necessary to restore operators.
            if 0x40 <= register <= 0xff or 0x20 <= register <= 0x27:
                for kind in ('@', '@v', 'p'):
                    state.pop(kind, None)
        retained.append((index, token))

    if not durations:
        return ' '.join(t for _, t in retained), decisions
    output = []
    index = depth = 0
    while index < len(retained):
        position, token = retained[index]
        if token == '[':
            depth += 1
        elif token.startswith(']'):
            depth -= 1
        if re.fullmatch(r'r%\d+', token):
            duration = int(token[2:])
            blocks, tail = divmod(duration, 128)
            # MDX's rest encoder emits one byte per 128 ticks. A finite loop
            # costs six bytes, so at least eight equal chunks yield a saving.
            if blocks >= 8 and depth < MDX_REPEAT_DEPTH:
                parts, saved = [], 0
                while blocks >= 8:
                    count = min(blocks, 255)
                    parts.append(f'[r%128]{count}')
                    saved += count - 7
                    blocks -= count
                remaining = blocks * 128 + tail
                if remaining:
                    parts.append(f'r%{remaining}')
                replacement = ' '.join(parts)
                output.append(replacement)
                decisions.append(dict(track=track, token_index=position, action='rest_chunks',
                                      before=token, after=replacement,
                                      reason='same ordered 128-tick rest chunks', bytes_saved=saved))
                index += 1
                continue
        if re.fullmatch(r'[a-g][+#-]?%256', token):
            stop = index
            while (stop + 1 < len(retained) and retained[stop][1] == token
                   and retained[stop+1][1] == '&'):
                stop += 2
            count = (stop-index)//2
            if count >= 4 and depth < MDX_REPEAT_DEPTH:
                repeat = min(count, 255)
                replacement = f'[{token} &]{repeat}'
                output.append(replacement)
                decisions.append(dict(track=track, token_index=position, action='tied_chunks',
                                      before=' '.join(t for _, t in retained[index:index+2*repeat]),
                                      after=replacement, reason='identical note-and-tie pairs',
                                      bytes_saved=3*repeat-9))
                index += 2*repeat
                continue
        output.append(token)
        index += 1
    return ' '.join(output), decisions
