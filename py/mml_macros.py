"""Lossless target-text macros; never cross synchronization comment boundaries."""
from collections import defaultdict
import re
from mml_sync import _parse, _text


def compress_macros(text, limit=32):
    # Avoid renumbering externally supplied definitions.
    if re.search(r'^\*\d+\s*=', text, re.M):
        return text
    parts = []
    rhythm = bool(re.search(r'^#opll_mode\s+1\b', text, re.M))
    for line in text.splitlines():
        match = re.fullmatch(r'([1-9a-h])\s+(.*)', line, re.I)
        if match:
            ch, body = match[1].lower(), match[2]
            if parts and isinstance(parts[-1], list) and parts[-1][0] == ch:
                parts[-1][1] += ' ' + body
            else:
                parts.append([ch, body])
        else:
            parts.append(line)
    blocks = [part for part in parts if isinstance(part, list)]
    for block in blocks:
        block[1] = [_text(node) for node in _parse(block[1], rhythm=rhythm and block[0] == 'f')]
    definitions = []
    for number in range(limit):
        candidates = defaultdict(list)
        for bi, (ch, nodes) in enumerate(blocks):
            lengths = list(map(len, nodes))
            has_macro = ['*' in node for node in nodes]
            for start in range(len(nodes)):
                if nodes[start] == '&' or has_macro[start]:
                    continue
                body_length = 0
                for width in range(1, min(24, len(nodes)-start)+1):
                    stop = start + width
                    body_length += lengths[stop-1] + (width > 1)
                    if body_length > 160 or has_macro[stop-1]:
                        break
                    if width < 4 or nodes[stop-1] == '&':
                        continue
                    if stop < len(nodes) and nodes[stop] == '&':
                        continue
                    seq = tuple(nodes[start:stop])
                    # Rhythm and melodic commands have different grammars.
                    candidates[(rhythm and ch == 'f', seq)].append((bi, start))
        best = None
        ref = f'*{number}'
        for (_, seq), positions in candidates.items():
            body = ' '.join(seq)
            if len(positions) < 2 or len(positions)*(len(body)-len(ref)) - len(f'{ref} = {{ {body} }}\n') <= 0:
                continue
            selected, ends = [], {}
            for bi, start in positions:
                if start >= ends.get(bi, 0):
                    selected.append((bi, start))
                    ends[bi] = start + len(seq)
            saving = len(selected)*(len(body)-len(ref)) - len(f'{ref} = {{ {body} }}\n')
            if len(selected) > 1 and saving > 0 and (best is None or saving > best[0]):
                best = saving, seq, selected
        if best is None:
            break
        _, seq, selected = best
        definitions.append(f'{ref} = {{ ' + ' '.join(seq) + ' }')
        for bi, start in reversed(selected):
            blocks[bi][1][start:start+len(seq)] = [ref]
    if not definitions:
        return text
    lines, inserted = [], False
    for part in parts:
        if isinstance(part, str):
            lines.append(part)
            continue
        if not inserted:
            lines.extend(definitions)
            inserted = True
        ch, nodes = part
        line = ch + ' '
        for word in ' '.join(nodes).split():
            if len(line) + len(word) + 1 > 120:
                lines.append(line.rstrip())
                line = ch + ' '
            line += word + ' '
        lines.append(line.rstrip())
    result = '\n'.join(lines) + '\n'
    return result if len(result) < len(text) else text
