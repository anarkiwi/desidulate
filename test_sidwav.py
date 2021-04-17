#!/usr/bin/python3

import os
import unittest
import tempfile
from io import StringIO
import pandas as pd
import sox
from sidlib import get_sid
from sidwav import df2wav, df2samples
from ssf import normalize_ssf


class SidWavTestCase(unittest.TestCase):
    """Test sidwav."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
  
    def tearDown(self):
        self.tmpdir.cleanup() 

    def verify_normalize(self, df_txt):
        sid = get_sid(pal=True)
        df = pd.read_csv(df_txt, dtype=pd.Int64Dtype())
        sid = get_sid(pal=True)
        samples = tuple(df2samples(df, sid))
        df_str = df.to_string() 
        normalized_df = normalize_ssf(df, sid)
        normalized_df_str = normalized_df.to_string()
        self.assertNotEqual(df_str, normalized_df_str)
        normalized_samples = tuple(df2samples(normalized_df, sid))
        if len(samples) == len(normalized_samples):
            self.assertEqual(samples, normalized_samples)
        else:
            for i, j in enumerate(normalized_samples):
                self.assertEqual(j, samples[i])
        print(df_str)
        print(normalized_df_str)

    def test_snare_normalize_ssf(self):
        df_txt = StringIO("""
hashid,count,clock,freq1,pw_duty1,atk1,dec1,sus1,rel1,gate1,sync1,ring1,test1,tri1,saw1,pulse1,noise1,flt1,flt_res,flt_coff,flt_low,flt_band,flt_high,vol,mute1,mute3
1976258253992649556,336,0,7940,2048,0,2,15,7,1,0,0,1,0,0,0,0,,,,,,,15,0,
1976258253992649556,336,19705,,,,,,,,,,-1,,,,1,,,,,,,,,
1976258253992649556,336,39410,-4789,,,,,,,,,,,,,,,,,,,,,,
1976258253992649556,336,39423,,,,,,,,,,,,,1,-1,,,,,,,,,
1976258253992649556,336,59115,-923,,,,,,,,,,,,,,,,,,,,,,
1976258253992649556,336,59128,,,,,,,-1,,,,,,,,,,,,,,,,
1976258253992649556,336,78820,48188,,,,,,,,,,,,,,,,,,,,,,
1976258253992649556,336,78833,,,,,,,,,,,,,-1,1,,,,,,,,,
1976258253992649556,336,118230,,,,13,,,,,,,,,,,,,,,,,,,
1976258253992649556,336,157640,,,,-13,-5,-5,,,,,,,,,,,,,,,,,
""")
        self.verify_normalize(df_txt)

    def test_squeeze_ssf(self):
        df_txt = StringIO("""
hashid,count,clock,freq1,pw_duty1,atk1,dec1,sus1,rel1,gate1,sync1,ring1,test1,tri1,saw1,pulse1,noise1,flt1,flt_res,flt_coff,flt_low,flt_band,flt_high,vol,mute1,mute3
-4489989180376990138,276,0,50416,0,0,1,8,4,1,0,0,1,0,0,0,0,,,,,,,15,0,
-4489989180376990138,276,19705,,,,,,,,,,-1,,,,1,,,,,,,,,
-4489989180376990138,276,39410,,,,,,,-1,,,,,,,,,,,,,,,,
-4489989180376990138,276,118230,,,,14,,,,,,,,,,,,,,,,,,,
-4489989180376990138,276,157640,,,,-13,2,-2,,,,,,,,,,,,,,,,,
""")
        self.verify_normalize(df_txt)

    def test_null_envelope_ssf(self):
        df_txt = StringIO("""
hashid,count,clock,freq1,pw_duty1,atk1,dec1,sus1,rel1,gate1,sync1,ring1,test1,tri1,saw1,pulse1,noise1,flt1,flt_res,flt_coff,flt_low,flt_band,flt_high,vol,mute1,mute3
-5729649771641807184,279,0,50416,0,0,1,8,4,1,0,0,1,0,0,0,0,,,,,,,15,0,
-5729649771641807184,279,19705,,,,,,,,,,-1,,,,1,,,,,,,,,
-5729649771641807184,279,39410,,,,14,,,,,,,,,,,,,,,,,,,
-5729649771641807184,279,39419,,,,,-8,-4,,,,,,,,,,,,,,,,,
-5729649771641807184,279,39468,,,,,,,-1,,,,,,,,,,,,,,,,
""")
        self.verify_normalize(df_txt)

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
            freq_diff = abs(freq_max - test_real_freq)
            self.assertLessEqual(freq_diff, 3)


if __name__ == '__main__':
    unittest.main()
