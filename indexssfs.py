#!/usr/bin/python3

# Copyright 2021 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.


import os
import concurrent.futures
import multiprocessing
from collections import defaultdict
from pathlib import Path
import pandas as pd


MAX_WORKERS = multiprocessing.cpu_count()
SSF_SUFFIX = 'thumbnail_ssf'
SSF_ROOT = r'.'
SSF_EXT = '.%s.xz' % SSF_SUFFIX
COL_MAXES = ('test1', 'sync1', 'ring1', 'pulse1', 'saw1', 'tri1', 'pulse1', 'noise1', 'flt1', 'fltlo', 'fltband', 'flthi', 'fltext')
COL_UNIQUE = ('freq1', 'freq3', 'pwduty1', 'fltcoff')


def index_dir(dirname):
    dir_index = defaultdict(set)
    dir_metadata = {}
    dir_paths = [os.path.join(dirname, filename) for filename in os.listdir(dirname)]
    dir_paths = [file_path for file_path in dir_paths if os.path.isfile(file_path) and file_path.endswith(SSF_EXT)]
    for path in dir_paths:
        try:
            short_path = path[len(SSF_ROOT)-1:]
            df = pd.read_csv(path)
            for hashid, ssf_df in df.groupby('hashid', sort=False):
                dir_index[hashid].add(short_path)
                if hashid not in dir_metadata:
                    metadata = {col: len(ssf_df[ssf_df[col] == 1][col]) for col in COL_MAXES}
                    metadata.update({'n%s' % col: ssf_df[ssf_df[col] > 0][col].nunique() for col in COL_UNIQUE})
                    for col in COL_UNIQUE:
                        v = ssf_df[ssf_df[col] > 0][col]  # pylint: disable=unsubscriptable-object
                        if len(v):
                            metadata.update({'f%s' % col: v.iat[0]})
                    metadata.update({'len': len(ssf_df), 'frames': ssf_df['frame'].max()})
                    dir_metadata[hashid] = metadata
        except ValueError:
            continue
    return (dir_index, dir_metadata)


global_dir_index = defaultdict(set)
global_dir_metadata = {}
with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
    result_futures = map(lambda x: executor.submit(index_dir, x), Path(SSF_ROOT).glob('**/'))
    for future in concurrent.futures.as_completed(result_futures):
        dir_index, dir_metadata = future.result()
        for hashid, paths in dir_index.items():
            global_dir_index[hashid].update(paths)
        for hashid, metadata in dir_metadata.items():
            global_dir_metadata[hashid] = metadata

for hashid, paths in global_dir_index.items():
    global_dir_metadata[hashid].update({'hashid': hashid, 'ssffiles': paths})

df = pd.DataFrame(global_dir_metadata.values())
df['ssffileslen'] = df.ssffiles.transform(len)
df.sort_values('ssffileslen', ascending=False, inplace=True)
df.to_csv('%s_index.xz' % SSF_SUFFIX, index=False)

# to re-read
# df = pd.read_csv('thumbnail_ssf_index.xz', converters={'ssffiles': ast.literal_eval}, index_col=['hashid'])
