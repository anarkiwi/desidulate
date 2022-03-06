#!/usr/bin/python3

# Copyright 2020-2022 Josh Bailey (josh@vandervecken.com)

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
from desidulate.fileio import read_csv

SSF_GLOB = r'*.resample_ssf.*xz'
MAXES_RE = re.compile(r'.+\.(\d+)\.([^\.]+)\.xz$')
MAX_WORKERS = multiprocessing.cpu_count()


def scrape_resample_dir(resample_df_files):
    dfs = []
    hashids = defaultdict(set)
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


def scrape_paths(orders_filter, fromssfs):
    current = pathlib.Path(r'./')
    resample_orders_files = defaultdict(list)
    globs = [SSF_GLOB]
    if orders_filter:
        orders_filter = set(orders_filter)
        globs = [r'*.resample_ssf.0-%s.*' % i for i in orders_filter] + [r'*.resample_ssf.%s.*' % i for i in orders_filter]
    fromssfs_files = None
    if fromssfs:
        if fromssfs.endswith('.gz'):
            opener = gzip.open
        else:
            opener = open
        with opener(fromssfs) as f:
            fromssfs_files = f.read().decode('utf8').splitlines()  # pytype: disable=attribute-error
    for glob in globs:
        if fromssfs_files:
            globber = fromssfs_files
        else:
            globber = current.rglob(glob)
        for resample_df_file in globber:
            resample_df_file = os.path.normpath(str(resample_df_file))
            match = MAXES_RE.match(resample_df_file)
            pr_speed, order = int(match.group(1)), match.group(2)
            if order.startswith('0-'):
                order = order[2:]
            if orders_filter and order not in orders_filter:
                continue
            resample_orders_files[(pr_speed, order)].append(resample_df_file)

    return resample_orders_files


def scrape_resample_dfs(resample_dir_dfs):
    with concurrent.futures.ProcessPoolExecutor(max_workers=min(MAX_WORKERS, len(resample_dir_dfs))) as executor:
        result_futures = map(lambda x: executor.submit(scrape_resample_dir, x), resample_dir_dfs.values())
        results = [future.result() for future in concurrent.futures.as_completed(result_futures)]
    results = [result for result in results if result[0] is not None]
    hashids = defaultdict(set)
    resample_df = pd.concat([result[1] for result in results]).drop_duplicates()
    for result in results:
        for hashid, source in result[0].items():
            hashids[hashid].update(source)
    hashids_df = pd.DataFrame(hashids.items(), columns=['hashid', 'sources'])
    return (resample_df, hashids_df)


def write_df(df, name):
    df.to_csv(name, index=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--orders', nargs='+', default=None)
    parser.add_argument('--fromssfs', type=str, default=None)
    args = parser.parse_args()
    resample_orders_files = scrape_paths(args.orders, args.fromssfs)
    for order_pr_speed, resample_df_files in sorted(resample_orders_files.items()):
        order, pr_speed = order_pr_speed
        print(order, pr_speed)
        resample_dir_dfs = defaultdict(list)
        for resample_df_file in resample_df_files:
            resample_dir_dfs[os.path.dirname(resample_df_file)].append(resample_df_file)
        resample_df, hashids_df = scrape_resample_dfs(resample_dir_dfs)
        write_df(resample_df, 'resample_ssf.%u.%s.xz' % (order, pr_speed))
        write_df(hashids_df, 'resample_ssf.hashid.%u.%s.xz' % (order, pr_speed))


if __name__ == '__main__':
    main()
