"""Build executable source loops before selecting PSG/SCC software envelopes."""
import csv
import json
from collections import Counter
from pathlib import Path
from source_loop_plan import SourceLoopPlan
from mml_envelopes import EnvelopeBank, candidate_curves, settings, render, build_performance


def prepare(notes, chip, strategy='structural', score_guided=False, guide_keys=None):
    plans, representatives = {}, {}
    for ch, rows in notes.items():
        keys = [n.structural_key if hasattr(n, 'structural_key') else
                (n.length, n.rest, () if n.rest else settings(n.segment, chip), tuple(n.runs))
                for n in rows]
        plan = SourceLoopPlan.build(keys, strategy=strategy)
        if score_guided:
            from score_structure import partition_key,variant_representatives,GuidedLoopPlan
            score_keys=[guide_keys[ch,i] if guide_keys is not None else
                        partition_key(n,rows[i-1] if i else None) for i,n in enumerate(rows)]
            guide=SourceLoopPlan.build(score_keys,strategy=strategy)
            representatives[ch]=variant_representatives(guide,rows,chip)
            plans[ch]=GuidedLoopPlan(guide,plan)
        else:
            plans[ch] = plan
            representatives[ch] = [rows[i] for i in plan.representatives()]
    return plans, representatives


class LoopFirstEnvelopeBank(EnvelopeBank):
    loop_first = True
    source_strategy = 'structural'
    score_guided = False

    def flush(self):
        counts = Counter()
        prepared = []
        if not self.loop_first:
            for segments, chip, _, kwargs in self.pending:
                counts.update(candidate_curves(dict(kwargs['performance'].channels),kwargs['performance'].tick_clock_hz))
            if any(kwargs.get('score_timing') and kwargs['score_timing'].tempo!=225
                   for _,_,_,kwargs in self.pending):counts.clear()
            self.select(counts)
        for segments, chip, path, kwargs in self.pending:
            performance = kwargs.get('performance')
            if performance is None:
                performance = build_performance(segments, chip)
                kwargs = dict(kwargs, performance=performance)
            notes = dict(performance.channels)
            guide_keys=None
            if self.score_guided and getattr(self,'score_guide',None) is not None:
                from score_structure import guided_partition_keys
                guide_keys=guided_partition_keys(self.score_guide,performance,getattr(self,'guide_bindings',()))
            plans, representatives = prepare(notes, chip, self.source_strategy,self.score_guided,guide_keys)
            counts.update(candidate_curves(representatives,performance.tick_clock_hz))
            prepared.append((segments, chip, path, kwargs, plans, notes, representatives))
        if self.loop_first:
            if any(kwargs.get('score_timing') and kwargs['score_timing'].tempo!=225
                   for _,_,_,kwargs,_,_,_ in prepared):
                # Uniform tied-envelope compensation is validated at tempo225.
                # Other score tempi retain the curve as timed inline controls.
                counts.clear()
            self.select(counts)
        self.prepared = True
        for segments, chip, path, kwargs, plans, notes, representatives in prepared:
            dump = kwargs.get('dump_path')
            if dump:
                expanded, structural = candidate_curves(notes,performance.tick_clock_hz), candidate_curves(representatives,performance.tick_clock_hz)
                score_slots=candidate_curves({ch:[notes[ch][i] for i in plan.guide.representatives()]
                    if hasattr(plan,'guide') else representatives[ch] for ch,plan in plans.items()},performance.tick_clock_hz)
                report = str(dump).replace('.target_notes.csv', '.pre_envelope_counts.csv')
                with Path(report).open('w', newline='', encoding='utf-8') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(('volume_runs', 'expanded_count', 'structural_count', 'envelope_id',
                                     'score_slot_first_curve_count','structural_variant_count'))
                    for curve, count in sorted(expanded.items()):
                        writer.writerow((str(curve), count, structural[curve],
                                         self.curves.get(curve, self.aliases.get(curve, '')),
                                         score_slots[curve],structural[curve]))
            text = render(segments, chip, self, source_plans=plans, **kwargs)
            Path(path).write_text(text, encoding='utf-8', newline='\n')
            if dump and self.score_guided:
                summary=dict(score_guided=True,source_notes=sum(map(len,notes.values())),
                    exact_curve_variants=sum(map(len,representatives.values())),
                    selected_envelopes=len(self.curves),
                    channels={str(ch):plan.comparison for ch,plan in plans.items()},
                    cuts_applied=False,pitch_and_timbre_normalized=False)
                Path(str(dump).replace('.target_notes.csv','.score_guide.loops.json')).write_text(
                    json.dumps(summary,indent=2)+'\n',encoding='utf-8')
        self.pending.clear()


class EnvelopeFirstStructuredBank(LoopFirstEnvelopeBank):
    """Same tree builder/projector, with expanded envelope selection done first."""
    loop_first = False


class ScoreGuidedEnvelopeBank(LoopFirstEnvelopeBank):
    """Candidate score repeats precede selection of every exact curve variant."""
    score_guided = True
