#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import csv
import argparse
from collections import defaultdict

import numpy as np
import scipy.io.wavfile
from pyresidfp import Voice, ControlBits, ModeVolBits

from fileio import file_reader, wav_path
from sidlib import get_sid


parser = argparse.ArgumentParser(description='Convert [single|multi]_patches.csv into a WAV file')
parser.add_argument('patchcsv', default='', help='patch CSV to read')
parser.add_argument('hashid', default=0, help='hashid to reproduce')
parser.add_argument('--wavfile', default='', help='WAV file to write')
pal_parser = parser.add_mutually_exclusive_group(required=False)
pal_parser.add_argument('--pal', dest='pal', action='store_true', help='Use PAL clock')
pal_parser.add_argument('--ntsc', dest='pal', action='store_false', help='Use NTSC clock')
parser.set_defaults(pal=True)
args = parser.parse_args()

sid = get_sid(pal=args.pal)
wavfile = args.wavfile
if not wavfile:
    wavfile = wav_path(args.patchcsv)


def control_reg(voicenum, voicestate):
    return ControlBits(
        (ControlBits.GATE.value * voicestate['gate%u' % voicenum]) |
        (ControlBits.SYNC.value * voicestate['sync%u' % voicenum]) |
        (ControlBits.RING_MOD.value * voicestate['ring%u' % voicenum]) |
        (ControlBits.TEST.value * voicestate['test%u' % voicenum]) |
        (ControlBits.TRIANGLE.value * voicestate['tri%u' % voicenum]) |
        (ControlBits.SAWTOOTH.value * voicestate['saw%u' % voicenum]) |
        (ControlBits.PULSE.value * voicestate['pulse%u' % voicenum]) |
        (ControlBits.NOISE.value * voicestate['noise%u' % voicenum]))


def filter_coff_reg(voicestate):
    return voicestate['flt_coff'] & (2 ** 11 - 1)


def filtermodevol_reg(voicestate):
    return ModeVolBits(
        (ModeVolBits.BP.value * voicestate['flt_band']) |
        (ModeVolBits.HP.value * voicestate['flt_high']) |
        (ModeVolBits.LP.value * voicestate['flt_low'])).value + voicestate['vol']


def nib2byte(hi, lo):
    return (hi << 4) + lo


def filterres_reg(voicenum, voicestate):
    return nib2byte(voicestate['flt_res'], voicestate['flt%u' % voicenum])


def attack_decay(voicenum, voicestate):
    return nib2byte(voicestate['atk%u' % voicenum], voicestate['dec%u' % voicenum])


def sustain_release(voicenum, voicestate):
    return nib2byte(voicestate['sus%u' % voicenum], voicestate['rel%u' % voicenum])


def freq(voicenum, voicestate):
    return voicestate['freq%u' % voicenum]


def pw_duty(voicenum, voicestate):
    return voicestate['pw_duty%u' % voicenum] & (2 ** 12 - 1)


raw_samples = []
lastclock = 0
sidstate = defaultdict(int)
arghashid = int(args.hashid)

with file_reader(args.patchcsv) as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        row = {k: int(v) for k, v in row.items() if v != ''}
        hashid = row['hashid']
        if hashid != arghashid:
            continue
        clock = row['clock']
        ts_offset = clock - lastclock
        raw_samples.extend(sid.add_samples(ts_offset))

        for f in set(row.keys()) - {'hashid', 'count', 'clock'}:
            sidstate[f] += row[f]

        sid.resid.filter_cutoff(filter_coff_reg(sidstate))
        sid.resid.Filter_Mode_Vol = filtermodevol_reg(sidstate)

        for voice in (Voice.ONE, Voice.THREE):
            voicenum = voice.value + 1
            sid.resid.Filter_Res_Filt = filterres_reg(voicenum, sidstate)
            sid.resid.oscillator(voice, freq(voicenum, sidstate))
            sid.resid.pulse_width(voice, pw_duty(voicenum, sidstate))
            sid.resid.attack_decay(voice, attack_decay(voicenum, sidstate))
            sid.resid.sustain_release(voice, sustain_release(voicenum, sidstate))
            sid.resid.control(voice, control_reg(voicenum, sidstate))

        lastclock = clock


scipy.io.wavfile.write(
    wavfile, int(sid.resid.sampling_frequency), np.array(raw_samples, dtype=np.float32) / 2**15)
