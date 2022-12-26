#!/usr/bin/python3

# Copyright 2020-2022 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import argparse
import logging
from collections import defaultdict
import pandas as pd

from desidulate.fileio import read_csv, out_path
from desidulate.sidlib import CANON_REG_ORDER, resampledf_to_pr, hash_vdf, df_waveform_order

parser = argparse.ArgumentParser(description='Downsample SSFs to PR frames')
parser.add_argument('ssffile', help='SSF file')
parser.add_argument('--max_clock', default=500000, type=int, help='include number of cycles')
parser.add_argument('--max_pr_speed', default=8, type=int, help='max pr_speed')


def resample(df, ssffile):
    sid_cols = set(CANON_REG_ORDER) - {'fltext'}
    resample_dfs = defaultdict(list)

    for hashid, ssf_df in df.groupby('hashid'):  # pylint: disable=no-member
        resample_waveform = df_waveform_order(ssf_df)
        resample_df = ssf_df.reset_index(drop=True).set_index('clock')
        resample_df = resampledf_to_pr(resample_df)
        resample_df = hash_vdf(resample_df, sid_cols, hashid='resample_hashid_noclock', ssf='hashid')
        resample_waveform_order = df_waveform_order(resample_df)
        resample_dfs['-'.join(resample_waveform_order)].append(resample_df)
        if resample_waveform != resample_waveform_order:
            print(resample_waveform, resample_waveform_order)
            print(ssf_df)
            print(resample_df)
    for waveform, dfs in resample_dfs.items():
        resample_df = pd.concat(dfs)
        resample_path = out_path(ssffile, '%s.resample_ssf.zst' % waveform)
        resample_df.to_csv(resample_path, index=False)


def main():
    args = parser.parse_args()
    df = read_csv(args.ssffile, dtype=pd.Int64Dtype())
    if not df.empty:
        df = df[(df.clock <= args.max_clock) & (df.pr_speed <= args.max_pr_speed)].drop(['rate', 'count', 'hashid_noclock'], axis=1)
        resample(df, args.ssffile)


if __name__ == '__main__':
    main()
