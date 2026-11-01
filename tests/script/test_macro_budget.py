"""The MGSC macro-definition budget expands macros without changing state."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))
from macro_budget import enforce_macro_budget
from mml_relative_state import signature


class MacroBudgetTest(unittest.TestCase):
    def test_under_budget_is_unchanged(self):
        text = "#title test\n*0 = { c d e f }\n1 *0 *0\n"
        result, expanded = enforce_macro_budget(text, 5500)
        self.assertEqual(result, text)
        self.assertEqual(expanded, [])

    def test_expansion_fits_budget_and_preserves_signature(self):
        body = ' '.join(['c8 d8 e8 f8'] * 6)
        lines = ['#title test']
        lines += [f'*{n} = {{ {body} n{n} }}' for n in range(8)]
        lines.append('1 ' + ' '.join(f'*{n}' for n in range(8)) + ' ' +
                     ' '.join(f'*{n}' for n in range(8)))
        text = '\n'.join(lines) + '\n'
        result, expanded = enforce_macro_budget(text, 400)
        self.assertTrue(expanded)
        remaining = [line for line in result.split('\n') if line.startswith('*')]
        prefix = len('\n'.join(result.split('\n')[:result.split('\n').index(remaining[-1]) + 1])) if remaining else 0
        self.assertLessEqual(prefix, 400)
        self.assertEqual(signature(result), signature(text))


if __name__ == '__main__':
    unittest.main()
