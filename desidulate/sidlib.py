# Copyright 2020-2022 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABL E FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import copy
import logging
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
from collections import defaultdict
import pandas as pd
import numpy as np
from desidulate.fileio import read_csv

# use of external filter will be non deterministic.
FLTEXT = False
ADSR_COLS = ['atk1', 'dec1', 'sus1', 'rel1']
CONTROL_BITS = ['gate', 'sync', 'ring', 'test', 'tri', 'saw', 'pulse', 'noise']
V1_CONTROL_BITS = [bit + '1' for bit in CONTROL_BITS]
V1_CONTROL_BITS_LABELS = {'gate1': 'g', 'sync1': 'S', 'ring1': 'R', 'test1': 'T', 'tri1': 't', 'saw1': 's', 'pulse1': 'p', 'noise1': 'n'}
CANON_REG_ORDER = (
    'gate1', 'freq1', 'pwduty1', 'pulse1', 'noise1', 'tri1', 'saw1', 'test1',
    'sync1', 'ring1', 'freq3', 'test3',
    'flt1', 'fltcoff', 'fltres', 'fltlo', 'fltband', 'flthi', 'fltext',
    'atk1', 'dec1', 'sus1', 'rel1', 'vol')


def bits2byte(df, cols, startbit=0):
    byte_col = df[cols[0]].copy()
    byte_col.loc[:] = 0
    for i, col in enumerate(cols[startbit:], start=startbit):
        byte_col += df[col].fillna(0) * 2**i
    return byte_col.rename(None)


def calc_rates(sid, maxprspeed, vdf, ratemin=128):
    rate_cols = []
    rate_col_pairs = []
    for col in {'freq1', 'pwduty1', 'freq3', 'test3', 'fltcoff', 'fltres', 'vol'}:
        col_max = vdf[col].max()
        if pd.notna(col_max) and col_max:
            rate_col = '%s_rate' % col
            rate_cols.append(rate_col)
            rate_col_pairs.append((col, rate_col))

    rate_col_df = pd.DataFrame(vdf[['clock', 'clock_start']])

    for col, rate_col in rate_col_pairs:
        diff = vdf.astype(pd.Int64Dtype()).groupby(['ssf'], sort=False)[col].diff()
        rate_col_df[rate_col] = rate_col_df['clock']
        rate_col_df.loc[(diff == 0) | diff.isna(), [rate_col]] = pd.NA

    control_col = bits2byte(vdf, V1_CONTROL_BITS)
    filter_col = bits2byte(vdf, ['flt1', 'fltlo', 'fltband', 'flthi'])
    for rate_col, col in (('control_rate', control_col), ('filter_rate', filter_col)):
        diff = col.groupby(['ssf'], sort=False).diff()
        rate_col_df[rate_col] = rate_col_df['clock']
        rate_col_df.loc[diff == 0, [rate_col]] = pd.NA
        rate_cols.append(rate_col)

    rate_col_df[rate_cols] = rate_col_df.groupby(['ssf'], sort=False)[rate_cols].fillna(
        method='ffill').diff().astype(pd.Int64Dtype())
    # remove diffs that cross SSF boundaries.
    rate_col_df.loc[rate_col_df.clock == rate_col_df.clock_start, rate_cols] = pd.NA
    rate_col_df.drop(['clock', 'clock_start'], axis=1, inplace=True)

    for col in rate_col_df.columns:
        rate_col_df.loc[rate_col_df[col] <= ratemin, col] = pd.NA

    rate_cols = [col for col in rate_col_df.columns if not rate_col_df[rate_col_df[col].notna()].empty]
    rate = rate_col_df.groupby(['ssf'], sort=False)[rate_cols].min().min(axis=1).astype(pd.Int64Dtype()).clip(upper=sid.clockq)
    pr_speed = rate.rdiv(sid.clockq).round().astype(pd.UInt8Dtype())
    pr_speed.loc[pr_speed == 0] = int(1)
    pr_speed.loc[pr_speed.isna()] = 0
    pr_speed.loc[pr_speed > maxprspeed] = 0

    return (rate, pr_speed)


