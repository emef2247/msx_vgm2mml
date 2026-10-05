import unittest
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from analyze_wav import analyze

class WavAnalysisTests(unittest.TestCase):
    def test_tone_and_antiphase_do_not_cancel(self):
        rate=32768
        x=.5*np.sin(2*np.pi*1024*np.arange(rate)/rate)
        stats,f,p,_=analyze(np.column_stack((x,-x)),rate,2)
        self.assertAlmostEqual(stats['rms_dbfs'], -9.0309, places=3)
        self.assertAlmostEqual(stats['spectral_centroid_hz'], 1024, delta=1)
        self.assertEqual(f[np.argmax(p)],1024)
        self.assertLess(stats['energy_above_4khz_fraction'],1e-8)
    def test_gain_changes_level_not_shape(self):
        rate=32768
        x=np.sin(2*np.pi*8192*np.arange(rate)/rate)[:,None]
        a,_,_,_=analyze(x*.5,rate,2)
        b,_,_,_=analyze(x*.25,rate,2)
        self.assertAlmostEqual(a['rms_dbfs']-b['rms_dbfs'],6.0206,places=3)
        self.assertAlmostEqual(a['spectral_centroid_hz'],b['spectral_centroid_hz'])
        self.assertGreater(a['energy_above_4khz_fraction'],.999)
    def test_silence_has_no_invented_centroid(self):
        stats,_,_,_=analyze(np.zeros((4096,2)),44100,2)
        self.assertIsNone(stats['rms_dbfs'])
        self.assertIsNone(stats['spectral_centroid_hz'])

if __name__ == '__main__': unittest.main()
