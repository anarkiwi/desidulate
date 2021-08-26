#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

# https://codebase64.org/doku.php?id=base:building_a_music_routine
# http://www.ucapps.de/howto_sid_wavetables_1.html

import argparse
import pandas as pd
from fileio import midi_path, out_path
from sidlib import get_sid
from sidmidi import SidMidiFile
from ssf import SidSoundFragment, SidSoundFragmentParser


parser = argparse.ArgumentParser(description='Convert ssf log into a MIDI file')
parser.add_argument('ssflogfile', default='', help='SSF log file to read')
parser.add_argument('--midifile', default='', help='MIDI file to write')
parser.add_argument('--bpm', default=125, type=int, help='MIDI BPM')
parser.add_argument('--percussion', dest='percussion', action='store_true')
parser.add_argument('--no-percussion', dest='percussion', action='store_false')
pal_parser = parser.add_mutually_exclusive_group(required=False)
pal_parser.add_argument('--pal', dest='pal', action='store_true', help='Use PAL clock')
pal_parser.add_argument('--ntsc', dest='pal', action='store_false', help='Use NTSC clock')
parser.set_defaults(pal=True, percussion=True)
args = parser.parse_args()

sid = get_sid(args.pal)
smf = SidMidiFile(sid, args.bpm)
parser = SidSoundFragmentParser(args.ssflogfile, args.percussion, sid)
parser.read_patches()

ssf_log_df = pd.read_csv(args.ssflogfile, dtype=pd.Int64Dtype())
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
