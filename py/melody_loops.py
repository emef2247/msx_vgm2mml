"""Project Segment candidates into loops without changing expanded commands."""
import csv
from pathlib import Path


def project(body, boundaries, analysis, channel):
    """Only replace identical emitted units at complete target-note boundaries.

    The first iteration can retain different initialization commands. Subsequent
    identical runs are looped verbatim, so relative controls and envelope
    commands expand to the exact original command sequence, including ties.
    """
    _, patterns, uses = analysis
    replacements, report = [], []
    for occurrence_id, use in enumerate(uses):
        if use.repeats < 2:
            continue
        width = len(patterns[use.pattern_id])
        indices = [use.group_start + i * width for i in range(use.repeats + 1)]
        if not all(i in boundaries for i in indices):
            report.append((channel, use.pattern_id, occurrence_id, use.repeats, 0,
                           'target_note_boundary'))
            continue
        cuts = [boundaries[i] for i in indices]
        units = [tuple(body[a:b]) for a, b in zip(cuts, cuts[1:])]
        first, looped = 0, 0
        while first < len(units):
            end = first + 1
            while end < len(units) and units[end] == units[first]:
                end += 1
            count = end - first
            if count > 1 and units[first]:
                text = ' '.join(units[first])
                chunks = []
                remaining = count
                while remaining:
                    n = min(remaining, 255)
                    chunks.append(f'[{text}]{n}' if n > 1 else text)
                    remaining -= n
                replacement = ' '.join(chunks)
                original = ' '.join(body[cuts[first]:cuts[end]])
                if len(replacement) < len(original):
                    replacements.append((cuts[first], cuts[end], replacement))
                    looped += count
            first = end
        report.append((channel, use.pattern_id, occurrence_id, use.repeats, looped,
                       'applied' if looped else 'different_commands_or_no_saving'))
    for start, end, replacement in reversed(replacements):
        body = body[:start] + [replacement] + body[end:]
    return body, report


def dump_projection(dump_path, before, after, report):
    if not dump_path:
        return
    prefix = str(dump_path).removesuffix('.target_notes.csv') + '.melody'
    for label, text in (('before', before), ('after', after)):
        Path(f'{prefix}.{label}.target.mml').write_text(text, encoding='utf-8')
    with open(f'{prefix}.loops.csv', 'w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(('ch', 'pattern_id', 'occurrence_id', 'candidate_repeats',
                         'looped_repeats', 'status'))
        writer.writerows(report)