def remove_end_repeats(waveforms):
    repeat_len = int(len(waveforms) / 2)
    if repeat_len > 1:
        repeat_range = [i for i in reversed(range(repeat_len + 1)) if i > 1]
        for lookback in repeat_range:
            while len(waveforms) >= lookback * 2:
                if waveforms[-lookback:] != waveforms[-(lookback*2):-lookback]:
                    break
                waveforms = waveforms[:-lookback]
    return waveforms


def remove_repeats(seq):
    non_repeats = seq[:1]
    for i in seq[1:]:
        if i != non_repeats[-1]:
            non_repeats.append(i)
            non_repeats = remove_end_repeats(non_repeats)
    return non_repeats


def bits2control(val):
    labels = []
    for i, bit in enumerate(V1_CONTROL_BITS):
        if 2**i & val:
            labels.append(V1_CONTROL_BITS_LABELS[bit])
    if labels:
        return ''.join(labels)
    return '0'


def control_label(df):
    control_reg = bits2byte(df, V1_CONTROL_BITS, startbit=1)
    df['control'] = control_reg
    control_df = pd.DataFrame([{'control': val, 'control_label': bits2control(val)} for val in control_reg.unique()])
    return df.merge(control_df, how='left', on='control')


def control_labels(df):
    df = control_label(df)
    labels = df.groupby('hashid').apply(lambda ssf_df: '-'.join(remove_repeats(list(squeeze_diffs(ssf_df, ['control'])['control_label']))))
    labels.name = 'control_labels'
    return df.merge(labels, how='left', on='hashid')


def unique_control_labels(df):
    labels = df.groupby('hashid').apply(lambda ssf_df: '-'.join(sorted(waveform for waveform in ssf_df['control_label'].unique() if 'T' not in waveform)))
    labels.name = 'unique_control_labels'
    return df.merge(labels, on='hashid', how='left')


def timer_args(parser):
    video_parser = parser.add_mutually_exclusive_group(required=False)
    video_parser.add_argument('--pal', dest='pal', action='store_true', help='Use PAL clock')
    video_parser.add_argument('--ntsc', dest='pal', action='store_false', help='Use NTSC clock')
    parser.add_argument('--cia', default=0, type=float, help='If > 0, use CIA timer in cycles')
    parser.set_defaults(pal=True, skiptest=True)


def set_sid_dtype(df):
    df.dtype = pd.UInt64Dtype()
    for col in df.columns:
        if col.startswith('freq') or col.startswith('pwduty') or col == 'fltcoff':
            col_type = pd.UInt16Dtype()
        elif col[-1].isdigit() or col.startswith('flt') or col == 'vol':
            col_type = pd.UInt8Dtype()
        else:
            continue
        df[col] = df[col].astype(col_type)
    return df


def squeeze_diffs(df, diff_cols, fill_value=0):
    return df.loc[(df[diff_cols].shift(fill_value=fill_value) != df[diff_cols]).any(axis=1)]


