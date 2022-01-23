#!/usr/bin/python3

# Copyright 2021 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import argparse
import gzip
import re
import multiprocessing
import os
import pathlib
import concurrent.futures
from collections import defaultdict
import pandas as pd
from fileio import read_csv

SSF_GLOB = r'*.resample_ssf.*xz'
MAXES_RE = re.compile(r'.+\.([^\.]+)\.xz$')
MAX_WORKERS = multiprocessing.cpu_count()


def scrape_resample_dir(dir_max, resample_dir, resample_dir_dfs):
    dfs = []
    hashids = defaultdict(set)
    resample_df_files = [
        resample_df_file for df_max, resample_df_file in resample_dir_dfs[resample_dir]
        if df_max == dir_max]
    for resample_df_file in resample_df_files:
        resample_df = read_csv(resample_df_file, dtype=pd.Int64Dtype())
        if len(resample_df) < 1:
            continue
        resample_df_file_base = resample_df_file[:resample_df_file.find('.')]
        for hashid in resample_df['hashid'].unique():
            hashids[int(hashid)].add(resample_df_file_base)
        dfs.append(resample_df)
    if dfs:
        df = pd.concat(dfs)
        drop_cols = set()
        for col in df.columns:
            if col.startswith('hashid'):
                df[col] = df[col].astype(pd.Int64Dtype())
                continue
            if not col[-1].isdigit():
                if col in ('count,'):
                    drop_cols.add(col)
                else:
                    df[col] = df[col].astype(pd.Int32Dtype())
                continue
            if col.startswith(('freq', 'fltcoff', 'pwduty')):
                df[col] = df[col].astype(pd.UInt16Dtype())
                continue
            if col.startswith(('vol',)):
                drop_cols.add(col)
                continue
            df[col] = df[col].astype(pd.UInt8Dtype())
        if drop_cols:
            df = df.drop(drop_cols, axis=1)
        df = df.drop_duplicates()
        return (hashids, df)
    return (None, None)


def scrape_paths(maxes_filter, fromssfs):
    current = pathlib.Path(r'./')
    resample_dir_dfs = defaultdict(list)
    resample_maxes_files = defaultdict(list)
    globs = [SSF_GLOB]
    if maxes_filter:
        maxes_filter = set(maxes_filter)
        globs = [r'*.resample_ssf.%s.*' % i for i in maxes_filter]
    fromssfs_files = None
    if fromssfs:
        if fromssfs.endswith('.gz'):
            opener = gzip.open
        else:
            opener = open
        with opener(fromssfs) as f:
            fromssfs_files = f.read().decode('utf8').splitlines()  # pylint: disable=attribute-error
    for glob in globs:
        if fromssfs_files:
            globber = fromssfs_files
        else:
            globber = current.rglob(glob)
        for resample_df_file in globber:
            resample_df_file = str(resample_df_file)
            match = MAXES_RE.match(resample_df_file).group(1)
            if maxes_filter and match not in maxes_filter:
                continue
            resample_maxes_files[match].append(resample_df_file)

        for match, resample_df_files in resample_maxes_files.items():
            for resample_df_file in resample_df_files:
                resample_dir_dfs[os.path.dirname(resample_df_file)].append((match, resample_df_file))

    resample_dirs = list(resample_dir_dfs.keys())
    maxes = set(resample_maxes_files.keys())
    return (maxes, resample_dirs, resample_dir_dfs)


def scrape_resample_dfs(dir_max, resample_dirs, resample_dir_dfs):
    with concurrent.futures.ProcessPoolExecutor(max_workers=min(MAX_WORKERS, len(resample_dirs))) as executor:
        result_futures = map(lambda x: executor.submit(scrape_resample_dir, dir_max, x, resample_dir_dfs), resample_dirs)
        results = [future.result() for future in concurrent.futures.as_completed(result_futures)]
    results = [result for result in results if result[0] is not None]
    hashids = defaultdict(set)
    resample_df = pd.concat([result[1] for result in results]).drop_duplicates()
    for result in results:
        for hashid, source in result[0].items():
            hashids[hashid].update(source)
    hashids_df = pd.DataFrame(hashids.items(), columns=['hashid', 'sources'])
    return (resample_df, hashids_df)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--maxes', nargs='+', default=None)
    parser.add_argument('--fromssfs', type=str, default=None)
    args = parser.parse_args()
    maxes, resample_dirs, resample_dir_dfs = scrape_paths(args.maxes, args.fromssfs)
    for dir_max in sorted(maxes):
        print(dir_max)
        resample_df, hashids_df = scrape_resample_dfs(dir_max, resample_dirs, resample_dir_dfs)
        resample_df.to_csv('resample_ssf.%s.xz' % dir_max, index=False)
        hashids_df.to_csv('resample_ssf.hashid.%s.xz' % dir_max, index=False)


if __name__ == '__main__':
    main()
