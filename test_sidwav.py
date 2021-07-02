#!/usr/bin/python3

import os
import unittest
import tempfile
import pandas as pd
import sox
from sidwav import state2samples, write_wav
from sidlib import get_sid


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
                [{'hashid': 1, 'count': 1, 'clock': 0, 'freq1': test_raw_freq, 'sus1': 15, 'gate1': 1, 'tri1': 1, 'vol': 15},
                 {'hashid': 1, 'count': 1, 'clock': 1e6 * 10, 'gate1': 0}], dtype=pd.UInt64Dtype()).set_index('clock')
            df = df.fillna(method='ffill').astype(pd.UInt64Dtype())
            write_wav(test_wav, sid, state2samples(df, sid))
            power_df = pd.DataFrame(transformer.power_spectrum(test_wav), columns=['freq', 'val'])
            val_max = power_df['val'].max()
            freq_max = power_df[power_df['val'] == val_max].iloc[0]['freq']
            freq_diff = abs(freq_max - test_real_freq)
            self.assertLessEqual(freq_diff, 3)


if __name__ == '__main__':
    unittest.main()
