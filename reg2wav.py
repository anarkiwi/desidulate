#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import argparse
from fileio import wav_path
from sidlib import get_sid, reg2state
from sidwav import state2samples, write_wav

parser = argparse.ArgumentParser(description='Convert vicesnd.sid log into a WAV file')
parser.add_argument('logfile', default='vicesnd.sid', help='log file to read')
parser.add_argument('--wavfile', default='', help='WAV file to write')
pal_parser = parser.add_mutually_exclusive_group(required=False)
pal_parser.add_argument('--pal', dest='pal', action='store_true', help='Use PAL clock')
pal_parser.add_argument('--ntsc', dest='pal', action='store_false', help='Use NTSC clock')
parser.set_defaults(pal=True)
args = parser.parse_args()
wavfile = args.wavfile
if not wavfile:
    wavfile = wav_path(args.logfile)

sid = get_sid(pal=args.pal)
df = reg2state(sid, args.logfile)
raw_samples = state2samples(df, sid)
write_wav(wavfile, sid, raw_samples)
