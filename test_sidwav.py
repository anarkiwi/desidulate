#!/usr/bin/python3

import os
import unittest
import tempfile
import pandas as pd
import numpy as np
from sidwav import state2samples, write_wav, loudestf
from sidlib import get_sid


class SidWavTestCase(unittest.TestCase):
    """Test sidwav."""

    @staticmethod
    def _make_wav_df(rows):
        return pd.DataFrame(rows, dtype=pd.UInt64Dtype()).set_index('clock').fillna(method='ffill').astype(pd.UInt64Dtype())

    def _same_samples(self, df1, df2):
        sid = get_sid(pal=True)
        raw_samples = state2samples(df1, sid)
        sid = get_sid(pal=True)
        raw_samples2 = state2samples(df2, sid)
        self.assertTrue(len(raw_samples))
        self.assertTrue(len(raw_samples2))
        self.assertNotEqual(df1.to_string(), df2.to_string())
        self.assertTrue(np.array_equal(raw_samples, raw_samples2))

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

    def test_start_waveform0(self):
        sid = get_sid(pal=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            test_wav = os.path.join(tmpdir, 'test.wav')

            gateon = {'hashid': 1, 'clock': 0, 'gate1': 1, 'dec1': 2, 'rel1': 2, 'vol': 15}
            sawon = {'hashid': 1, 'clock': 20000, 'saw1': 1, 'freq1': 1000}
            gateoff = {'hashid': 1, 'clock': 60000, 'gate1': 0}
            df = self._make_wav_df([
                gateon,
                sawon,
                gateoff,
            ])
            write_wav(test_wav, sid, state2samples(df, sid))
            freq_max = loudestf(test_wav)
            self.assertEqual(freq_max, 0)
            gateon['sus1'] = 15
            df = self._make_wav_df([
                gateon,
                sawon,
                gateoff,
            ])
            write_wav(test_wav, sid, state2samples(df, sid))
            freq_max = loudestf(test_wav)
            self.assertEqual(freq_max, 16)

    def test_start_waveform0_atk(self):
        sid = get_sid(pal=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            test_wav = os.path.join(tmpdir, 'test.wav')

            df = self._make_wav_df([
                {'hashid': 1, 'clock': 0, 'freq1': 8192, 'gate1': 1, 'test1': 1, 'atk11': 15, 'dec1': 15, 'vol': 15},
                {'hashid': 1, 'clock': 512, 'gate1': 1, 'test1': 1},
                {'hashid': 1, 'clock': 1024, 'gate1': 1, 'saw1': 1, 'test1': 0},
                {'hashid': 1, 'clock': 102400, 'gate1': 0},
            ])
            write_wav(test_wav, sid, state2samples(df, sid))
            freq_max = loudestf(test_wav)
            self.assertEqual(freq_max, 481)

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
