#!/usr/bin/python3

# Copyright 2020-2022 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import argparse
import pandas as pd

from desidulate.fileio import read_csv, out_path
from desidulate.sidlib import resample_ssfs

parser = argparse.ArgumentParser(description='Downsample SSFs to PR frames')
parser.add_argument('ssffile', help='SSF file')
parser.add_argument('--max_clock', default=500000, type=int, help='include number of cycles')
parser.add_argument('--max_pr_speed', default=8, type=int, help='max pr_speed')


def main():
    args = parser.parse_args()
    df = read_csv(args.ssffile, dtype=pd.Int64Dtype())
    if not df.empty:
        df = df[(df.clock <= args.max_clock) & (df.pr_speed <= args.max_pr_speed)]
        df = resample_ssfs(df)
        df.to_csv(out_path(args.ssffile, 'resample_ssf.zst'), index=False)


if __name__ == '__main__':
    main()