# Read a VICE "-sounddev dump" register dump (emulator or vsid)
def reg2state(snd_log_name, nrows=(10 * 1e6)):

    def compress_writes():
        logging.debug('reading %s', snd_log_name)
        # TODO: pyarrow can't do nrows
        df = read_csv(
            snd_log_name,
            sep=' ',
            names=['clock_offset', 'reg', 'val'],
            dtype={'clock_offset': np.uint64, 'reg': np.uint8, 'val': np.uint8})[:int(nrows)]
        logging.debug('read %u rows from %s', len(df), snd_log_name)
        df['clock'] = df['clock_offset'].cumsum()
        assert df['reg'].min() >= 0
        df = df[['clock', 'reg', 'val']]
        # remove consecutive repeated register writes
        reg_dfs = []
        reg_cols = ['reg', 'val']
        for reg in sorted(df.reg.unique()):
            reg_df = df[df['reg'] == reg]
            reg_df = squeeze_diffs(reg_df, reg_cols)
            reg_dfs.append(reg_df)
        df = pd.concat(reg_dfs)
        df = df.set_index('clock').sort_index()
        return df

    def set_bit(df, val, b, bit_name):
        df[bit_name] = np.uint8(val & 2**b)
        df[bit_name] = df[bit_name].clip(0, 1)

    def set_bits(reg_df, val, names, start=0):
        for b, name in enumerate(names, start=start):
            set_bit(reg_df, val, b, name)

    def set_hi_lo_nib(reg_df, val, hi, lo):
        reg_df[hi] = np.right_shift(val, 4)
        reg_df[lo] = val & 15

    def set_voice(reg_df, v):
        vb = (v - 1) * 7
        freq_lo = reg_df[vb]
        freq_hi = np.left_shift(reg_df[vb + 1].astype(np.uint16), 8)
        reg_df['freq%u' % v] = np.uint16(freq_hi + freq_lo)
        pwduty_lo = reg_df[vb + 2]
        pwduty_hi = np.left_shift(reg_df[vb + 3].astype(np.uint16) & 15, 8)
        reg_df['pwduty%u' % v] = np.uint16(pwduty_hi + pwduty_lo)
        control = reg_df[vb + 4]
        for b, name in enumerate(CONTROL_BITS):
            set_bit(reg_df, control, b, '%s%u' % (name, v))
        set_hi_lo_nib(reg_df, reg_df[vb + 5], 'atk%u' % v, 'dec%u' % v)
        set_hi_lo_nib(reg_df, reg_df[vb + 6], 'sus%u' % v, 'rel%u' % v)

    def set_common(reg_df):
        main = reg_df[24]
        reg_df['vol'] = main & 15
        set_bits(reg_df, main, ['fltlo', 'fltband', 'flthi', 'mute3'], start=4)
        filter_route = reg_df[23]
        set_bits(reg_df, filter_route, ['flt1', 'flt2', 'flt3', 'fltext'])
        if not FLTEXT:
            reg_df['fltext'] = 0
        reg_df['fltres'] = np.right_shift(filter_route, 4)
        filter_cutoff_lo = reg_df[21] & 7
        filter_cutoff_hi = np.left_shift(reg_df[22].astype(np.uint16), 3)
        reg_df['fltcoff'] = np.uint16(filter_cutoff_hi + filter_cutoff_lo)

    def decode_regs(df):
        max_reg = max(24, df['reg'].max())
        reg_df = df.pivot(columns='reg', values='val').fillna(
            method='ffill').fillna(0).astype(np.uint8)
        all_regs = [c for c in range(max_reg + 1)]
        for reg in all_regs:
            if reg not in reg_df.columns:
                reg_df[reg] = 0
        for v in (1, 2, 3):
            set_voice(reg_df, v)
        set_common(reg_df)
        reg_df.drop(all_regs, axis=1, inplace=True)
        return reg_df

    df = compress_writes()
    reg_df = decode_regs(df)
    df.drop(['reg', 'val'], axis=1, inplace=True)
    df = df.join(reg_df, on='clock')
    logging.debug('%u rows from %s after compression', len(df), snd_log_name)
    return df


def coalesce_near_writes(vdf, cols, near=16):
    vdf = vdf.reset_index()
    clock_diff = vdf['clock'].astype(np.int64).diff(-1).astype(pd.Int64Dtype())
    near_cond = ((clock_diff < 0) & (clock_diff >= -near))
    for b2_reg in cols:
        logging.debug('coalesce %s', b2_reg)
        b2_next = vdf[b2_reg].shift(-1)
        b2_cond = near_cond & (vdf[b2_reg] != b2_next)
        vdf.loc[b2_cond, [b2_reg]] = pd.NA
        vdf[b2_reg] = vdf[b2_reg].fillna(method='bfill')
    vdf = vdf.set_index('clock')
    return vdf


