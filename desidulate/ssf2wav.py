#!/usr/bin/python3

# Copyright 2020-2022 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import argparse
import logging
import os
import sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd
from desidulate.fileio import wav_path, out_path, read_csv
from desidulate.sidwav import df2wav
from desidulate.sidwrap import get_sid
from desidulate.sidmidi import SidMidiFile, midi_args
from desidulate.ssf import add_freq_notes_df, SidSoundFragment


class RenderWav:

    def __init__(self, smf, args):
        self.smf = smf
        self.args = args

    def render(self, ssf_df, wavfile):
        ssf_df = ssf_df.set_index('clock')
        ssf_df = ssf_df.fillna(method='ffill')
        sid = get_sid(self.args.pal, self.args.cia)
        df2wav(ssf_df, sid, wavfile, skiptest=self.args.skiptest)
        logging.info(ssf_df.to_string())
        if self.args.play:
            os.system(' '.join(['play', wavfile]))
        if self.args.skip_ssf_parser:
            return
        ssf = SidSoundFragment(self.args.percussion, sid, ssf_df, self.smf)
        logging.info(ssf.instrument({}))


def render_wav(ssf_df, wavfile):
    rw.render(ssf_df, wavfile)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    parser = argparse.ArgumentParser(description='Convert .ssf into a WAV file')
    parser.add_argument('ssffile', default='', help='ssf to read')
    parser.add_argument('--hashid', default=0, help='hashid to reproduce, or 0 if all')
    parser.add_argument('--maxclock', default=0, type=int, help='max clock value to render, 0 for no limit')
    parser.add_argument('--workers', default=4, type=int, help='workers to use when generating many wavs')
    play_parser = parser.add_mutually_exclusive_group(required=False)
    play_parser.add_argument('--play', dest='play', action='store_true', help='play the wavfile')
    play_parser.add_argument('--no-play', dest='play', action='store_false', help='do not play the wavfile')
    skiptest_parser = parser.add_mutually_exclusive_group(required=False)
    skiptest_parser.add_argument('--skiptest', dest='skiptest', action='store_true', help='skip initial SSF period where test1 is set')
    skiptest_parser.add_argument('--no-skiptest', dest='skiptest', action='store_false', help='do not skip initial SSF period where test1 is set')
    ssf_parser = parser.add_mutually_exclusive_group(required=False)
    ssf_parser.add_argument('--skip-ssf-parser', dest='skip_ssf_parser', action='store_true', help='skip parsing of SSF')
    ssf_parser.add_argument('--no-skip-ssf-parser', dest='skip_ssf_parser', action='store_false', help='do not skip parsing of SSF')
    midi_args(parser)
    args = parser.parse_args()

    df = read_csv(args.ssffile, dtype=pd.Int64Dtype())
    if df.empty:
        print('empty SSF file')
        sys.exit(0)

    if args.maxclock:
        df = df[df['clock'] <= args.maxclock]

    sid = get_sid(args.pal, args.cia)
    smf = None

    if not args.skip_ssf_parser:
        df = add_freq_notes_df(sid, df)
        smf = SidMidiFile(sid, args.bpm)

    if args.hashid:
        df = df[df['hashid'] == np.int64(args.hashid)].copy()

    # TODO: handle vol/samples.
    df = df[df['vol'].isna()]
    df['vol'] = 15

    global rw
    rw = RenderWav(smf, args)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for hashid, ssf_df in df.groupby('hashid'):
            wavfile = out_path(args.ssffile, '%u.wav' % hashid)
            pool.submit(render_wav, ssf_df.copy(), wavfile)


if __name__ == '__main__':
    main()
