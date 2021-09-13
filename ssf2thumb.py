#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import argparse
import sys
import numpy as np
import pandas as pd
from fileio import out_path
from sidlib import squeeze_diffs

THUMBNAIL_KEEP = ['gate1', 'test1', 'sync1', 'ring1', 'test3', 'pulse1', 'noise1', 'saw1', 'tri1', 'flt1', 'fltext', 'fltlo', 'fltband', 'flthi']
THUMBNAIL_IGNORE = ['atk1', 'dec1', 'sus1', 'rel1', 'vol', 'count']

parser = argparse.ArgumentParser(description='Convert ssfs into thumbnail ssfs')
parser.add_argument('ssffile', default='', help='SSF file to read')
parser.add_argument('--dfext', default='xz', help='default dataframe extension')
parser.add_argument('--maxframe', default=30, help='max frame count')
args = parser.parse_args()

ssf_df = pd.read_csv(args.ssffile, dtype=pd.Int64Dtype())
if not set(THUMBNAIL_KEEP).issubset(set(ssf_df.columns)):
    print('not an SSF file: %s' % args.ssffile)
    sys.exit(0)

ssf_df = ssf_df.drop(THUMBNAIL_IGNORE, axis=1).set_index('hashid')  # pylint: disable=no-member
ssf_df = ssf_df[ssf_df['frame'] <= args.maxframe]
ssf_df = ssf_df.fillna(0)

for col, bits in (
        ('freq1', 8),
        ('freq3', 8),
        ('pwduty1', 4),
        ('fltcoff', 3)):
    ssf_df[col] = np.right_shift(ssf_df[col], bits)
    ssf_df[col] = np.left_shift(ssf_df[col], bits)

thumbnails = {}
for _, ssf_df in ssf_df.groupby('hashid'):
    ssf_df = ssf_df.drop(['clock'], axis=1).reset_index(drop=True)
    thumbnail_ssf_df = squeeze_diffs(ssf_df, THUMBNAIL_KEEP).reset_index(drop=True)
    if thumbnail_ssf_df.empty:
        thumbnail_ssf_df = ssf_df[:1]
    thumbnail_hashid = hash(tuple([hash(tuple(r)) for r in thumbnail_ssf_df.itertuples()]))
    thumbnail_ssf_df = thumbnail_ssf_df.copy()
    thumbnail_ssf_df['hashid'] = thumbnail_hashid
    if thumbnail_hashid not in thumbnails:
        thumbnails[thumbnail_hashid] = thumbnail_ssf_df

thumbnail_df = pd.concat(list(thumbnails.values())).set_index('hashid')
thumbnail_df.to_csv(out_path(args.ssffile, '.'.join(('thumbnail_ssf', args.dfext))))
