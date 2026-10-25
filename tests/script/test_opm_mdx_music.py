"""Source note interpretation, score clock evidence and reversible MDX output."""
from pathlib import Path
from dataclasses import replace
import csv
import json
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'scripts')]
from opm_mdx import project_segments
from opm_mdx_music import build_music,infer_clock,duration_spelling,tone_and_level,source_plan
from source_loop_plan import SourceLoopPlan
from source_loop_plan import expanded_tokens
from test_opm_mdx import analyze,wait,write
from test_opm_reader import vgm


class MusicalMdxTests(unittest.TestCase):
    def test_unique_source_leaves_do_not_change_any_shared_planner_candidate_or_tree(self):
        import random
        rng=random.Random(20261007)
        cases=[tuple('ababXabababYccccZ'),tuple('XababcabcabcYababcabcabcZ')]
        cases += [tuple(rng.randrange(8) for _ in range(24)) for _ in range(40)]
        cases += [tuple(i%period for i in range(period*repeats+tail))
                  for period in range(1,7) for repeats in range(2,7) for tail in range(period)]
        for keys in cases:
            optimized=source_plan(keys)
            expected=SourceLoopPlan.build(keys,strategy='structural')
            self.assertEqual(optimized.structure.catalog,expected.structure.catalog)
            self.assertEqual(optimized.tree,expected.tree)

    def build(self,path,folder):
        analysis=analyze(path,folder/'trace')
        before=tuple(analysis.segments)
        clock=infer_clock(before,analysis.source_end_vgmticks)
        plan=project_segments(before,end_vgmticks=analysis.source_end_vgmticks,
                              sample_multiplier=clock['chosen']['multiplier'])
        music=build_music(plan,before)
        self.assertEqual(before,analysis.segments)
        ids=[event for units in music.units.values() for u in units for event in u.source_event_ids]
        self.assertEqual(sorted(ids),sorted(w.source_event_id for w in plan.writes))
        return analysis,plan,music

    def test_held_controls_belong_to_notes_instead_of_rejecting_the_whole_attack(self):
        fixture=ROOT/'tests/fixtures/public/opm/from_mdx/held_controls/held_controls.vgm'
        with tempfile.TemporaryDirectory() as tmp:
            a,p,music=self.build(fixture,Path(tmp))
            attacks=[e for e in a.events if e.rising_mask]
            self.assertEqual(music.summary()['note_units'],len(attacks))
            notes=[u for units in music.units.values() for u in units if u.kind=='note']
            self.assertTrue(any('&' in u.command for u in notes))
            self.assertTrue(any('@v' in u.command for u in notes))
            self.assertTrue(all(len(u.source_event_ids)>1 for u in notes))

    def test_inferred_clock_preserves_every_boundary_and_selects_score_time_when_available(self):
        fixture=ROOT/'tests/fixtures/public/opm/from_mdx/nested_phrase_loops/nested_phrase_loops.vgm'
        with tempfile.TemporaryDirectory() as tmp:
            a,p,music=self.build(fixture,Path(tmp))
            self.assertGreater(p.sample_multiplier,1)
            self.assertLessEqual(p.timing_report()['max_abs_timing_error_samples'],6)
            self.assertEqual(p.timing_report()['collapsed_positive_intervals'],0)
            self.assertIn(f'A @t{256-p.sample_multiplier}',music.text)
            self.assertEqual(music.summary()['note_units'],24)
            self.assertGreater(music.summary()['emitted_loop_commands'],0)
            for track,units in music.units.items():
                commands=[u.command for u in units]
                folded,_=music.plans[track].render(commands)
                self.assertEqual(expanded_tokens(folded),expanded_tokens(' '.join(commands)))

    def test_zero_time_keys_keep_raw_edges_and_have_explicit_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);path=folder/'zero.vgm'
            path.write_bytes(vgm(write(8,120)+write(8,0)+write(8,120)+wait(101)))
            a,p,music=self.build(path,folder)
            body=' '.join(u.command for u in music.units['A'])
            self.assertEqual([x for x in expanded_tokens(body) if x.startswith('y8,')],['y8,120','y8,0','y8,120'])
            reasons=music.summary()['fallback_reasons']
            self.assertIn('zero_duration_attack',reasons)
            self.assertIn('no_complete_terminal_keyoff',reasons)

    def test_uniform_carrier_levels_share_a_voice_without_changing_operator_ratios(self):
        fixture=ROOT/'tests/fixtures/public/opm/from_mdx/held_controls/held_controls.vgm'
        with tempfile.TemporaryDirectory() as tmp:
            a,_,_=self.build(fixture,Path(tmp))
            state=next(e.state for e in a.events if e.rising_mask)
            base,level=tone_and_level(state)
            slots=(8,8,8,8,12,14,14,15)[state.algorithm]
            altered=replace(state,operators=tuple(replace(op,tl=op.tl+1) if slots & (1<<i) else op
                            for i,op in enumerate(state.operators)),
                            channel_registers=tuple((reg,value+1 if 0x60<=reg<0x80 and slots & (1<<((reg-0x60)//8)) else value)
                                                    for reg,value in state.channel_registers))
            changed,changed_level=tone_and_level(altered)
            self.assertEqual(base,changed)
            self.assertEqual(changed_level,level+1)


    def test_note_values_are_target_notation_with_exact_nonstandard_fallback(self):
        self.assertEqual(duration_spelling(12),'16')
        self.assertEqual(duration_spelling(18),'16.')
        self.assertEqual(duration_spelling(48),'4')
        self.assertEqual(duration_spelling(13),'%13')

    def test_inner_pitch_repeats_preserve_one_attack_and_expand_to_all_controls(self):
        setup=write(0x20,0xc7)+write(0x28,0x40)+write(0x30,0)+write(0x38,0)
        for slot in range(4):
            for base,value in ((0x40,1),(0x60,20),(0x80,31),(0xa0,0),(0xc0,0),(0xe0,15)):
                setup+=write(base+slot*8,value)
        for altered in (False,True):
            with self.subTest(altered=altered),tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp);path=folder/'held.vgm'
                body=setup+write(8,120)
                for i in range(20):
                    body+=write(0x30,12 if altered and i==8 else (i%2)*8)+wait(113)
                body+=write(8,0)+wait(113)
                path.write_bytes(vgm(body))
                a,p,music=self.build(path,folder)
                notes=[u for u in music.units['A'] if u.kind=='note']
                self.assertEqual(len(notes),1)
                self.assertEqual(len([e for e in a.events if e.rising_mask]),1)
                self.assertGreater(music.summary()['applied_inner_loops'],0)
                self.assertEqual(expanded_tokens(notes[0].command),expanded_tokens(notes[0].unlooped_command))
                if altered:
                    # A single different KF must survive the surrounding repeats.
                    self.assertIn('D-2',expanded_tokens(notes[0].command))
                self.assertEqual(notes[0].source_end_vgmticks,2260)
                tail=music.units['A'][-1]
                self.assertEqual(tail.source_end_vgmticks,2373)

    def test_same_tick_post_key_tone_edit_cannot_be_overwritten_by_deferred_voice_loading(self):
        setup=write(0x20,0xc7)+write(0x28,0x40)+write(0x30,0)
        for slot in range(4):
            for base,value in ((0x40,1),(0x60,20),(0x80,31),(0xa0,0),(0xc0,0),(0xe0,15)):
                setup+=write(base+slot*8,value)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);path=folder/'ordered.vgm'
            path.write_bytes(vgm(setup+write(8,120)+write(0x60,25)+wait(113)+write(8,0)+wait(113)))
            a,p,music=self.build(path,folder)
            self.assertEqual(music.summary()['note_units'],0)
            self.assertIn('same_tick_post_key_setup',music.summary()['fallback_reasons'])
            emitted=expanded_tokens(' '.join(u.command for u in music.units['A']))
            self.assertLess(emitted.index('y8,120'),emitted.index('y96,25'))
            self.assertIn('y8,0',emitted)

    def test_volume_spelling_cannot_discard_reserved_bits_from_held_raw_tl(self):
        setup=write(0x20,0xc7)+write(0x28,0x40)+write(0x30,0)
        for slot in range(4):
            for base,value in ((0x40,1),(0x60,20),(0x80,31),(0xa0,0),(0xc0,0),(0xe0,15)):
                setup+=write(base+slot*8,value)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);path=folder/'bits.vgm'
            edits=b''.join(write(0x60+slot*8,148) for slot in range(4))
            path.write_bytes(vgm(setup+write(8,120)+wait(113)+edits+wait(113)+write(8,0)+wait(113)))
            a,p,music=self.build(path,folder)
            self.assertEqual(music.summary()['note_units'],1)
            emitted=expanded_tokens(' '.join(u.command for u in music.units['A']))
            for slot in range(4): self.assertIn(f'y{0x60+slot*8},148',emitted)


if __name__=='__main__': unittest.main()
