#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

# https://codebase64.org/doku.php?id=base:building_a_music_routine
# http://www.ucapps.de/howto_sid_wavetables_1.html

import argparse
from fileio import midi_path
from sidlib import get_gate_events, get_reg_writes, get_sid, VOICES
from sidmidi import SidMidiFile
from ssf import SidSoundFragmentParser


parser = argparse.ArgumentParser(description='Convert vicesnd.sid log into a MIDI file')
parser.add_argument('logfile', default='vicesnd.sid', help='log file to read')
parser.add_argument('--midifile', default='', help='MIDI file to write')
parser.add_argument('--voicemask', default=','.join((str(v) for v in VOICES)), help='command separated list of SID voices to use')
parser.add_argument('--minclock', default=0, type=int, help='start rendering from this clock value')
parser.add_argument('--maxclock', default=0, type=int, help='if > 0, stop rendering at this clock value')
parser.add_argument('--bpm', default=125, type=int, help='MIDI BPM')
parser.add_argument('--percussion', dest='percussion', action='store_true')
parser.add_argument('--no-percussion', dest='percussion', action='store_false')
pal_parser = parser.add_mutually_exclusive_group(required=False)
pal_parser.add_argument('--pal', dest='pal', action='store_true', help='Use PAL clock')
pal_parser.add_argument('--ntsc', dest='pal', action='store_false', help='Use NTSC clock')
parser.set_defaults(pal=True, percussion=True)
args = parser.parse_args()

voicemask = frozenset((int(v) for v in args.voicemask.split(',')))
sid = get_sid(args.pal)
smf = SidMidiFile(sid, args.bpm)
reg_writes = get_reg_writes(
    sid,
    args.logfile,
    minclock=args.minclock,
    maxclock=args.maxclock,
    voicemask=voicemask)

parser = SidSoundFragmentParser(args.logfile, args.percussion, sid, smf)
for voicenum, events in get_gate_events(reg_writes):
    ssf, first_clock = parser.parse(voicenum, events)
    if ssf:
        ssf.smf_transcribe(smf, first_clock, voicenum)

midifile = args.midifile
if not midifile:
    midifile = midi_path(args.logfile)

smf.write(midifile)
parser.dump_patches()
