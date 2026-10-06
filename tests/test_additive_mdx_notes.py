"""Validate note spelling and semantic checks independently of private songs."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'py'))
from additive_mdx_notes import render, verify
from opm_mdx import projected_samples


def plan():
    regs = {0x20:199, 0x28:74, 0x30:0, 0x38:0}
    for b, harmonic in enumerate((1,3,5,7)):
        for base, value in ((0x40,harmonic),(0x60,30+b*5),(0x80,31),(0xa0,0),(0xc0,0),(0xe0,15)):
            regs[base+8*b] = value
    writes = [SimpleNamespace(target_ch=0, mdx_tick=0, register=r, data=d) for r,d in regs.items()]
    writes.append(SimpleNamespace(target_ch=0, mdx_tick=0, register=8, data=120))
    writes.append(SimpleNamespace(target_ch=0, mdx_tick=600, register=8, data=0))
    return writes


class NoteTests(unittest.TestCase):
    def test_long_notes_are_tied_and_volume_preserves_tl_differences(self):
        text, mapping = render(plan(), 600, 'test')
        self.assertIn('@v97', text)
        self.assertIn('b%256 & b%256 & b%88', text)
        self.assertNotIn(' y', text)
        self.assertEqual(mapping[0]['volume'], 97)
        self.assertIn('31,0,0,15,0,10,0,5,0,0,0', text)

    def test_semantic_verifier_accepts_redundant_writes(self):
        writes = plan()
        actual = [(projected_samples(w.mdx_tick),w.register,w.data) for w in writes]
        actual.insert(1,actual[0])
        self.assertTrue(verify(writes,600,actual)['passed'])

    def test_semantic_verifier_rejects_wrong_volume_and_extra_attack(self):
        writes = plan()
        actual = [(projected_samples(w.mdx_tick),w.register,w.data) for w in writes]
        actual += [(100,0x60,99),(200,8,0),(200,8,120)]
        report = verify(writes,600,actual)
        self.assertFalse(report['passed'])
        self.assertGreater(report['state_mismatches'],0)
        self.assertNotEqual(report['expected_key_edges'],report['actual_key_edges'])

    def test_pitch_change_is_tied_not_a_new_attack(self):
        writes = plan()
        writes.insert(-1,SimpleNamespace(target_ch=0,mdx_tick=300,register=0x28,data=76))
        text,mapping = render(writes,600,'test')
        self.assertEqual(len(mapping),2)
        self.assertIn('b%44 &',text)
        self.assertIn('c%256',text)

if __name__ == '__main__':
    unittest.main()
