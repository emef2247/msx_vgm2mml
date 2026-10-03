"""Build executable source loops before selecting PSG/SCC software envelopes."""
import csv
from collections import Counter
from pathlib import Path
from source_loop_plan import SourceLoopPlan
from mml_envelopes import EnvelopeBank, extract_notes, candidate_curves, settings, render


def prepare(notes, chip, strategy='structural'):
    plans, representatives = {}, {}
    for ch, rows in notes.items():
        keys = [(n.length, n.rest, () if n.rest else settings(n.segment, chip),
                 tuple(n.runs)) for n in rows]
        plan = SourceLoopPlan.build(keys, strategy=strategy)
        plans[ch] = plan
        representatives[ch] = [rows[i] for i in plan.representatives()]
    return plans, representatives


class LoopFirstEnvelopeBank(EnvelopeBank):
    loop_first = True
    source_strategy = 'structural'

    def flush(self):
        counts = Counter()
        prepared = []
        if not self.loop_first:
            for segments, chip, _, _ in self.pending:
                counts.update(candidate_curves(extract_notes(segments, chip)))
            self.select(counts)
        for segments, chip, path, kwargs in self.pending:
            notes = extract_notes(segments, chip)
            plans, representatives = prepare(notes, chip, self.source_strategy)
            counts.update(candidate_curves(representatives))
            prepared.append((segments, chip, path, kwargs, plans, notes, representatives))
        if self.loop_first:
            self.select(counts)
        self.prepared = True
        for segments, chip, path, kwargs, plans, notes, representatives in prepared:
            dump = kwargs.get('dump_path')
            if dump:
                expanded, structural = candidate_curves(notes), candidate_curves(representatives)
                report = str(dump).replace('.target_notes.csv', '.pre_envelope_counts.csv')
                with Path(report).open('w', newline='', encoding='utf-8') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(('volume_runs', 'expanded_count', 'structural_count', 'envelope_id'))
                    for curve, count in sorted(expanded.items()):
                        writer.writerow((str(curve), count, structural[curve],
                                         self.curves.get(curve, self.aliases.get(curve, ''))))
            text = render(segments, chip, self, source_plans=plans, **kwargs)
            Path(path).write_text(text, encoding='utf-8', newline='\n')
        self.pending.clear()


class EnvelopeFirstStructuredBank(LoopFirstEnvelopeBank):
    """Same tree builder/projector, with expanded envelope selection done first."""
    loop_first = False
