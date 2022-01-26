#!/usr/bin/python3

import ast
import copy
import pandas as pd
import pyarrow as pa

waveform_order = 'p-n-p'
dbdir = '/usr/local/datasets/hvsc-76'


def read_dfs(waveform_order, dbdir):
    hdf = pd.read_csv('%s/resample_ssf.%s.xz' % (dbdir, waveform_order), dtype=pd.Int64Dtype(), nrows=1)
    match_cols = hdf.columns.to_list()
    match_cols = [col for col in match_cols if col == 'test1_0' or not col.startswith(('vol', 'atk', 'sus', 'rel', 'flt', 'test'))]
    match_cols = [col for col in match_cols if not col.startswith('freq1') or not col[-1].isdigit()]
    df = pd.read_csv('%s/resample_ssf.%s.xz' % (dbdir, waveform_order), engine='pyarrow', dtype=pd.Int64Dtype(), usecols=match_cols).fillna(0)
    match_cols.remove('hashid')
    match_cols.remove('hashid_noclock')
    return (df, match_cols)


def describe_matches(match_df, waveform_order, dbdir):
    hash_df = pd.read_csv('%s/resample_ssf.hashid.%s.xz' % (dbdir, waveform_order), engine='pyarrow', index_col='hashid')
    xdf = match_df.join(hash_df)
    print(xdf)
    xdf['sources'] = xdf['sources'].apply(ast.literal_eval)
    for row in xdf.itertuples():
        for source in row.sources:
            print('%s/%s.%d.wav' % (dbdir, source, row.Index))


hashid = -8980603949025395325
matching_hashids = {hashid}
df, match_cols = read_dfs(waveform_order, dbdir)

while True:
    i = len(matching_hashids)
    hashid_df = df[df.hashid.isin(matching_hashids)]
    match_df = pd.merge(df, hashid_df, on=match_cols).set_index('hashid_x')
    noclocks = set(match_df.hashid_noclock_x.unique())
    matching_hashids.update(set(match_df.index.unique()))
    matching_hashids.update(set(df[df.hashid_noclock.isin(noclocks)].hashid.unique()))
    if len(matching_hashids) == i:
        break
    print('next')

describe_matches(df[df.hashid.isin(matching_hashids)].set_index('hashid'), waveform_order, dbdir)
