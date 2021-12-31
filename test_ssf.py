#!/usr/bin/python3

import os
import tempfile
import unittest
from io import StringIO
import pandas as pd
from sidlib import get_sid, jittermatch_df, reg2state, state2ssfs, squeeze_diffs, coalesce_near_writes
from sidmidi import SidMidiFile, DEFAULT_BPM
from ssf import SidSoundFragment, add_freq_notes_df


class SIDLibTestCase(unittest.TestCase):

    def str2df(self, df_str):
        return pd.read_csv(StringIO(df_str), dtype=pd.UInt64Dtype()).set_index('clock')

    def test_jittermatch(self):
        df1 = self.str2df('''
clock,frame,freq1,pwduty1,gate1,sync1,ring1,test1,tri1,saw1,pulse1,noise1,atk1,dec1,sus1,rel1,vol,fltlo,fltband,flthi,flt1,fltext,fltres,fltcoff,freq3,test3,freq1nunique,pwduty1nunique,volnunique
0,0,,,1,,,1,,,,,0,0,5,5,15,0,0,1,1,0,15,128,,,1,0,1
19346,1,,,1,,,1,,,,,0,0,5,5,15,0,0,1,1,0,15,640,,,1,0,1
19636,1,50416,,1,0,0,0,0,0,0,1,0,0,5,5,15,0,0,1,1,0,15,640,,,1,0,1
39225,2,50416,,1,0,0,0,0,0,0,1,0,15,5,5,15,0,0,1,1,0,15,640,,,1,0,1
39234,2,50416,,1,0,0,0,0,0,0,1,0,15,0,0,15,0,0,1,1,0,15,640,,,1,0,1
39283,2,50416,,0,0,0,0,0,0,0,1,,,,,15,0,0,1,1,0,15,640,,,1,0,1
''').reset_index()
        df2 = self.str2df('''
clock,frame,freq1,pwduty1,gate1,sync1,ring1,test1,tri1,saw1,pulse1,noise1,atk1,dec1,sus1,rel1,vol,fltlo,fltband,flthi,flt1,fltext,fltres,fltcoff,freq3,test3,freq1nunique,pwduty1nunique,volnunique
0,0,,,1,,,1,,,,,0,0,5,5,15,0,0,1,1,0,15,128,,,1,0,1
19410,1,,,1,,,1,,,,,0,0,5,5,15,0,0,1,1,0,15,640,,,1,0,1
19700,1,50416,,1,0,0,0,0,0,0,1,0,0,5,5,15,0,0,1,1,0,15,640,,,1,0,1
39289,2,50416,,1,0,0,0,0,0,0,1,0,15,5,5,15,0,0,1,1,0,15,640,,,1,0,1
39298,2,50416,,1,0,0,0,0,0,0,1,0,15,0,0,15,0,0,1,1,0,15,640,,,1,0,1
39347,2,50416,,0,0,0,0,0,0,0,1,,,,,15,0,0,1,1,0,15,640,,,1,0,1
''').reset_index()
        self.assertEqual(
            df1.drop(['clock'], axis=1).to_string(),
            df2.drop(['clock'], axis=1).to_string())
        self.assertTrue(jittermatch_df(df1, df2, 'clock', 1024))
        self.assertFalse(jittermatch_df(df1, df2, 'clock', 32))

    def test_squeeze_diffs(self):
        df = self.str2df('''
clock,gate1,pulse1,noise1
100,1,1,0
200,1,0,1
''')
        s_df = squeeze_diffs(df, ['gate1', 'pulse1', 'noise1'])
        self.assertEqual(df.to_string(), s_df.to_string())
        df = self.str2df('''
clock,gate1,pulse1,noise1
100,1,1,0
200,1,1,0
300,1,0,1
400,1,0,1
''')
        s_df = squeeze_diffs(df, ['gate1', 'pulse1', 'noise1'])
        df = df[~df.index.isin((200, 400))]
        self.assertEqual(df.to_string(), s_df.to_string())

    def test_coalesce_near_writes(self):
        df = self.str2df('''
clock,gate1,freq1
100,1,100
101,1,200
''')
        df_coalesced = self.str2df('''
clock,gate1,freq1
100,1,200
101,1,200
''')
        df = coalesce_near_writes(df, 16, ['freq1'])
        self.assertEqual(df.to_string(), df_coalesced.to_string())

        df = self.str2df('''
clock,gate1,freq1
100,1,100
201,1,200
''')
        df_coalesced = coalesce_near_writes(df, 16, ['freq1'])
        self.assertEqual(df.to_string(), df_coalesced.to_string())


