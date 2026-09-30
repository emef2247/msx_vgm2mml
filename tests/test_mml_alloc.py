import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'py'))
from mml_alloc import parse_alloc, override_alloc


class AllocOverride(unittest.TestCase):
    def test_partial_and_case(self):
        source='#alloc { 9=100, a=200, f=300 }\n9 c4\n'
        self.assertEqual(override_alloc(source,parse_alloc(' A=3780 ')),
                         '#alloc { 9=100, a=3780, f=300 }\n9 c4\n')
        self.assertEqual(override_alloc(source,None),source)

    def test_full(self):
        value='9=1800, a=3780, b=1480, c=2850, d=4750, f=600'
        self.assertIn('#alloc { '+value+' }',override_alloc('#alloc { 9=10 }\n',parse_alloc(value)))

    def test_invalid(self):
        for value in ('', 'a=-1','a=65536','z=10','a=2,A=3','a=2,','a=2\n9 c4'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_alloc(value)
