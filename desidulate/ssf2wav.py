#!/usr/bin/python3

# Copyright 2020-2022 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import argparse
import os
import sys
import numpy as np
import pandas as pd
from desidulate.fileio import wav_path, out_path, read_csv
from desidulate.sidlib import get_sid, resampledf_to_pr
from desidulate.sidwav import df2wav
from desidulate.sidmidi import SidMidiFile, midi_args
from desidulate.ssf import add_freq_notes_df, SidSoundFragment


def main():
    parser = argparse.ArgumentParser(description='Convert .ssf into a WAV file')
    parser.add_argument('ssffile', default='', help='ssf to read')
    parser.add_argument('--hashid', default=0, help='hashid to reproduce, or 0 if all')
    parser.add_argument('--wavfile', default='', help='WAV file to write')
    parser.add_argument('--maxclock', default=0, type=int, help='max clock value to render, 0 for no limit')
    play_parser = parser.add_mutually_exclusive_group(required=False)
    play_parser.add_argument('--play', dest='play', action='store_true', help='play the wavfile')
    play_parser.add_argument('--no-play', dest='play', action='store_false', help='do not play the wavfile')
    skiptest_parser = parser.add_mutually_exclusive_group(required=False)
    skiptest_parser.add_argument('--skiptest', dest='skiptest', action='store_true', help='skip initial SSF period where test1 is set')
    skiptest_parser.add_argument('--no-skiptest', dest='skiptest', action='store_false', help='do not skip initial SSF period where test1 is set')
    single_waveform_parser = parser.add_mutually_exclusive_group(required=False)
    single_waveform_parser.add_argument('--skip-single-waveform', dest='skip_single_waveform', action='store_true', help='skip SSFs that use only a single waveform')
    single_waveform_parser.add_argument('--no-skip-single-waveform', dest='skip_single_waveform', action='store_false', help='do not skip SSFs that use only a single waveform')
    ssf_parser = parser.add_mutually_exclusive_group(required=False)
    ssf_parser.add_argument('--skip-ssf-parser', dest='skip_ssf_parser', action='store_true', help='skip parsing of SSF')
    ssf_parser.add_argument('--no-skip-ssf-parser', dest='skip_ssf_parser', action='store_false', help='do not skip parsing of SSF')
    pr_resample = parser.add_mutually_exclusive_group(required=False)
    pr_resample.add_argument('--pr_resample', dest='pr_resample', default=True, action='store_true', help='skip parsing of SSF')
    pr_resample.add_argument('--no-pr_resample', dest='pr_resample', action='store_false', help='do not skip parsing of SSF')
    midi_args(parser)
    args = parser.parse_args()

    df = read_csv(args.ssffile, dtype=pd.Int64Dtype())

    if not len(df):
        print('empty SSF file')
        sys.exit(0)

    if args.maxclock:
        df = df[df['clock'] < args.maxclock]

    sid = get_sid(pal=args.pal)
    smf = None

    if not args.skip_ssf_parser:
        df = add_freq_notes_df(sid, df)
        smf = SidMidiFile(sid, args.bpm)
    hashid = np.int64(args.hashid)


    def render_wav(ssf_df, wavfile, verbose):
        ssf_df = ssf_df.set_index('clock')
        if args.pr_resample:
            if pd.isna(ssf_df['pr_speed'].iat[0]):
                return
            ssf_df = resampledf_to_pr(ssf_df)
        else:
            ssf_df = ssf_df.fillna(method='ffill')
        df2wav(ssf_df, sid, wavfile, skiptest=args.skiptest)
        if verbose:
            print(ssf_df.to_string())
        if args.play:
            os.system(' '.join(['aplay', wavfile]))
        if args.skip_ssf_parser:
            return
        ssf = SidSoundFragment(args.percussion, sid, ssf_df, smf)
        if verbose:
            print(ssf.instrument({}))

    if hashid:
        wavfile = args.wavfile
        if not wavfile:
            wavfile = wav_path(args.ssffile)

        ssf_df = df[df['hashid'] == hashid].copy()

        if len(ssf_df):
            render_wav(ssf_df, wavfile, True)
        else:
            print('SSF %d not found' % hashid)
    else:
        def single_waveform(ssf_df):
            waveforms = {'pulse1', 'saw1', 'tri1', 'noise1'}

            def single_waveform_filter(w1, w2, w3, w4):
                return ssf_df[w1].max() == 1 and ssf_df[w2].max() != 1 and ssf_df[w3].max() != 1 and ssf_df[w4].max() != 1

            for waveform in waveforms:
                other_waveforms = list(waveforms - {waveform})
                if single_waveform_filter(waveform, other_waveforms[0], other_waveforms[1], other_waveforms[2]):
                    return True
            return False

        for hashid, ssf_df in df.groupby('hashid'):
            if args.skip_single_waveform and single_waveform(ssf_df):
                continue
            wavfile = out_path(args.ssffile, '%u.wav' % hashid)
            render_wav(ssf_df.copy(), wavfile, False)


if __name__ == '__main__':
    main()
