import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'py'))
from structured_macros import enhance_macros,expanded,select

class StructuredMacros(unittest.TestCase):
    def test_inside_different_loops(self):
        phrase='o4 v12 c8 d8 e8 f8 g8 a8 b8 > c8 < '
        text='#opll_mode 1\n9 '+''.join('['+phrase+'r'+str(n)+']2 ' for n in (4,8,16,32))+'\n'
        result,rows=select(text,32,64,0)
        self.assertTrue(rows)
        self.assertTrue(any(len(path)>1 for row in rows for path,_,_ in __import__('json').loads(row['locations'])))
        self.assertEqual(expanded(text),expanded(result))
        self.assertEqual(text.count('['),result.count('['))

    def test_existing_macros_reselected_and_comments_preserved(self):
        text='*0 = { o4 v12 c8 d8 e8 f8 g8 a8 }\n'
        text+=''.join('; sync '+str(i)+'\n9 [*0 r8]2\n' for i in range(6))
        result=enhance_macros(text)
        self.assertEqual(expanded(text),expanded(result))
        self.assertLessEqual(len(result),len(text))
        self.assertEqual([l for l in text.splitlines() if l.startswith(';')],[l for l in result.splitlines() if l.startswith(';')])

    def test_rhythm_and_ties(self):
        text='#opll_mode 1\n9 '+('o4 v12 [c8 & c8 d8 e8]2 r8 '*8)+'\nf '+('vb15 vs12 [bs: h: s8 h:]2 r8 '*8)+'\n'
        result=enhance_macros(text)
        self.assertEqual(expanded(text),expanded(result))
        self.assertLessEqual(len(result),len(text))

    def test_small_text_unchanged(self):
        self.assertEqual(enhance_macros('9 c4\n'),'9 c4\n')

    def test_long_macro_definitions_are_wrapped(self):
        from structured_macros import emit, parts_from
        body = ' '.join(['v12 c8 d8 e8 f8'] * 12)
        parts, _ = parts_from('9 c4\n')
        parts[0][1] = ['*0']
        result = emit(parts, ['*0 = { ' + body + ' }'])
        self.assertTrue(all(len(line) <= 120 for line in result.splitlines()))
        self.assertEqual(expanded(result), expanded('9 ' + body + '\n'))
