#!/usr/bin/python3

import os
import unittest
import tempfile
import pandas as pd
import sox
from sidlib import get_sid
from sidwav import df2wav 


class SidWavTestCase(unittest.TestCase):
    """Test sidwav."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
  
    def tearDown(self):
        self.tmpdir.cleanup() 

    def test_df2wav(self):
        sid = get_sid(pal=True)
        test_wav = os.path.join(self.tmpdir.name, 'test.wav')
        transformer = sox.Transformer()

        for i in range(1, 5):
            test_raw_freq = int(i * 2048)
            test_real_freq = sid.real_sid_freq(test_raw_freq)
            df = pd.DataFrame(
                [{'hashid': -1, 'count': 1, 'clock': 0, 'freq1': test_raw_freq, 'pw_duty1': 0, 'atk1': 0, 'dec1': 0, 'sus1': 15, 'rel1': 0, 'gate1': 1, 'sync1': 0, 'ring1': 0, 'test1': 0, 'tri1': 1, 'saw1': 0, 'pulse1': 0, 'noise1': 0, 'flt1': 1, 'flt_res': 0, 'flt_coff': 0, 'flt_low': 0, 'flt_band': 0, 'flt_high': 0, 'vol': 15},
                 {'hashid': -1, 'count': 1, 'clock': 1e6 * 10, 'gate1': -1}], dtype=pd.Int64Dtype)
            df2wav(df, sid, test_wav)
            power_df = pd.DataFrame(transformer.power_spectrum(test_wav), columns=['freq', 'val'])
            val_max = power_df['val'].max()
            freq_max = power_df[power_df['val'] == val_max].iloc[0]['freq']
            self.assertGreaterEqual(freq_max, test_real_freq - 3)
            self.assertLessEqual(freq_max, test_real_freq + 3)


if __name__ == "__main__":
    unittest.main()
