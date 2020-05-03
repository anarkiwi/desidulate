#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import argparse
from sidlib import get_reg_changes, get_reg_writes, VOICES
from sidwav import get_sid, make_wav_from_reg


parser = argparse.ArgumentParser(description='Convert vicesnd.sid log into a WAV file')
parser.add_argument('--logfile', default='vicesnd.sid', help='log file to read')
parser.add_argument('--logoutfile', default='', help='if defined, output only register changes to this file in vicesnd.sid format')
parser.add_argument('--wavfile', default='reg2wav.wav', help='WAV file to write')
parser.add_argument('--voicemask', default=','.join((str(v) for v in VOICES)), help='command separated list of SID voices to use')
parser.add_argument('--minclock', default=0, type=int, help='start rendering from this clock value')
parser.add_argument('--maxclock', default=0, type=int, help='if > 0, stop rendering at this clock value')
pal_parser = parser.add_mutually_exclusive_group(required=False)
pal_parser.add_argument('--pal', dest='pal', action='store_true', help='Use PAL clock')
pal_parser.add_argument('--ntsc', dest='pal', action='store_false', help='Use NTSC clock')
parser.set_defaults(pal=True)
args = parser.parse_args()
voicemask = set((int(v) for v in args.voicemask.split(',')))


sid = get_sid(pal=args.pal)
reg_writes = get_reg_changes(get_reg_writes(args.logfile), voicemask=voicemask, minclock=args.minclock, maxclock=args.maxclock)
make_wav_from_reg(sid, reg_writes, args.wavfile)
