#!/usr/bin/python3

import os
import unittest
import tempfile
import pandas as pd
from sidlib import get_reg_writes, get_sid


class SidLibTestCase(unittest.TestCase):
    """Test sidlib."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_df2wav(self):
        sid = get_sid(True)
        test_log = os.path.join(self.tmpdir.name, 'vicesnd.log')
        with open(test_log, 'w') as log:
            log.write('\n'.join((
                '0 24 2',
                '1 3 99',
                '10 24 2',
                '1 3 99',
                '13 24 1')) + '\n')
        df = get_reg_writes(sid, test_log)
        self.assertEqual(df['clock'].max(), 25)
        self.assertLess(len(df), len(open(test_log).readlines()))
        self.assertEqual(df[df['reg'] == 24]['val'].iloc[-1], 1)
        self.assertEqual(df[df['reg'] == 3]['val'].iloc[-1], 99)



if __name__ == "__main__":
    unittest.main()
