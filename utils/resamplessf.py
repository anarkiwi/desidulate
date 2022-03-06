#!/usr/bin/python3

# Copyright 2020-2022 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import argparse
from collections import defaultdict
import numpy as np
import pandas as pd

from desidulate.fileio import out_path, read_csv
from desidulate.sidlib import df_waveform_order, resampledf_to_pr, timer_args, get_sid, ADSR_COLS

parser = argparse.ArgumentParser(description='Downsample SSFs to frames')
parser.add_argument('ssffile', help='SSF file')
parser.add_argument('--max_clock', default=500000, type=int, help='include number of cycles')
parser.add_argument('--max_pr_speed', default=8, type=int, help='max pr_speed')
timer_args(parser)

args = parser.parse_args()
waveform_cols = {'sync1', 'ring1', 'tri1', 'saw1', 'pulse1', 'noise1'}
adsr_cols = {'atk1', 'dec1', 'sus1', 'rel1'}
sid_cols = { # exclude vol, fltext
    'freq1', 'pwduty1', 'test1',
    'fltlo', 'fltband', 'flthi', 'flt1', 'fltres', 'fltcoff',
    'freq3', 'test3'}.union(waveform_cols).union(adsr_cols)
big_regs = {'freq1': 8, 'freq3': 8, 'pwduty1': 4, 'fltcoff': 3}
sid = get_sid(pal=args.pal)


def col_diffs(col):
    diff = col.diff()
    return diff[diff != 0].count()


def resample():
    clockrq = int(sid.clockq / (args.max_pr_speed * 2))
    df = read_csv(args.ssffile, dtype=pd.Int64Dtype())
    df_raws = defaultdict(list)
    if len(df) < 1:
        return df_raws
    df = df[(df['clock'] <= args.max_clock) & (df['pr_speed'] <= args.max_pr_speed)]
    for col, bits in big_regs.items():
        df[col] = np.left_shift(np.right_shift(df[col], bits), bits)
    df['clockrq'] = df['clock'].floordiv(clockrq)
    meta_cols = set(df.columns) - sid_cols
    meta_cols -= {'clock'}

    for hashid, ssf_df in df.groupby(['hashid']):  # pylint: disable=no-member
        vol_changes = col_diffs(ssf_df['vol'])
        test_changes = col_diffs(ssf_df['test1'])
        if vol_changes > 2 or test_changes > 2:
            continue
        first_row = ssf_df.iloc[0]
        ssf_df.drop_duplicates(['hashid', 'clockrq'], keep='last', inplace=True)
        for col in ADSR_COLS:
            ssf_df[col] = getattr(first_row, col)
        pre_waveforms = df_waveform_order(ssf_df)
        resample_df = ssf_df.reset_index(drop=True).set_index('clock')
        resample_df = resampledf_to_pr(resample_df)
        cols = (set(resample_df.columns) - meta_cols)
        df_raw = {col: resample_df[col].iat[-1] for col in meta_cols - {'pr_frame'}}
        waveforms = df_waveform_order(resample_df)
        if pre_waveforms != waveforms:
            if pre_waveforms[0] == '0':
                pre_waveforms = pre_waveforms[1:]
        if pre_waveforms != waveforms:
            print(hashid)
            print(pre_waveforms)
            print(waveforms)
            orig = ssf_df.reset_index(drop=True).set_index('clock').drop(['hashid', 'hashid_noclock', 'vbi_frame'], axis=1)
            # orig.drop(['rate', 'pr_speed', 'count', 'pr_frame'], axis=1)
            print(orig)
            print(resample_df.drop(['hashid', 'hashid_noclock', 'vbi_frame'], axis=1))
            # assert False

        for row in resample_df.itertuples():
            time_cols = {(col, '%s_%u' % (col, row.pr_frame)) for col in cols if not (col in adsr_cols and row.pr_frame)}
            df_raw.update({time_col: getattr(row, col) for col, time_col in time_cols})
        for col in big_regs:
            col_raw = resample_df[resample_df[col].notna()][col]
            col_diff = col_raw.diff()
            for col_title, col_var in (
                    ('%s_mindiff' % col, col_diff.min()),
                    ('%s_maxdiff' % col, col_diff.max()),
                    ('%s_meandiff' % col, col_diff.mean()),
                    ('%s_nunique' % col, col_raw.nunique())):
                df_raw[col_title] = pd.NA
                if pd.notna(col_var):
                    df_raw[col_title] = int(col_var)

        waveforms = '-'.join(waveforms)
        df_raws[(ssf_df['pr_speed'].iat[0], waveforms)].append(df_raw)
    return df_raws


def main():
    df_raws = resample()
    for pr_speed_waveforms, dfs in df_raws.items():
        pr_speed, waveforms = pr_speed_waveforms
        df = pd.DataFrame(dfs, dtype=pd.Int64Dtype()).set_index('hashid')
        nacols = [col for col in df.columns if df[col].isnull().all() or df[col].max() == 0]
        df.drop(nacols, axis=1, inplace=True)
        df.drop_duplicates(inplace=True)
        outfile = out_path(args.ssffile, 'resample_ssf.%u.%s.xz' % (pr_speed, waveforms))
        df.to_csv(outfile)


if __name__ == '__main__':
    main()
