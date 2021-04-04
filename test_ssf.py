#!/usr/bin/python3

import unittest
import pandas as pd
from sidlib import get_sid
from sidmidi import SidMidiFile
from ssf import SidSoundFragment


class SSFTestCase(unittest.TestCase):
    """Test SSF."""

    def test_ssf(self):
        sid = get_sid(pal=True)
        smf = SidMidiFile(sid, 125)
        df = pd.DataFrame(
            [{'hashid': -1, 'count': 1, 'clock': 0, 'freq1': 1024, 'pw_duty1': 0, 'atk1': 0, 'dec1': 0, 'sus1': 15, 'rel1': 0, 'gate1': 1, 'sync1': 0, 'ring1': 0, 'test1': 0, 'tri1': 1, 'saw1': 0, 'pulse1': 0, 'noise1': 0, 'flt1': 1, 'flt_res': 0, 'flt_coff': 0, 'flt_low': 0, 'flt_band': 0, 'flt_high': 0, 'vol': 15},
             {'hashid': -1, 'count': 1, 'clock': 1e6 * 10, 'gate1': -1}], dtype=pd.Int64Dtype)
        s = SidSoundFragment(percussion=True, sid=sid, smf=smf, df=df)
        self.assertEqual(set(s.waveforms.keys()), {'tri'})
        self.assertEqual(s.midi_pitches, (35,))
        self.assertEqual(s.total_duration, 9990435)


if __name__ == "__main__":
    unittest.main()
