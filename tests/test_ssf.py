#!/usr/bin/python3

import os
import tempfile
import unittest
import pandas as pd
from desidulate.sidlib import get_sid, reg2state, state2ssfs, calc_vbi_frame
from desidulate.sidmidi import SidMidiFile, MAX_VEL
from desidulate.ssf import SidSoundFragment, add_freq_notes_df


class SSFTestCase(unittest.TestCase):
    """Test SSF."""

    @staticmethod
    def _df2ssf(df, percussion=True):
        sid = get_sid(pal=True)
        smf = SidMidiFile(sid)
        df = add_freq_notes_df(sid, df)
        df['pr_speed'] = 1
        df['vbi_frame'] = calc_vbi_frame(sid, df['clock'])
        df['pr_frame'] = df['vbi_frame'].floordiv(df['pr_speed'])
        df = df.fillna(method='ffill').set_index('clock')
        return SidSoundFragment(percussion=percussion, sid=sid, smf=smf, df=df)

    def test_adsr(self):
        sid = get_sid(pal=True)
        smf = SidMidiFile(sid)
        self.assertEqual(127, smf.sid_adsr_to_velocity(0, None, atk1=0, dec1=0, sus1=15, rel1=0, gate1=1))
        self.assertEqual(59, smf.sid_adsr_to_velocity(0, None, atk1=0, dec1=0, sus1=7, rel1=0, gate1=1))
        self.assertEqual(32, smf.sid_adsr_to_velocity(20e3, None, atk1=7, dec1=0, sus1=0, rel1=0, gate1=1))
        self.assertEqual(32, smf.sid_adsr_to_velocity(20e3, None, atk1=7, dec1=0, sus1=1, rel1=0, gate1=1))
        self.assertEqual(8, smf.sid_adsr_to_velocity(20e3, 20e3, atk1=7, dec1=0, sus1=1, rel1=0, gate1=0))
        self.assertEqual(127, smf.sid_adsr_to_velocity(0, None, atk1=0, dec1=1, sus1=8, rel1=8, gate1=1))

    def test_notest_ssf(self):
        df = pd.DataFrame(
            [{'hashid': 1, 'count': 1, 'clock': 0, 'freq1': 1024, 'pwduty1': 0, 'atk1': 0, 'dec1': 0, 'sus1': 15, 'rel1': 0, 'gate1': 1, 'sync1': 0, 'ring1': 0, 'test1': 0, 'tri1': 1, 'saw1': 0, 'pulse1': 0, 'noise1': 0, 'flt1': 0, 'fltres': 0, 'fltcoff': 0, 'fltlo': 0, 'fltband': 0, 'flthi': 0, 'vol': 15},
             {'hashid': 1, 'count': 1, 'clock': 1e5, 'gate1': 0}], dtype=pd.UInt64Dtype())
        s = self._df2ssf(df, percussion=True)
        self.assertEqual(s.waveforms, {'tri'})
        self.assertEqual(s.midi_pitches, (35,))
        self.assertEqual(s.total_duration, 98280)
        self.assertEqual(s.midi_notes, ((0, 35, s.total_duration, MAX_VEL, 60.134765625),))

    def test_test_ssf(self):
        df = pd.DataFrame(
            [{'hashid': 1, 'count': 1, 'clock': 0, 'freq1': 1024, 'pwduty1': 0, 'atk1': 0, 'dec1': 0, 'sus1': 15, 'rel1': 0, 'gate1': 1, 'sync1': 0, 'ring1': 0, 'test1': 1, 'tri1': 1, 'saw1': 0, 'pulse1': 0, 'noise1': 0, 'flt1': 0, 'fltres': 0, 'fltcoff': 0, 'fltlo': 0, 'fltband': 0, 'flthi': 0, 'vol': 15},
             {'hashid': 1, 'count': 1, 'clock': 2 * 1e4, 'test1': 0},
             {'hashid': 1, 'count': 1, 'clock': 1e5, 'gate1': 0}], dtype=pd.UInt64Dtype())
        s = self._df2ssf(df, percussion=True)
        self.assertEqual(s.waveforms, {'tri'})
        self.assertEqual(s.midi_pitches, (35,))
        self.assertEqual(s.total_duration, 78624)
        self.assertEqual(s.midi_notes, ((20000, 35, s.total_duration, MAX_VEL, 60.134765625),))

    def test_ssf_parser(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_log = os.path.join(tmpdir, 'vicesnd.log')
            sid = get_sid(pal=True)
            smf = SidMidiFile(sid)
            with open(test_log, 'w', encoding='utf8') as log:
                log.write('\n'.join((
                    '1 24 15',
                    '1 7 255',
                    '1 8 128',
                    '1 13 255',
                    '100 11 129',
                    '100000 11 128',
                    '')))
            ssf_log_df, ssf_dfs, = state2ssfs(sid, reg2state(test_log))
            ssf_log_df.reset_index(level=0, inplace=True)
            ssf_dfs.reset_index(level=0, inplace=True)
            ssf_dfs = add_freq_notes_df(sid, ssf_dfs)
            ssf = None
            row = None
            for row in ssf_log_df.itertuples():
                ssf_df = ssf_dfs[ssf_dfs['hashid'] == row.hashid].set_index('clock')
                ssf = SidSoundFragment(True, sid, ssf_df, smf)
                if ssf and row.clock == 104:
                    break
            self.assertTrue(row is not None)
            if row:
                self.assertEqual(row.clock, 104)
                self.assertEqual(row.voice, 2)
            self.assertTrue(ssf is not None)
            if ssf:
                self.assertTrue(ssf.df[ssf.df.pr_frame.isna()].empty)
                ssf.smf_transcribe(smf, 0, 1)
                smf.write(os.devnull)
                self.assertEqual(ssf.midi_pitches, (95,))
                self.assertEqual(ssf.total_duration, 117936)


if __name__ == '__main__':
    unittest.main()
