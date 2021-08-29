#!/usr/bin/python3

# Copyright 2021 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.


import os
from collections import defaultdict
import concurrent.futures
from pathlib import Path
import pandas as pd

MAX_WORKERS = 4
SSF_SUFFIX = 'control_ssf'
SSF_ROOT = r'.'
SSF_EXT = '.%s.xz' % SSF_SUFFIX


def index_dir(dirname):
    dir_index = defaultdict(set)
    dir_paths = [os.path.join(dirname, filename) for filename in os.listdir(dirname)]
    dir_paths = [file_path for file_path in dir_paths if os.path.isfile(file_path) and file_path.endswith(SSF_EXT)]
    for path in dir_paths:
        try:
            hashids = pd.read_csv(path, usecols=['hashid'])['hashid'].unique()
            for file_hashid in hashids:
                dir_index[file_hashid].add(os.path.basename(path))
        except ValueError:
            continue
    return dir_index


global_dir_index = defaultdict(set)
with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
    result_futures = map(lambda x: executor.submit(index_dir, x), Path(SSF_ROOT).glob('**/'))
    for future in concurrent.futures.as_completed(result_futures):
        for hashid, paths in future.result().items():
            global_dir_index[hashid].update(paths)

df = pd.DataFrame(global_dir_index.items(), columns=['hashid', 'ssffiles'])
df['ssffileslen'] = df.ssffiles.transform(len)
df.to_csv('%s_index.xz' % SSF_SUFFIX, index=False)

# to re-read
# df = pd.read_csv('control_ssf_index.xz', converters={'ssffiles': ast.literal_eval}, index_col=['hashid'])
