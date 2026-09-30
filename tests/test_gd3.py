import struct
import sys
import tempfile
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'py'))
from gd3 import title_from_gd3


class Gd3(unittest.TestCase):
    def title(self, fields, language='ja', corrupt=False):
        data=bytearray(0x40); data[:4]=b'Vgm '
        struct.pack_into('<I',data,0x14,0x40-0x14)
        payload=('\0'.join(fields)+'\0').encode('utf-16-le')
        data+=b'Gd3 '+struct.pack('<II',0x100,len(payload)+(2 if corrupt else 0))+payload
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'test.vgm'; path.write_bytes(data)
            return title_from_gd3(path,'test',language)

    def test_languages_and_field_fallback(self):
        fields=['Track','曲','Game','ゲーム','MSX2','','Author','作者','1989','writer','notes']
        self.assertEqual(self.title(fields),'[MSX2]ゲーム(1989) 曲 作者')
        self.assertEqual(self.title(fields,'en'),'[MSX2]Game(1989) Track Author')

    def test_missing_and_malformed(self):
        self.assertEqual(self.title(['']*11),'test')
        with self.assertWarns(UserWarning):
            self.assertEqual(self.title(['']*11,corrupt=True),'test')

    def test_system_is_english_and_date_width_is_normalized(self):
        fields=['Track','曲','Game','ゲーム','ＭＳＸ２','日本語機種','Author','作者',
                '１９８９－１１','writer','notes']
        self.assertEqual(self.title(fields),'[MSX2]ゲーム(1989-11) 曲 作者')
        self.assertEqual(self.title(fields,'en'),'[MSX2]Game(1989-11) Track Author')
        fields[4] = ''
        self.assertEqual(self.title(fields),'ゲーム(1989-11) 曲 作者')

    def test_safe_title_and_length(self):
        fields=['";{\n'+ 'あ'*200]+['']*10
        with self.assertWarns(UserWarning):
            title=self.title(fields)
        self.assertLessEqual(len(title.encode('cp932')),240)
        self.assertNotIn('"',title)
        self.assertNotIn('\n',title)
