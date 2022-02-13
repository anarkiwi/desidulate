#!/usr/bin/python3

import unittest
from io import StringIO
import pandas as pd
from fileio import read_csv
from sidlib import jittermatch_df, squeeze_diffs, coalesce_near_writes, remove_end_repeats, df_waveform_order, get_sid, calc_vbi_frame, calc_rates, bits2byte


class SIDLibTestCase(unittest.TestCase):

    def test_bits2byte(self):
        df = pd.DataFrame([{'col1': 0, 'col2': 1, 'col3': 0, 'col4': 1}])
        self.assertEqual(10, bits2byte(df, df.columns).iat[0])
        df = pd.DataFrame([{'col1': 1, 'col2': 0, 'col3': 1, 'col4': 0}])
        self.assertEqual(5, bits2byte(df, df.columns).iat[0])
        df = pd.DataFrame([{'col1': 1}])
        self.assertEqual(1, bits2byte(df, df.columns).iat[0])

    def str2df(self, df_str):
        return read_csv(StringIO(df_str), dtype=pd.UInt64Dtype()).set_index('clock')

    def ssfdf(self, df_str, ssf=1):
        df = self.str2df(df_str)
        non_meta_cols = set(df.columns) - {'ssf'}
        if ssf is not None:
            df['ssf'] = ssf
        df = df.reset_index().set_index('ssf')
        df['clock'] += 1024
        return (df, non_meta_cols)

    def test_calc_rates(self):
        sid = get_sid(pal=True)
        df, non_meta_cols = self.ssfdf('''
clock,gate1,freq1,pwduty1,pulse1,noise1,tri1,saw1,test1,sync1,ring1,freq3,test3,flt1,fltcoff,fltres,fltlo,fltband,flthi,fltext,atk1,dec1,sus1,rel1,vol
0,1,,,,,,,1,,,,,,,,,,,,9,0,10,0,15
4946,1,65535,,0,1,0,0,0,,,,,0,,,,,,,,,,,15
39393,1,1669,,0,1,0,0,0,,,,,0,,,,,,,,,,,15
39415,0,1669,,0,0,1,0,0,,,,,0,,,,,,,,,,,15
44191,0,65535,,0,0,1,0,0,,,,,0,,,,,,,,,,,15
44213,0,65535,,0,1,0,0,0,,,,,0,,,,,,,,,,,15
786407,0,65535,,0,1,0,0,0,,,,,0,,,,,,,,,,,15
''')
        rate, pr_speed = calc_rates(sid, 20, df, non_meta_cols)
        self.assertEqual(4798, rate.iat[-1])
        self.assertEqual(4, pr_speed.iat[-1])

        df, non_meta_cols = self.ssfdf('''
clock,gate1,freq1,pwduty1,pulse1,noise1,tri1,saw1,test1,sync1,ring1,freq3,test3,flt1,fltcoff,fltres,fltlo,fltband,flthi,fltext,atk1,dec1,sus1,rel1,vol
20000,1,,,,,,,1,,,,,,,,,,,,2,9,10,15,10
200036,1,2145,,0,0,0,1,0,,,,,0,,,,,,,,,,,10
264219,1,2145,,0,0,0,1,0,,,,,0,,,,,,,,,,,10
''')
        rate, pr_speed = calc_rates(sid, 20, df, non_meta_cols)
        self.assertEqual(sid.clockq, rate.iat[-1])
        self.assertEqual(1, pr_speed.iat[-1])

    def test_frames(self):
        df = pd.DataFrame([
            {'clock': 5000, 'pal_vbi_frame': 0, 'ntsc_vbi_frame': 0},
            {'clock': 10000, 'pal_vbi_frame': 0, 'ntsc_vbi_frame': 0},
            {'clock': 15000, 'pal_vbi_frame': 0, 'ntsc_vbi_frame': 0},
            {'clock': 18000, 'pal_vbi_frame': 0, 'ntsc_vbi_frame': 1},
            {'clock': 20000, 'pal_vbi_frame': 1, 'ntsc_vbi_frame': 1},
            {'clock': 25000, 'pal_vbi_frame': 1, 'ntsc_vbi_frame': 1}])
        self.assertEqual(
            df['pal_vbi_frame'].to_list(),
            calc_vbi_frame(get_sid(pal=True), df['clock']).to_list())
        self.assertEqual(
            df['ntsc_vbi_frame'].to_list(),
            calc_vbi_frame(get_sid(pal=False), df['clock']).to_list())

    def test_remove_end_repeats(self):
        self.assertEqual([1, 2], remove_end_repeats([1, 2]))
        self.assertEqual([1, 2, 3, 1, 2], remove_end_repeats([1, 2, 3, 1, 2, 1, 2, 1, 2]))
        self.assertEqual([1, 2, 3], remove_end_repeats([1, 2, 3, 1, 2, 3]))

    def test_df_waveform_order(self):
        df = self.str2df('''
clock,pulse1,noise1,sync1,ring1,test1,tri1,saw1
0,1,0,,,,,
100,0,1,,,,,
150,0,1,,,,,
200,1,0,,,,,
250,1,0,,,,,
''').reset_index()
        self.assertEqual(['p', 'n', 'p'], df_waveform_order(df))

        df = self.str2df('''
clock,pulse1,noise1,sync1,ring1,test1,tri1,saw1
0,,,,,,,
100,0,1,,,,,
150,0,1,,,,,
200,1,0,,,,,
250,1,0,,,,,
''').reset_index()
        self.assertEqual(['0', 'n', 'p'], df_waveform_order(df))

        df = self.str2df('''
clock,pulse1,noise1,sync1,ring1,test1,tri1,saw1
0,,,,,,,
100,0,1,,,,,
150,0,1,,,,,
200,1,1,,,,,
250,1,0,,,,,
''').reset_index()
        self.assertEqual(['0', 'n', 'np', 'p'], df_waveform_order(df))

        df = self.str2df('''
clock,pulse1,noise1,sync1,ring1,test1,tri1,saw1
0,,,,,,,
100,0,1,,,,,
150,0,1,,,,,
200,1,1,,,,,
250,1,0,,,,,
300,,,,,,,
''').reset_index()
        self.assertEqual(['0', 'n', 'np', 'p', '0'], df_waveform_order(df))

        df = self.str2df('''
clock,pulse1,noise1,sync1,ring1,test1,tri1,saw1
0,1,0,,,,,
50,,,,,,,
75,,,,,,,
100,0,1,,,,,
200,1,0,,,,,
''').reset_index()
        self.assertEqual(['p', '0', 'n', 'p'], df_waveform_order(df))

    def test_jittermatch(self):
        df1 = self.str2df('''
clock,vbi_frame,freq1,pwduty1,gate1,sync1,ring1,test1,tri1,saw1,pulse1,noise1,atk1,dec1,sus1,rel1,vol,fltlo,fltband,flthi,flt1,fltext,fltres,fltcoff,freq3,test3,freq1nunique,pwduty1nunique,volnunique
0,0,,,1,,,1,,,,,0,0,5,5,15,0,0,1,1,0,15,128,,,1,0,1
19346,1,,,1,,,1,,,,,0,0,5,5,15,0,0,1,1,0,15,640,,,1,0,1
19636,1,50416,,1,0,0,0,0,0,0,1,0,0,5,5,15,0,0,1,1,0,15,640,,,1,0,1
39225,2,50416,,1,0,0,0,0,0,0,1,0,15,5,5,15,0,0,1,1,0,15,640,,,1,0,1
39234,2,50416,,1,0,0,0,0,0,0,1,0,15,0,0,15,0,0,1,1,0,15,640,,,1,0,1
39283,2,50416,,0,0,0,0,0,0,0,1,,,,,15,0,0,1,1,0,15,640,,,1,0,1
''').reset_index()
        df2 = self.str2df('''
clock,vbi_frame,freq1,pwduty1,gate1,sync1,ring1,test1,tri1,saw1,pulse1,noise1,atk1,dec1,sus1,rel1,vol,fltlo,fltband,flthi,flt1,fltext,fltres,fltcoff,freq3,test3,freq1nunique,pwduty1nunique,volnunique
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
clock,freq1
80,100
100,100
108,200
116,300
124,400
''')
        df_coalesced = self.str2df('''
clock,freq1
80,100
100,400
108,400
116,400
124,400
''')
        df = coalesce_near_writes(df, ['freq1'], near=16)
        self.assertEqual(df.to_string(), df_coalesced.to_string())

        df = self.str2df('''
clock,freq1
80,100
100,100
101,200
120,200
''')
        df_coalesced = coalesce_near_writes(df, ['freq1'], near=16)
        df = self.str2df('''
clock,freq1
80,100
100,200
101,200
120,200
''')
        self.assertEqual(df.to_string(), df_coalesced.to_string())

        df = self.str2df('''
clock,freq1
100,100
201,200
''')
        df_coalesced = coalesce_near_writes(df, ['freq1'], near=16)
        self.assertEqual(df.to_string(), df_coalesced.to_string())

        df = self.str2df('''
clock,freq1
39085,3747
39123,3594
39132,3338
58651,3338
''')
        df_coalesced = coalesce_near_writes(df, ['freq1'], near=16)
        df = self.str2df('''
clock,freq1
39085,3747
39123,3338
39132,3338
58651,3338
''')
        self.assertEqual(df.to_string(), df_coalesced.to_string())



if __name__ == '__main__':
    unittest.main()
