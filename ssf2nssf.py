#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import argparse
import pandas as pd
from fileio import out_path
from ssf import normalize_ssf
from sidlib import get_sid
from sidwav import df2samples

parser = argparse.ArgumentParser(description='Normalize [single|multi]_patches.csv')
parser.add_argument('patchcsv', nargs='+', default=[], help='patch CSV(s) to read')
parser.add_argument('--outcsv', default='', help='patch CSV to write')
pal_parser = parser.add_mutually_exclusive_group(required=False)
pal_parser.add_argument('--pal', dest='pal', action='store_true', help='Use PAL clock')
pal_parser.add_argument('--ntsc', dest='pal', action='store_false', help='Use NTSC clock')
parser.set_defaults(pal=True)
args = parser.parse_args()

sid = get_sid(pal=args.pal)
new_ssf_dfs = {}
sample_hashes = {}
outcsv = args.outcsv

for patchcsv in args.patchcsv:
    ssf_dfs = pd.read_csv(patchcsv, dtype=pd.Int64Dtype())
    if not outcsv:
        outcsv = out_path(patchcsv, 'nssf.txt.xz')

    for _, ssf_df in ssf_dfs.groupby('hashid'):
        new_ssf = normalize_ssf(ssf_df, sid)
        hashid = new_ssf['hashid'].max()
        count = new_ssf['count'].max()
        if hashid in new_ssf_dfs:
            new_ssf_dfs[hashid]['count'] += count
        else:
            samples_hash = hash(tuple(df2samples(new_ssf, sid)))
            if samples_hash in sample_hashes:
                hashid = sample_hashes[samples_hash]
                new_ssf_dfs[hashid]['count'] += count
            else:
                new_ssf_dfs[hashid] = new_ssf
                sample_hashes[samples_hash] = hashid

ssf_dfs = pd.concat(sorted(new_ssf_dfs.values(), key=lambda x: x['count'].max(), reverse=True))
ssf_dfs.to_csv(outcsv, index=False)
