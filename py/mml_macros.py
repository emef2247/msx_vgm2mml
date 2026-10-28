"""Lossless target-text macros; never cross synchronization comment boundaries."""
from collections import defaultdict
import re
from mml_sync import _parse, _text
from mml_relative_state import normalize, relative_body, compact_callers, signature
from mml_macro_phrases import prepare as prepare_phrases, contexts, summaries, extend, classify


def compress_macros(text, limit=32):
    # Avoid renumbering externally supplied definitions.
    if re.search(r'^\*\d+\s*=', text, re.M):
        return text
    original = text
    text = prepare_phrases(normalize(text))
    def finish(result):
        result = compact_callers(result)
        if signature(result) != signature(original):
            raise AssertionError('Relative macro preparation changed target state/timing')
        return result
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
            percussion = rhythm and ch == 'f'
            policy_nodes = [_parse(node, rhythm=percussion)[0] if node.startswith('[') else node for node in nodes]
            context = contexts(policy_nodes, percussion)
            node_shapes = summaries(policy_nodes,percussion)
            lengths = list(map(len, nodes))
            has_macro = ['*' in node for node in nodes]
            has_absolute = [not relative_body([node]) for node in nodes]
            for start in range(len(nodes)):
                if nodes[start] == '&' or has_macro[start]:
                    continue
                body_length = 0
                stats = (0,0,0,None,context[0][start],False)
                for width in range(1, min(24, len(nodes)-start)+1):
                    stop = start + width
                    body_length += lengths[stop-1] + (width > 1)
                    if body_length > 160 or has_macro[stop-1] or has_absolute[stop-1]:
                        break
                    stats = extend(stats,node_shapes[stop-1][int(stats[4])])
                    if stats[3] is True:break
                    if width < 4 or nodes[stop-1] == '&':
                        continue
                    if stop < len(nodes) and nodes[stop] == '&':
                        continue
                    seq = tuple(nodes[start:stop])
                    category = classify(stats,context[1][stop],at_end=stop==len(nodes))
                    if not category:continue
                    # Rhythm and melodic commands have different grammars.
                    candidates[(percussion, category, seq)].append((bi, start))
        best = None
        ref = f'*{number}'
        for (_, category, seq), positions in candidates.items():
            body = ' '.join(seq)
            if len(positions) < 2 or len(positions)*(len(body)-len(ref)) - len(f'{ref} = {{ {body} }}\n') <= 0:
                continue
            selected, ends = [], {}
            for bi, start in positions:
                if start >= ends.get(bi, 0):
                    selected.append((bi, start))
                    ends[bi] = start + len(seq)
            saving = len(selected)*(len(body)-len(ref)) - len(f'{ref} = {{ {body} }}\n')
            if len(selected) > 1 and saving > 0 and (best is None or (category,saving) > best[:2]):
                best = category, saving, seq, selected
        if best is None:
            break
        _, _, seq, selected = best
        definitions.append(f'{ref} = {{ ' + ' '.join(seq) + ' }')
        for bi, start in reversed(selected):
            blocks[bi][1][start:start+len(seq)] = [ref]
    if not definitions:
        return finish(text)
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
    return finish(result if len(result) < len(text) else text)
