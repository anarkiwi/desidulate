#!/usr/bin/python3

import os
import tempfile
import unittest
import pandas as pd
from sidlib import get_sid, get_reg_writes, get_gate_events
from sidmidi import SidMidiFile
from ssf import SidSoundFragment, SidSoundFragmentParser


class SSFTestCase(unittest.TestCase):
    """Test SSF."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmpdir.cleanup()

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

    def test_ssf_parser(self):
        sid = get_sid(True)
        smf = SidMidiFile(sid, 125)
        test_log = os.path.join(self.tmpdir.name, 'vicesnd.log')
        with open(test_log, 'w') as log:
            log.write('\n'.join((
                '1 24 15',
                '1 7 255',
                '1 8 128',
                '1 13 255',
                '100 11 129',
                '100000 11 0')) + '\n')
        reg_writes = get_reg_writes(sid, test_log)
        parser = SidSoundFragmentParser(logfile=None, percussion=True, sid=sid, smf=smf)
        for voicenum, events in get_gate_events(reg_writes):
            ssf, first_clock = parser.parse(voicenum, events)
            self.assertNotEqual(ssf, None)
            if ssf:
                self.assertEqual(first_clock, 103)
                self.assertEqual(ssf.midi_pitches, (95,))
                self.assertEqual(ssf.total_duration, 98525)
                self.assertEqual(voicenum, 2)


if __name__ == "__main__":
    unittest.main()
