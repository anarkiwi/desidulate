#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import argparse
import logging
from fileio import wav_path
from sidlib import get_sid, reg2state, timer_args
from sidwav import state2samples, write_wav

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

parser = argparse.ArgumentParser(description='Convert vicesnd.sid log into a WAV file')
parser.add_argument('logfile', default='vicesnd.sid', help='log file to read')
parser.add_argument('--maxstates', default=int(10 * 1e6), help='maximum number of SID states to analyze')
parser.add_argument('--wavfile', default='', help='WAV file to write')
timer_args(parser)
args = parser.parse_args()
wavfile = args.wavfile
if not wavfile:
    wavfile = wav_path(args.logfile)

sid = get_sid(pal=args.pal)
df = reg2state(sid, args.logfile, nrows=int(args.maxstates))
raw_samples = state2samples(df, sid)
write_wav(wavfile, sid, raw_samples)
