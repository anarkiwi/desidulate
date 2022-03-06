#!/usr/bin/python3

import os
import unittest
import tempfile
import pandas as pd
import numpy as np
from desidulate.sidwav import state2samples, write_wav, loudestf
from desidulate.sidlib import get_sid


class SidWavTestCase(unittest.TestCase):
    """Test sidwav."""

    @staticmethod
    def _make_wav_df(rows):
        return pd.DataFrame(rows, dtype=pd.UInt64Dtype()).set_index('clock').fillna(method='ffill').astype(pd.UInt64Dtype())

    def _same_samples(self, df1, df2, same=True):
        sid = get_sid(pal=True)
        raw_samples = state2samples(df1, sid)
        sid = get_sid(pal=True)
        raw_samples2 = state2samples(df2, sid)
        self.assertTrue(len(raw_samples))
        self.assertTrue(len(raw_samples2))
        self.assertNotEqual(df1.to_string(), df2.to_string())
        if same:
            self.assertTrue(np.array_equal(raw_samples, raw_samples2))
        else:
            self.assertFalse(np.array_equal(raw_samples, raw_samples2))

    def test_skiptest(self):
        sid = get_sid(pal=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            test_wav = os.path.join(tmpdir, 'test.wav')

            df = self._make_wav_df([
                {'hashid': 1, 'clock': 0, 'freq1': 4000, 'sus1': 15, 'rel1': 15, 'vol': 15, 'gate1': 1, 'test1': 1},
                {'hashid': 1, 'clock': 20000, 'gate1': 0, 'test1': 0, 'tri1': 1},
                {'hashid': 1, 'clock': 200000},
            ])

            write_wav(test_wav, sid, state2samples(df, sid, skiptest=True))
            freq_max = loudestf(test_wav)
            self.assertEqual(freq_max, 235)

    def test_ring_non_tri(self):
        gateon = {'hashid': 1, 'clock': 0, 'freq1': 1024, 'sus1': 15, 'gate1': 1, 'pwduty1': 1024, 'pulse1': 1, 'saw1': 1, 'vol': 15, 'freq3': 512}
        end = {'hashid': 1, 'clock': 1e6 * 20, 'freq1': 0}
        df1 = self._make_wav_df([
            gateon,
            end,
        ])
        gateon['ring1'] = 1
        df2 = self._make_wav_df([
            gateon,
            end,
        ])
        self._same_samples(df1, df2)

    def test_sync_noise(self):
        gateon = {'hashid': 1, 'clock': 0, 'freq1': 1024, 'sus1': 15, 'gate1': 1, 'noise1': 1, 'vol': 15, 'freq3': 512}
        gateoff = {'hashid': 1, 'clock': 1e6 * 10, 'gate1': 0}
        end = {'hashid': 1, 'clock': 1e6 * 20, 'freq1': 0}
        df1 = self._make_wav_df([
            gateon,
            end,
        ])
        gateon['sync1'] = 1
        df2 = self._make_wav_df([
            gateon,
            end,
        ])
        self._same_samples(df1, df2, same=False)

    def test_changes_in_no_rel(self):
        gateon = {'hashid': 1, 'clock': 0, 'freq1': 1000, 'sus1': 15, 'rel': 0, 'gate1': 1, 'tri1': 1, 'vol': 15}
        gateoff = {'hashid': 1, 'clock': 1e6 * 10, 'gate1': 0}
        end = {'hashid': 1, 'clock': 1e6 * 20, 'freq1': 0}
        df1 = self._make_wav_df([
            gateon,
            gateoff,
            end,
        ])
        df2 = self._make_wav_df([
            gateon,
            gateoff,
            {'hashid': 1, 'clock': gateoff['clock'] + 256, 'freq1': gateon['freq1'] * 2},
            end,
        ])
        self._same_samples(df1, df2, same=False)

    def test_no_flt_route(self):
        gateoff = {'hashid': 1, 'clock': 1e6 * 10, 'gate1': 0}
        end = {'hashid': 1, 'clock': 1e6 * 20, 'freq1': 0}
        df1 = self._make_wav_df([
            {'hashid': 1, 'clock': 0, 'freq1': 1000, 'sus1': 15, 'gate1': 1, 'tri1': 1, 'vol': 15, 'flt1': 1, 'fltres': 15, 'fltcoff': 16},
            gateoff,
            end,
        ])
        df2 = self._make_wav_df([
            {'hashid': 1, 'clock': 0, 'freq1': 1000, 'sus1': 15, 'gate1': 1, 'tri1': 1, 'vol': 15, 'flt1': 1, 'fltres': 8, 'fltcoff': 512},
            gateoff,
            end,
        ])
        self._same_samples(df1, df2)

    def test_rel_change_before_gateoff(self):
        gateoff = {'hashid': 1, 'clock': 1e6 * 10, 'gate1': 0}
        end = {'hashid': 1, 'clock': 1e6 * 20, 'freq1': 0}
        rel = 5
        df1 = self._make_wav_df([
            {'hashid': 1, 'clock': 0, 'freq1': 1000, 'sus1': 15, 'gate1': 1, 'tri1': 1, 'vol': 15, 'rel1': rel},
            gateoff,
            end,
        ])
        df2 = self._make_wav_df([
            {'hashid': 1, 'clock': 0, 'freq1': 1000, 'sus1': 15, 'gate1': 1, 'tri1': 1, 'vol': 15, 'rel1': rel * 2},
            {'hashid': 1, 'clock': 1e6 * 1, 'rel1': rel},
            gateoff,
            end,
        ])
        self._same_samples(df1, df2)

    def test_dec_change_before_gateoff(self):
        gateon = {'hashid': 1, 'clock': 0, 'freq1': 1000, 'dec': 2, 'sus1': 10, 'gate1': 1, 'tri1': 1, 'vol': 15}
        gateoff = {'hashid': 1, 'clock': 1e4 * 30, 'gate1': 0}
        end = {'hashid': 1, 'clock': 1e4 * 60, 'freq1': 0}
        df1 = self._make_wav_df([
            gateon,
            gateoff,
            end,
        ])
        df2 = self._make_wav_df([
            gateon,
            {'hashid': 1, 'clock': 1e4 * 10, 'dec': 15},
            gateoff,
            end,
        ])
        self._same_samples(df1, df2)

    def test_sus_change_before_gateoff(self):
        gateon = {'hashid': 1, 'clock': 0, 'freq1': 1000, 'dec': 2, 'sus1': 10, 'gate1': 1, 'tri1': 1, 'vol': 15}
        gateoff = {'hashid': 1, 'clock': 1e4 * 30, 'gate1': 0}
        end = {'hashid': 1, 'clock': 1e4 * 60, 'freq1': 0}
        df1 = self._make_wav_df([
            gateon,
            gateoff,
            end,
        ])
        df2 = self._make_wav_df([
            gateon,
            {'hashid': 1, 'clock': 1e4 * 10, 'sus': 2},
            gateoff,
            end,
        ])
        self._same_samples(df1, df2)

    def test_dec_sus_change_before_gateoff(self):
        gateon = {'hashid': 1, 'clock': 0, 'freq1': 1000, 'dec': 2, 'sus1': 10, 'gate1': 1, 'tri1': 1, 'vol': 15}
        gateoff = {'hashid': 1, 'clock': 1e4 * 30, 'gate1': 0}
        end = {'hashid': 1, 'clock': 1e4 * 60, 'freq1': 0}
        df1 = self._make_wav_df([
            gateon,
            gateoff,
            end,
        ])
        df2 = self._make_wav_df([
            gateon,
            {'hashid': 1, 'clock': 1e4 * 10, 'dec': 15, 'sus': 2},
            gateoff,
            end,
        ])
        self._same_samples(df1, df2)

    def test_df2wav(self):
        sid = get_sid(pal=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            test_wav = os.path.join(tmpdir, 'test.wav')
            for i in range(1, 5):
                test_raw_freq = int(i * 2048)
                test_real_freq = sid.real_sid_freq(test_raw_freq)
                df = self._make_wav_df([
                    {'hashid': 1, 'count': 1, 'clock': 0, 'freq1': test_raw_freq, 'sus1': 15, 'gate1': 1, 'tri1': 1, 'vol': 15},
                    {'hashid': 1, 'count': 1, 'clock': 1e6 * 10, 'gate1': 0}])
                write_wav(test_wav, sid, state2samples(df, sid))
                freq_max = loudestf(test_wav)
                freq_diff = abs(freq_max - test_real_freq)
                self.assertLessEqual(freq_diff, 3)


if __name__ == '__main__':
    unittest.main()