def calc_pr_frames(ssf_df, sid, first_clock_start):
    pr_speed = ssf_df['pr_speed'].clip(lower=1)
    pr_speed_q = (sid.clockq / pr_speed).astype(pd.Int32Dtype())
    pr_clock = ssf_df['clock'] + ssf_df['clock_start'] - first_clock_start
    ssf_df['pr_frame'] = pr_clock.floordiv(pr_speed_q).astype(pd.Int32Dtype())
    ssf_df['pr_frame'] -= ssf_df['pr_frame'].min()
    return ssf_df


def hash_tuple(s):
    return hash(tuple(s))


def hash_vdf(vdf, meta_cols, hashid='hashid_noclock', ssf='ssf'):
    uniq = vdf.drop(list(meta_cols), axis=1).drop_duplicates(ignore_index=True)
    merge_cols = list(uniq.columns)
    dtypes = set(uniq.dtypes.to_dict().values())
    valid_dtypes = {pd.UInt8Dtype(), pd.UInt16Dtype(), pd.Int64Dtype()}
    if dtypes - valid_dtypes:
        logging.error('invalid dtypes to hash_vdf: %s', dtypes - valid_dtypes)
        raise ValueError
    uniq['row_hash'] = uniq.apply(hash_tuple, axis=1)
    logging.debug('%u unique voice states', len(uniq))
    vdf = vdf.merge(uniq, how='left', on=merge_cols)
    vdf[hashid] = vdf.groupby([ssf], sort=False)['row_hash'].transform(hash_tuple).astype(np.int64)
    vdf.drop(['row_hash'], inplace=True, axis=1)
    return vdf


