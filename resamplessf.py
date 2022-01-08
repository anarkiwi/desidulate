#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import argparse
import sys
import numpy as np
import pandas as pd
from fileio import out_path

parser = argparse.ArgumentParser(description='Downsample SSFs')
parser.add_argument('ssffile', help='SSF file')
parser.add_argument('--sample_cycles', default=7000, type=int, help='sample interval in CPU cycles')
parser.add_argument('--max_cycles', default=1e5, type=int, help='max number of CPU cycles')

args = parser.parse_args()
sample_count = int(args.max_cycles / args.sample_cycles) + 1
sid_cols = {
    'freq1', 'pwduty1', 'gate1', 'sync1', 'ring1', 'test1', 'tri1', 'saw1', 'pulse1', 'noise1', 'vol',
    'fltlo', 'fltband', 'flthi', 'flt1', 'fltext', 'fltres', 'fltcoff',
    'freq3', 'test3', 'atk1', 'dec1', 'sus1', 'rel1'}
sample_df = pd.DataFrame([{'clock': i * args.sample_cycles} for i in range(sample_count)], dtype=np.int64)

outfile = out_path(args.ssffile, 'resample_ssf.xz')
df = pd.read_csv(args.ssffile, dtype=pd.Int64Dtype())
if len(df) < 1:
    print('ignore empty %s' % args.ssffile)
    sys.exit(0)
df['clock'] = df['clock'].astype(np.int64)
meta_cols = set(df.columns) - sid_cols
df_raws = []
for hashid, ssf_df in df.groupby(['hashid']):  # pylint: disable=no-member
    resample_df = pd.merge_asof(sample_df, ssf_df).astype(pd.Int64Dtype())
    cols = set(resample_df.columns) - meta_cols
    df_raw = {col: resample_df[col].iat[-1] for col in meta_cols - {'clock', 'frame'}}
    for row in resample_df.itertuples():
        for col in cols:
            df_raw['%s_%u' % (col, row.clock)] = getattr(row, col)
    df_raws.append(df_raw)
df = pd.DataFrame(df_raws, dtype=pd.Int64Dtype()).set_index('hashid')
df.to_csv(outfile)
