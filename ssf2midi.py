#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

# https://codebase64.org/doku.php?id=base:building_a_music_routine
# http://www.ucapps.de/howto_sid_wavetables_1.html

import argparse
import sys
import pandas as pd
from fileio import midi_path, out_path
from sidlib import get_sid, timer_args
from sidmidi import SidMidiFile, DEFAULT_BPM, midi_args
from ssf import SidSoundFragment, SidSoundFragmentParser

ALL_VOICES = frozenset([1, 2, 3])

parser = argparse.ArgumentParser(description='Convert ssf log into a MIDI file')
parser.add_argument('ssflogfile', default='', help='SSF log file to read')
parser.add_argument('--midifile', default='', help='MIDI file to write')
parser.add_argument('--minclock', default=0, type=int, help='Min clock value')
parser.add_argument('--maxclock', default=0, type=int, help='Max clock value')
parser.add_argument('--voicemask', default=','.join([str(v) for v in ALL_VOICES]), type=str, help='Voice mask')
timer_args(parser)
midi_args(parser)
args = parser.parse_args()
voicemask = frozenset([int(v) for v in args.voicemask.split(',')])

sid = get_sid(args.pal)
smf = SidMidiFile(sid, args.bpm)
parser = SidSoundFragmentParser(args.ssflogfile, args.percussion, sid)
parser.read_patches()

ssf_log_df = pd.read_csv(args.ssflogfile, dtype=pd.Int64Dtype())
cols = set(ssf_log_df.columns)
if cols != {'clock', 'hashid', 'voice'}:
    print('not an SSF log file (cols %s)' % cols)
    sys.exit(1)

if args.maxclock:
    ssf_log_df = ssf_log_df[ssf_log_df['clock'] <= args.maxclock]  # pylint: disable=unsubscriptable-object
if args.minclock:
    ssf_log_df = ssf_log_df[ssf_log_df['clock'] >= args.minclock]  # pylint: disable=unsubscriptable-object
    min_clock = ssf_log_df['clock'].min()
    ssf_log_df['clock'] -= min_clock

if voicemask != ALL_VOICES:
    ssf_log_df = ssf_log_df[ssf_log_df['voice'].isin(voicemask)]

ssf_cache = {}
ssf_instruments = []
for row in ssf_log_df.itertuples():
    ssf = ssf_cache.get(row.hashid, None)
    if ssf is None:
        ssf_df = parser.ssf_dfs[row.hashid]
        ssf = SidSoundFragment(args.percussion, sid, ssf_df, smf)
        ssf_cache[row.hashid] = ssf
        ssf_instruments.append(ssf.instrument({'hashid': row.hashid}))
    ssf.smf_transcribe(smf, row.clock, row.voice)

ssf_instrument_file = out_path(args.ssflogfile, 'inst.txt.xz')
ssf_instrument_df = pd.DataFrame(ssf_instruments)
ssf_instrument_df.to_csv(ssf_instrument_file, index=False)

midifile = args.midifile
if not midifile:
    midifile = midi_path(args.ssflogfile)
smf.write(midifile)