def split_vdf(sid, df, near=16, guard=96, maxprspeed=8):
    fltcols = [col for col in df.columns if col.startswith('flt') and not col[-1].isdigit()]
    mod_cols = ['freq3', 'test3', 'sync1', 'ring1']

    def v_cols(v):
        sync_map = {
           1: 3,
           2: 1,
           3: 2,
        }

        def append_voicenum(cols, v):
            return ['%s%u' % (col, v) for col in cols]

        cols = [col for col in df.columns if not col[-1].isdigit() or (col[-1] == str(v) and col != 'mute3')]
        cols.extend(append_voicenum(['freq', 'test'], sync_map[v]))
        return cols

    def renamed_cols(v, cols):
        if v == 1:
            return cols
        new_cols = []
        for col in cols:
            prefix, suffix = col[:-1], col[-1]
            if suffix.isdigit():
                if int(suffix) == v:
                    suffix = str(1)
                else:
                    suffix = str(3)
                col = ''.join((prefix, suffix))
            new_cols.append(col)
        return new_cols

    def split_gate_to_ssfs(v, v_df):
        logging.debug('splitting to SSFs for voice %u', v)
        v_df['diff_gate1'] = v_df['gate1'].astype(np.int8).diff(periods=1).fillna(0).astype(pd.Int8Dtype()).fillna(0)
        v_df['ssf'] = v_df['diff_gate1']
        v_df.loc[v_df['ssf'] != 1, ['ssf']] = 0
        v_df['ssf'] = v_df['ssf'].cumsum().astype(np.uint64)
        v_df = v_df.reset_index()
        logging.debug('%u raw SSFs for voice %u', v_df['ssf'].tail(1), v)
        return v_df

    def remove_redundant_state(v, v_df):
        if v_df['atk1'].max() or v_df['dec1'].max():
            logging.debug('removing redundant AD for voice %u', v)
            # select AD from when gate on
            ad_df = v_df[v_df['diff_gate1'] == 1][['ssf', 'atk1', 'dec1']]
            v_df.drop(['atk1', 'dec1'], axis=1, inplace=True)
            v_df = v_df.merge(ad_df, on='ssf', right_index=False)

        if v_df['rel1'].max():
            logging.debug('removing redundant R for voice %u', v)
            # select R from when gate off
            r_df = v_df[v_df['diff_gate1'] == -1][['ssf', 'rel1']]
            if not r_df.empty:
                v_df.drop(['rel1'], axis=1, inplace=True)
                v_df = v_df.merge(r_df, on='ssf', right_index=False)

        # use first non-zero S while gate on.
        logging.debug('removing redundant S for voice %u', v)
        v_df.loc[v_df['sus1'] == 0, 'sus1'] = pd.NA
        v_df['sus1'] = v_df['sus1'].fillna(method='bfill').fillna(0)
        v_df.loc[(v_df['diff_gate1'] == 1) & (v_df['sus1'] == 0) & (v_df['atk1'] == 0), ['sus1']] = 15

        v_df.loc[v_df['diff_gate1'] != 1, ['atk1', 'dec1', 'sus1', 'rel1']] = pd.NA
        v_df.drop(['diff_gate1'], axis=1, inplace=True)

        # http://www.ffd2.com/fridge/chacking/c=hacking20.txt
        # http://www.ffd2.com/fridge/chacking/c=hacking21.txt
        # https://codebase64.org/doku.php?id=base:vicious_sid_demo_routine_explained
        # https://bitbucket.org/wothke/websid/src/master/docs/digi-samples.txt

        v_df.set_index('ssf', inplace=True)

        logging.debug('removing redundant state for voice %u', v)
        # If test1 is set only at the start of the SSF, remove inaudible state.
        v_df['test1_first'] = v_df['clock']
        v_df.loc[v_df['test1'] == 1, ['test1_first']] = pd.NA
        v_df['test1_first'] = v_df.groupby(['ssf'], sort=False)['test1_first'].min()
        v_df.loc[(v_df['test1'] == 1) & (v_df['clock'] <= v_df['test1_first']), ['freq1', 'pwduty1', 'flt1']] = pd.NA
        v_df.drop(['test1_first'], axis=1, inplace=True)

        # remove modulator voice state while sync1/ring1 not set
        v_df.loc[(v_df['freq3'] == 0), ['ring1', 'sync1']] = 0
        v_df.loc[(v_df['ring1'] == 1) & (v_df['tri1'] == 0), ['ring1']] = 0
        v_df.loc[~((v_df['sync1'] == 1) | ((v_df['ring1'] == 1) & (v_df['tri1'] == 1))), mod_cols] = pd.NA
        # remove carrier state when waveform 0
        v_df.loc[~((v_df['tri1'] == 1) | (v_df['saw1'] == 1) | (v_df['noise1'] == 1) | (v_df['pulse1'] == 1)), ['freq1'] + mod_cols] = pd.NA
        # remove filter state when no filter.
        v_df.loc[(v_df['flt1'] == 0) | v_df['flt1'].isna(), fltcols] = pd.NA
        # remove pwduty state when no pulse1 set.
        v_df.loc[(v_df['pulse1'] == 0) | v_df['pulse1'].isna(), ['pwduty1']] = pd.NA

        # remove trailing rows when test1 set.
        v_df['test1_last'] = v_df['clock']
        v_df.loc[v_df['test1'] == 1, ['test1_last']] = pd.NA
        v_df['test1_last'] = v_df.groupby(['ssf'], sort=False)['test1_last'].max()
        v_df = v_df[(v_df['clock'] <= v_df['test1_last'])]
        v_df.drop(['test1_last'], axis=1, inplace=True)

        # remove trailing rows when no waveform set.
        v_df['waveform_last'] = v_df['clock']
        v_df.loc[(v_df['pulse1'] == 0) & (v_df['tri1'] == 0) & (v_df['noise1'] == 0) & (v_df['saw1'] == 0), ['waveform_last']] = pd.NA
        v_df['waveform_last'] = v_df.groupby(['ssf'], sort=False)['waveform_last'].max()
        # also removes SSFs with no waveform.
        v_df = v_df[(v_df['clock'] <= v_df['waveform_last'])]
        v_df.drop(['waveform_last'], axis=1, inplace=True)
        return v_df

    df = set_sid_dtype(df)
    df = coalesce_near_writes(df, ('fltcoff',), near=near)
    # when filter is not routed, cutoff and resonance do not matter.
    df.loc[(df['flthi'] == 0) & (df['fltband'] == 0) & (df['fltlo'] == 0), ['fltcoff', 'fltres']] = pd.NA
    # never use externally filtered audio
    df.loc[:, 'fltext'] = pd.NA
    df = set_sid_dtype(df)
    v_dfs = []
    ssfs = 0
    non_meta_cols = set()

    for v in (0, 1, 2, 3):
        logging.debug('splitting voice %u', v)

        if v:
            if df['gate%u' % v].max() == 0:
                continue
            cols = v_cols(v)
            v_df = df[cols].copy()
            v_df.loc[:, 'vol'] = pd.NA
            v_df.columns = renamed_cols(v, cols)

            logging.debug('coalescing near writes for voice %u', v)
            v_df = coalesce_near_writes(v_df, ('freq1', 'pwduty1', 'freq3'), near=near)
            v_df = split_gate_to_ssfs(v, v_df)
            v_df = remove_redundant_state(v, v_df)
            non_meta_cols = set(v_df.columns)
        else:
            cols = v_cols(1)
            v_df = df[cols].copy()
            non_vol_cols = copy.deepcopy(cols)
            non_vol_cols.remove('vol')
            v_df.columns = renamed_cols(1, cols)
            v_df.loc[:, non_vol_cols] = pd.NA

            diff_vol = v_df['vol'].astype(np.int8).diff(periods=1).fillna(0).astype(pd.Int8Dtype()).fillna(0)
            v_df['ssf'] = diff_vol
            v_df.loc[v_df['ssf'] != 0, ['ssf']] = 1
            v_df['ssf'] = v_df['ssf'].cumsum().astype(np.uint64)
            v_df = v_df.reset_index()
            v_df.set_index('ssf', inplace=True)
            non_meta_cols = {'vol'}

        non_meta_cols -= {'clock'}
        v_df = set_sid_dtype(v_df)
        logging.debug('calculating clock for voice %u', v)
        v_df['clock_start'] = v_df.groupby(['ssf'], sort=False)['clock'].min()
        v_df['next_clock_start'] = v_df['clock_start'].shift(-1).astype(pd.Int64Dtype())
        v_df['next_clock_start'] = v_df.groupby(['ssf'], sort=False)['next_clock_start'].max()
        v_df['next_clock_start'] = v_df['next_clock_start'].fillna(v_df['clock'].max())

        # discard state changes within N cycles of next SSF.
        guard_start = v_df['next_clock_start'] - v_df['clock'].astype(pd.Int64Dtype())
        v_df = v_df[~((guard_start > 0) & (guard_start < guard))]

        # extract only changes
        logging.debug('extracting only state changes for voice %u (rows before %u)', v, len(v_df))
        v_df = v_df.reset_index().set_index('clock')
        v_df = squeeze_diffs(v_df, list(non_meta_cols))

        logging.debug('extracted only state changes for voice %u (rows after %u)', v, len(v_df))
        v_df = v_df.reset_index().set_index('ssf')

        if v_df.empty:
            continue

        logging.debug('calculating rates for voice %u', v)
        v_df['rate'], v_df['pr_speed'] = calc_rates(sid, maxprspeed, v_df)
        pr_speeds = v_df['pr_speed'].unique()
        logging.debug('pr_speeds for voice %u: %s', v, sorted(pr_speeds))
        pr_speeds = v_df.reset_index()[['ssf', 'pr_speed']].groupby('pr_speed')['ssf'].nunique().to_dict()
        sorted_pr_speeds = sorted(pr_speeds.items(), key=lambda x: x[1], reverse=True)
        logging.debug(f'min/mean/max rate {v_df.rate.min()}/{v_df.rate.mean()}/{v_df.rate.max()} for voice {v} (counts {sorted_pr_speeds})')

        v_df['clock'] -= v_df['clock_start']
        v_df.reset_index(level=0, inplace=True)

        v_df['v'] = v
        v_df['ssf'] += ssfs
        ssfs = v + v_df['ssf'].max()
        v_dfs.append(v_df)

    if v_dfs:
        v_dfs = pd.concat(v_dfs)
        logging.debug('calculating row hashes on %s', sorted(non_meta_cols))
        v_dfs = hash_vdf(v_dfs, set(v_dfs.columns) - non_meta_cols)
        prefix_cols = ['pr_speed', 'clock']
        meta_cols = [col for col in v_dfs.columns if col not in CANON_REG_ORDER and col not in prefix_cols]
        v_dfs = v_dfs[prefix_cols + [col for col in CANON_REG_ORDER if col in v_dfs.columns] + meta_cols]

        for v, v_df in v_dfs.groupby('v'):
            yield (v, v_df.drop(['v'], axis=1))


