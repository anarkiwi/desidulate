#!/usr/bin/python3

# Copyright 2021 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.


import multiprocessing
import os
import pathlib
import concurrent.futures
from collections import defaultdict
import pandas as pd

MAX_WORKERS = multiprocessing.cpu_count()


def scrape_resample_dir(resample_dir, resample_dir_dfs):
    dfs = []
    cols = None
    for resample_df_file in resample_dir_dfs[resample_dir]:
        resample_df = pd.read_csv(resample_df_file, dtype=pd.Int64Dtype())
        if len(resample_df) < 1:
            continue
        if cols is None:
            cols = ['source'] + list(resample_df.columns)
        resample_df.loc[:, ['source']] = resample_df_file[:resample_df_file.find('.')]  # pylint: disable=no-member
        dfs.append(resample_df)
    return pd.concat(dfs)[cols]


def scrape_resample_dfs():
    current = pathlib.Path(r'./')
    resample_dir_dfs = defaultdict(set)
    for resample_df_file in current.rglob(r'*.resample_ssf.xz'):
        resample_dir_dfs[os.path.dirname(resample_df_file)].add(str(resample_df_file))
    resample_dirs = resample_dir_dfs.keys()

    with concurrent.futures.ProcessPoolExecutor(max_workers=min(MAX_WORKERS, len(resample_dirs))) as executor:
        result_futures = map(lambda x: executor.submit(scrape_resample_dir, x, resample_dir_dfs), resample_dirs)
        results = [future.result() for future in concurrent.futures.as_completed(result_futures)]

    return pd.concat(results)


df = scrape_resample_dfs()
df.to_csv('resample_ssf.xz', index=False)
