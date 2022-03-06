#!/usr/bin/python3

import unittest
from desidulate.swilib import sw_rle_diff, dot0


class SWITestCase(unittest.TestCase):

    def test_sw_rle_diff(self):
        self.assertEqual(['8800'] + ['0000'] * 9, sw_rle_diff(['8800'] * 10, 1))
        self.assertEqual(['8800', '0302', '0000', '0000'], sw_rle_diff(['8800', '8802', '8804', '8806'], 1))
        self.assertEqual(['8810', '03FE', '0000', '0000'], sw_rle_diff(['8810', '880E', '880C', '880A'], 1))

    def test_dot0(self):
        self.assertEqual('....', dot0('0000'))
        self.assertEqual('99..', dot0('9900'))


if __name__ == '__main__':
    unittest.main()