class SSFTestCase(unittest.TestCase):
    """Test SSF."""

    @staticmethod
    def _df2ssf(df, percussion=True):
        sid = get_sid(pal=True)
        smf = SidMidiFile(sid, DEFAULT_BPM)
        df = add_freq_notes_df(sid, df)
        df['frame'] = df['clock'].floordiv(int(sid.clockq))
        df = df.fillna(method='ffill').set_index('clock')
        return SidSoundFragment(percussion=percussion, sid=sid, smf=smf, df=df)

    def test_notest_ssf(self):
        df = pd.DataFrame(
            [{'hashid': 1, 'count': 1, 'clock': 0, 'freq1': 1024, 'pwduty1': 0, 'atk1': 0, 'dec1': 0, 'sus1': 15, 'rel1': 0, 'gate1': 1, 'sync1': 0, 'ring1': 0, 'test1': 0, 'tri1': 1, 'saw1': 0, 'pulse1': 0, 'noise1': 0, 'flt1': 0, 'fltres': 0, 'fltcoff': 0, 'fltlo': 0, 'fltband': 0, 'flthi': 0, 'vol': 15},
             {'hashid': 1, 'count': 1, 'clock': 1e5, 'gate1': 0}], dtype=pd.UInt64Dtype())
        s = self._df2ssf(df, percussion=True)
        self.assertEqual(s.waveforms, {'tri'})
        self.assertEqual(s.midi_pitches, (35,))
        self.assertEqual(s.total_duration, 98525)
        self.assertEqual(s.midi_notes, ((0, 0, 35, 98525, 127, 60.134765625),))

    def test_test_ssf(self):
        df = pd.DataFrame(
            [{'hashid': 1, 'count': 1, 'clock': 0, 'freq1': 1024, 'pwduty1': 0, 'atk1': 0, 'dec1': 0, 'sus1': 15, 'rel1': 0, 'gate1': 1, 'sync1': 0, 'ring1': 0, 'test1': 1, 'tri1': 1, 'saw1': 0, 'pulse1': 0, 'noise1': 0, 'flt1': 0, 'fltres': 0, 'fltcoff': 0, 'fltlo': 0, 'fltband': 0, 'flthi': 0, 'vol': 15},
             {'hashid': 1, 'count': 1, 'clock': 2 * 1e4, 'test1': 0},
             {'hashid': 1, 'count': 1, 'clock': 1e5, 'gate1': 0}], dtype=pd.UInt64Dtype())
        s = self._df2ssf(df, percussion=True)
        self.assertEqual(s.waveforms, {'tri'})
        self.assertEqual(s.midi_pitches, (35,))
        self.assertEqual(s.total_duration, 78820)
        self.assertEqual(s.midi_notes, ((20000, 1, 35, 78820, 127, 60.134765625),))

    def test_ssf_parser(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_log = os.path.join(tmpdir, 'vicesnd.log')
            sid = get_sid(pal=True)
            smf = SidMidiFile(sid, DEFAULT_BPM)
            with open(test_log, 'w', encoding='utf8') as log:
                log.write('\n'.join((
                    '1 24 15',
                    '1 7 255',
                    '1 8 128',
                    '1 13 255',
                    '100 11 129',
                    '100000 11 0',
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
                if ssf and row.clock == 103:
                    break
            self.assertTrue(row is not None)
            if row:
                self.assertEqual(row.clock, 103)
                self.assertEqual(row.voice, 2)
            self.assertTrue(ssf is not None)
            if ssf:
                ssf.smf_transcribe(smf, 0, 1)
                smf.write(os.devnull)
                self.assertEqual(ssf.midi_pitches, (95,))
                self.assertEqual(ssf.total_duration, 98525)


if __name__ == '__main__':
    unittest.main()
