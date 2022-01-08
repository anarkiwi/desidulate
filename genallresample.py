#!/usr/bin/python3

# Copyright 2021 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import re
import multiprocessing
import os
import pathlib
import concurrent.futures
from collections import defaultdict
import pandas as pd

SSF_GLOB = r'*.resample_ssf.*xz'
MAXES_RE = re.compile(r'.+\.([^\.]+)\.xz$')
MAX_WORKERS = multiprocessing.cpu_count()


def scrape_resample_dir(dir_max, resample_dir, resample_dir_dfs):
    dfs = []
    hashids = defaultdict(set)
    for df_max, resample_df_file in resample_dir_dfs[resample_dir]:
        if df_max != dir_max:
            continue
        resample_df = pd.read_csv(resample_df_file, dtype=pd.Int64Dtype()).drop(['count'], axis=1)
        if len(resample_df) < 1:
            continue
        for hashid in resample_df['hashid'].unique():
            hashids[int(hashid)].add(resample_df_file[:resample_df_file.find('.')])
        dfs.append(resample_df)
    if dfs:
        return (hashids, pd.concat(dfs).drop_duplicates())
    return (None, None)


def scrape_paths():
    current = pathlib.Path(r'./')
    resample_dir_dfs = defaultdict(set)
    maxes = set()
    for resample_df_path in current.rglob(SSF_GLOB):
        resample_df_file = str(resample_df_path)
        maxes_match = MAXES_RE.match(resample_df_file)
        maxes.add(maxes_match.group(1))
        resample_dir_dfs[os.path.dirname(resample_df_file)].add((maxes_match.group(1), str(resample_df_file)))
    resample_dirs = resample_dir_dfs.keys()
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
    resample_df = resample_df.merge(hashids_df, on='hashid')
    return resample_df


maxes, resample_dirs, resample_dir_dfs = scrape_paths()
for dir_max in sorted(maxes):
    resample_df = scrape_resample_dfs(dir_max, resample_dirs, resample_dir_dfs)
    resample_df.to_csv('resample_ssf.%s.xz' % dir_max, index=False)
