#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

# https://codebase64.org/doku.php?id=base:building_a_music_routine
# http://www.ucapps.de/howto_sid_wavetables_1.html

import argparse
import logging
from fileio import out_path
from sidlib import get_sid, reg2state, state2ssfs, timer_args

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')

parser = argparse.ArgumentParser(description='Convert vicesnd.sid log into SSF log files')
parser.add_argument('logfile', default='vicesnd.sid', help='log file to read')
parser.add_argument('--maxstates', default=int(10 * 1e6), help='maximum number of SID states to analyze')
timer_args(parser)
args = parser.parse_args()

sid = get_sid(args.pal)
df = reg2state(sid, args.logfile, nrows=int(args.maxstates))
ssf_log_df, ssf_df, control_ssf_df, skip_ssf_df = state2ssfs(sid, df)
ssf_log_df.to_csv(out_path(args.logfile, 'log.xz'))
ssf_df.to_csv(out_path(args.logfile, 'ssf.xz'))
control_ssf_df.to_csv(out_path(args.logfile, 'control_ssf.xz'))
skip_ssf_df.to_csv(out_path(args.logfile, 'skip_ssf.xz'))