def ssf_start_duration(sid, ssf_df):
    clock_duration = ssf_df['clock'].max() + sid.clockq
    next_clock_start = ssf_df['next_clock_start'].iat[-1]
    clock_start = ssf_df['clock_start'].iat[-1]

    if pd.notna(next_clock_start):
        if next_clock_start > clock_start:
            clock_duration = next_clock_start - clock_start - 1
    return (clock_start, clock_duration)


def pad_ssf_duration(sid, ssf_df, first_clock_duration):
    _clock_start, clock_duration = ssf_start_duration(sid, ssf_df)
    last_row_df = ssf_df[-1:].copy()
    last_row_df['clock'] = clock_duration
    last_row_df = last_row_df.astype(ssf_df.dtypes.to_dict())
    ssf_df = pd.concat([ssf_df, last_row_df], ignore_index=True).reset_index(drop=True)
    ssf_df = calc_pr_frames(ssf_df, sid, first_clock_duration).drop(['ssf', 'clock_start', 'next_clock_start'], axis=1)
    return ssf_df


def state2ssfs(sid, df, maxprspeed=8, near=16):
    ssf_log = []
    ssf_dfs = {}
    ssf_count = defaultdict(int)

    for v, v_df in split_vdf(sid, df, maxprspeed=maxprspeed, near=near):
        ssfs = v_df['ssf'].nunique()
        voice_ssfs = set()
        logging.debug('splitting %u SSFs for voice %u', ssfs, v)
        first_clock_start = int(v_df['clock_start'].iat[0] / sid.clockq) * sid.clockq
        for hashid_noclock_pr_speed, hashid_noclock_df in v_df.groupby(['hashid_noclock', 'pr_speed'], sort=False):
            hashid_noclock, pr_speed = hashid_noclock_pr_speed
            hashid = hash((hashid_noclock, pr_speed))
            group_ssf_dfs = [ssf_df for _, ssf_df in hashid_noclock_df.groupby('ssf', sort=True)]
            ssf_df = group_ssf_dfs[0]
            ssf_dfs[hashid] = pad_ssf_duration(sid, ssf_df, first_clock_start)
            ssf_count[hashid] += len(group_ssf_dfs)
            clock_starts = [ssf_df['clock_start'].iat[0] for ssf_df in group_ssf_dfs]
            ssf_log.extend([{'clock': clock_start, 'hashid': hashid, 'voice': v} for clock_start in clock_starts])
            voice_ssfs.add(hashid)
        logging.debug('reduced to unique %u SSFs for voice %u', len(voice_ssfs), v)

    for hashid, count in ssf_count.items():
        ssf_dfs[hashid]['count'] = count
        ssf_dfs[hashid]['hashid'] = hashid

    def concat_dfs(x, y):
        if x and y:
            return pd.concat([
                x[hashid] for hashid, count in sorted(y.items(), key=lambda i: i[1], reverse=True)]).set_index('hashid')
        return pd.DataFrame()

    ssf_log_df = pd.DataFrame()
    if ssf_log:
        ssf_log_df = pd.DataFrame(
            ssf_log, dtype=pd.Int64Dtype()).set_index('clock').sort_index()

    ssf_df = concat_dfs(ssf_dfs, ssf_count)

    logging.debug('%u SSFs', ssf_df.index.nunique())
    return ssf_log_df, ssf_df
