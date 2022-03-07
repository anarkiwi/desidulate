# Copyright 2020-2022 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABL E FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import logging
from collections import defaultdict
from datetime import timedelta
import pandas as pd
import numpy as np
from pyresidfp import SoundInterfaceDevice
from pyresidfp.sound_interface_device import ChipModel
from desidulate.fileio import read_csv

SID_SAMPLE_FREQ = 11025
# use of external filter will be non deterministic.
FLTEXT = False
ADSR_COLS = ['atk1', 'dec1', 'sus1', 'rel1']
CONTROL_BITS = ['gate', 'sync', 'ring', 'test', 'tri', 'saw', 'pulse', 'noise']
WAVEFORM_COLS = tuple(sorted((('S', 'sync1'), ('R', 'ring1'), ('t', 'tri1'), ('s', 'saw1'), ('p', 'pulse1'), ('n', 'noise1'))))
WAVEFORM_COLS_ORIG = [col[1] for col in WAVEFORM_COLS]
CANON_REG_ORDER = (
    'gate1', 'freq1', 'pwduty1', 'pulse1', 'noise1', 'tri1', 'saw1', 'test1',
    'sync1', 'ring1', 'freq3', 'test3',
    'flt1', 'fltcoff', 'fltres', 'fltlo', 'fltband', 'flthi', 'fltext',
    'atk1', 'dec1', 'sus1', 'rel1', 'vol')


def bits2byte(df, cols):
    byte_col = df[cols[0]].fillna(0)
    for i, col in enumerate(cols[1:], start=1):
        byte_col += df[col].fillna(0) * 2**i
    return byte_col


def calc_rates(sid, maxprspeed, vdf):
    ratemin = int(sid.clockq / (maxprspeed + 1))
    rate_cols = []
    rate_col_pairs = []
    for col in {'freq1', 'pwduty1', 'freq3', 'test3', 'fltcoff', 'fltres', 'vol'}:
        col_max = vdf[col].max()
        if pd.notna(col_max) and col_max:
            rate_col = '%s_rate' % col
            rate_cols.append(rate_col)
            rate_col_pairs.append((col, rate_col))

    rate_col_df = pd.DataFrame(vdf['clock'])

    for col, rate_col in rate_col_pairs:
        diff = vdf.astype(pd.Int64Dtype()).groupby(['ssf'], sort=False)[col].diff()
        rate_col_df[rate_col] = rate_col_df['clock']
        rate_col_df.loc[(diff == 0) | diff.isna(), [rate_col]] = pd.NA

    control_col = bits2byte(vdf, [col + '1' for col in CONTROL_BITS])
    filter_col = bits2byte(vdf, ['flt1', 'fltlo', 'fltband', 'flthi'])
    for rate_col, col in (('control_rate', control_col), ('filter_rate', filter_col)):
        diff = col.groupby(['ssf'], sort=False).diff()
        rate_col_df[rate_col] = rate_col_df['clock']
        rate_col_df.loc[diff == 0, [rate_col]] = pd.NA
        rate_cols.append(rate_col)

    rate_col_df.drop(['clock'], axis=1, inplace=True)
    rate_col_df[rate_cols] = rate_col_df.groupby(['ssf'], sort=False)[rate_cols].fillna(
        method='ffill').diff().astype(pd.Int64Dtype())

    for col in rate_col_df.columns:
        rate_col_df.loc[rate_col_df[col] <= ratemin, col] = pd.NA
    rate_cols = [col for col in rate_col_df.columns if not rate_col_df[rate_col_df[col].notna()].empty]
    rate = rate_col_df.groupby(['ssf'], sort=False)[rate_cols].min().min(axis=1).astype(pd.Int64Dtype()).clip(upper=sid.clockq)
    pr_speed = rate.rdiv(sid.clockq).round().astype(pd.UInt8Dtype())
    pr_speed.loc[pr_speed == 0] = int(1)

    return (rate, pr_speed)


def calc_vbi_frame(sid, clock):
    vbi_frame = clock.astype(pd.Float32Dtype())
    vbi_frame = vbi_frame.floordiv(sid.clockq).astype(pd.Int64Dtype())
    return vbi_frame


def resampledf_to_pr(ssf_df):
    pr_speed = ssf_df['pr_speed'].iat[0]
    first_row = ssf_df.iloc[0]
    resample_df = ssf_df.drop_duplicates('pr_frame', keep='last').reset_index(drop=True).drop('vbi_frame', axis=1).copy()
    resample_df_clock = ssf_df[['pr_frame', 'vbi_frame']].reset_index().drop_duplicates('pr_frame', keep='first').copy()
    resample_df = resample_df.merge(resample_df_clock, on='pr_frame').set_index('clock').sort_index()
    for col in ADSR_COLS:
        resample_df[col] = int(getattr(first_row, col))
    return resample_df


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


def df_waveform_order(df):
    waveforms = []
    squeeze_df = df[WAVEFORM_COLS_ORIG].fillna(0)
    for row in squeeze_df.itertuples():
        row_waveforms = (
            (mapped_col, getattr(row, waveform_col)) for mapped_col, waveform_col in WAVEFORM_COLS)
        row_waveforms = [
            waveform_col for waveform_col, waveform_val in row_waveforms if waveform_val]
        if row_waveforms:
            row_waveforms = ''.join(row_waveforms)
        else:
            row_waveforms = '0'
        if not waveforms or row_waveforms != waveforms[-1]:
            waveforms.append(row_waveforms)
            waveforms = remove_end_repeats(waveforms)
    return waveforms


def timer_args(parser):
    pal_parser = parser.add_mutually_exclusive_group(required=False)
    pal_parser.add_argument('--pal', dest='pal', action='store_true', help='Use PAL clock')
    pal_parser.add_argument('--ntsc', dest='pal', action='store_false', help='Use NTSC clock')
    parser.set_defaults(pal=True, skiptest=True)


def set_sid_dtype(df):
    df.dtype = pd.UInt64Dtype()
    for col in df.columns:
        if col.startswith('freq') or col.startswith('pwduty') or col == 'fltcoff':
            col_type = pd.UInt16Dtype()
        elif col[-1].isdigit() or col.startswith('flt'):
            col_type = pd.UInt8Dtype()
        else:
            continue
        df[col] = df[col].astype(col_type)
    return df


def squeeze_diffs(df, diff_cols, fill_value=0):
    return df.loc[(df[diff_cols].shift(fill_value=fill_value) != df[diff_cols]).any(axis=1)]


class SidWrap:

    ATTACK_MS = {
        0: 2,
        1: 8,
        2: 16,
        3: 24,
        4: 38,
        5: 56,
        6: 68,
        7: 80,
        8: 100,
        9: 250,
        10: 500,
        11: 800,
        12: 1000,
        13: 3000,
        14: 5000,
        15: 8000,
    }

    DECAY_RELEASE_MS = {
        0: 6,
        1: 24,
        2: 48,
        3: 72,
        4: 114,
        5: 168,
        6: 204,
        7: 240,
        8: 300,
        9: 750,
        10: 1500,
        11: 2400,
        12: 3000,
        13: 9000,
        14: 15000,
        15: 24000,
    }

    def __init__(self, pal, model, sampling_frequency):
        # https://codebase64.org/doku.php?id=magazines:chacking17
        if pal:
            self.clock_freq = SoundInterfaceDevice.PAL_CLOCK_FREQUENCY
            self.raster_lines = 312
            self.cycles_per_line = 63
        else:
            self.clock_freq = SoundInterfaceDevice.NTSC_CLOCK_FREQUENCY
            self.raster_lines = 263
            self.cycles_per_line = 65
        self.clockq = self.raster_lines * self.cycles_per_line
        self.int_freq = self.clock_freq / self.clockq
        self.freq_scaler = self.clock_freq / 16777216
        self.resid = SoundInterfaceDevice(
            model=model, clock_frequency=self.clock_freq,
            sampling_frequency=sampling_frequency)
        self.attack_clock = {
            k: int(v / 1e3 * self.clock_freq) for k, v in self.ATTACK_MS.items()}
        self.decay_release_clock = {
            k: int(v / 1e3 * self.clock_freq) for k, v in self.DECAY_RELEASE_MS.items()}

    def qn_to_clock(self, qn, bpm):
        return self.clock_freq * 60 / bpm * qn

    def clock_to_s(self, clock):
        return clock / self.clock_freq

    def clock_to_qn(self, clock, bpm):
        return self.clock_to_s(clock) * bpm / 60

    def clock_to_ticks(self, clock, bpm, tpqn):
        return self.clock_to_qn(clock, bpm) * tpqn

    def real_sid_freq(self, freq_reg):
        # http://www.sidmusic.org/sid/sidtech2.html
        return freq_reg * self.freq_scaler

    def add_samples(self, offset):
        timeoffset_seconds = offset / self.clock_freq
        return self.resid.clock(timedelta(seconds=timeoffset_seconds))


def get_sid(pal, model=ChipModel.MOS8580, sampling_frequency=SID_SAMPLE_FREQ):
    return SidWrap(pal, model, sampling_frequency)


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
    near_cond = ((clock_diff < 0) & (clock_diff > -near))
    for b2_reg in cols:
        logging.debug('coalesce %s', b2_reg)
        b2_next = vdf[b2_reg].shift(-1)
        b2_cond = near_cond & (vdf[b2_reg] != b2_next)
        vdf.loc[b2_cond, [b2_reg]] = pd.NA
        vdf[b2_reg] = vdf[b2_reg].fillna(method='bfill')
    vdf = vdf.set_index('clock')
    return vdf


def split_vdf(sid, df, near=16, guard=96, maxprspeed=20):
    fltcols = [col for col in df.columns if col.startswith('flt') and not col[-1].isdigit()]
    mod_cols = ['freq3', 'test3', 'sync1', 'ring1']

    def hash_tuple(s):
        return hash(tuple(s))

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

    def hash_vdf(vdf, non_meta_cols):
        meta_cols = set(vdf.columns) - non_meta_cols
        uniq = vdf.drop(list(meta_cols), axis=1).drop_duplicates(ignore_index=True)
        merge_cols = list(uniq.columns)
        uniq['row_hash'] = uniq.apply(hash_tuple, axis=1)
        logging.debug('%u unique voice states', len(uniq))
        vdf = vdf.merge(uniq, how='left', on=merge_cols)
        vdf['hashid_noclock'] = vdf.groupby(['ssf'], sort=False)['row_hash'].transform(hash_tuple).astype(np.int64)
        vdf.drop(['row_hash'], inplace=True, axis=1)
        return vdf

    df = set_sid_dtype(df)
    df = coalesce_near_writes(df, ('fltcoff',), near=near)
    # when filter is not routed, cutoff and resonance do not matter.
    df.loc[(df['flthi'] == 0) & (df['fltband'] == 0) & (df['fltlo'] == 0), ['fltcoff', 'fltres']] = pd.NA
    v_dfs = []
    ssfs = 0
    non_meta_cols = set()

    for v in (1, 2, 3):
        logging.debug('splitting voice %u', v)
        if df['gate%u' % v].max() == 0:
            continue
        cols = v_cols(v)
        v_df = df[cols].copy()
        v_df.columns = renamed_cols(v, cols)
        non_meta_cols = set(v_df.columns)

        logging.debug('coalescing near writes for voice %u', v)
        v_df = coalesce_near_writes(v_df, ('freq1', 'pwduty1', 'freq3'), near=near)

        # split on gate on transitions into SSFs
        logging.debug('splitting to SSFs for voice %u', v)
        v_df['diff_gate1'] = v_df['gate1'].astype(np.int8).diff(periods=1).fillna(0).astype(pd.Int8Dtype()).fillna(0)
        v_df['ssf'] = v_df['diff_gate1']
        v_df.loc[v_df['ssf'] != 1, ['ssf']] = 0
        v_df['ssf'] = v_df['ssf'].cumsum().astype(np.uint64)
        v_df = v_df.reset_index()
        logging.debug('%u raw SSFs for voice %u', v_df['ssf'].tail(1), v)

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

        # TODO: Skip SSFs with sample playback.
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
        v_df.loc[
            (v_df['test1'] == 1) & (v_df['clock'] <= v_df['test1_first']),
            ['freq1', 'tri1', 'saw1', 'pulse1', 'noise1', 'flt1'] + mod_cols] = pd.NA
        v_df.drop(['test1_first'], axis=1, inplace=True)

        # fold noise1 + other waveforms, to waveform 0.
        v_df.loc[(v_df['noise1'] == 1) & ((v_df['pulse1'] == 1) | (v_df['saw1'] == 1) | (v_df['tri1'] == 1)), ['noise1', 'pulse1', 'saw1', 'tri1']] = 0
        # remove modulator voice state while sync1/ring1 not set
        v_df.loc[(v_df['freq3'] == 0), ['ring1', 'sync1']] = 0
        v_df.loc[(v_df['ring1'] == 1) & (v_df['tri1'] == 0), ['ring1']] = 0
        v_df.loc[~((v_df['sync1'] == 1) | ((v_df['ring1'] == 1) & (v_df['tri1'] == 1))), mod_cols] = pd.NA
        # remove carrier state when waveform 0
        v_df.loc[~((v_df['tri1'] == 1) | (v_df['saw1'] == 1) | (v_df['noise1'] == 1) | (v_df['pulse1'] == 1)), ['freq1', 'flt1'] + mod_cols] = pd.NA
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
        v_df = squeeze_diffs(v_df, v_df.columns)
        logging.debug('extracted only state changes for voice %u (rows after %u)', v, len(v_df))
        v_df = v_df.reset_index().set_index('ssf')

        # remove empty SSFs
        for col in ('freq1', 'vol', 'gate1'):
            logging.debug('removing empty SSFs with no %s for voice %u (%u rows before)', col, v, len(v_df))
            v_df['max_col'] = v_df.groupby('ssf', sort=False)[col].max()
            v_df = v_df[v_df['max_col'] > 0]
            v_df.drop(['max_col'], axis=1, inplace=True)
        v_df['test1_min'] = v_df.groupby('ssf', sort=False)['test1'].min()
        v_df = v_df[v_df['test1_min'] == 0]
        v_df.drop(['test1_min'], axis=1, inplace=True)

        if v_df.empty:
            continue

        logging.debug('calculating rates for voice %u', v)
        v_df['rate'], v_df['pr_speed'] = calc_rates(sid, maxprspeed, v_df)
        pr_speeds = v_df[v_df['pr_speed'].notna()]['pr_speed'].unique()
        if len(pr_speeds) == 0:
            logging.debug('no pr_speed detected for voice %u', v)
        else:
            logging.debug('pr_speeds for voice %u: %s', v, sorted(pr_speeds))
            pr_speeds = v_df[v_df['pr_speed'].notna()].reset_index()[['ssf', 'pr_speed']].groupby('pr_speed')['ssf'].nunique().to_dict()
            sorted_pr_speeds = sorted(pr_speeds.items(), key=lambda x: x[1], reverse=True)
            logging.debug('min/mean/max rate %u/%u/%u for voice %u (counts %s)',
                v_df['rate'].min(), v_df['rate'].mean(), v_df['rate'].max(), v, sorted_pr_speeds)

        v_df['vbi_frame'] = calc_vbi_frame(sid, v_df['clock'])
        v_df['pr_frame'] = v_df['clock'].floordiv(v_df['rate']).astype(pd.Int64Dtype())
        # not playroutine? default to vbi.
        v_df['pr_frame'].where(v_df['pr_frame'].notna(), v_df['vbi_frame'], inplace=True)

        for col in ('vbi_frame', 'pr_frame'):
            col_min = v_df.groupby('ssf', sort=False)[col].min()
            v_df[col] -= col_min
        v_df['clock'] -= v_df['clock_start']

        v_df.reset_index(level=0, inplace=True)

        v_df['v'] = v
        v_df['ssf'] += ssfs
        ssfs = v + v_df['ssf'].max()
        v_dfs.append(v_df)

    if v_dfs:
        v_dfs = pd.concat(v_dfs)
        logging.debug('calculating row hashes on %s', sorted(non_meta_cols))
        v_dfs = hash_vdf(v_dfs, non_meta_cols)
        logging.debug('calculating clock hashes')
        v_dfs['hashid_clock'] = v_dfs.groupby(['ssf'], sort=False)['clock'].transform(hash_tuple).astype(np.int64)
        prefix_cols = ['clock', 'vbi_frame', 'pr_frame']
        meta_cols = [col for col in v_dfs.columns if col not in CANON_REG_ORDER and col not in prefix_cols]
        v_dfs = v_dfs[prefix_cols + [col for col in CANON_REG_ORDER if col in v_dfs.columns] + meta_cols]

        for v, v_df in v_dfs.groupby('v'):
            yield (v, v_df.drop(['v'], axis=1))


def jittermatch_df(df1, df2, jitter_col, jitter_max):
    df1_col = df1[jitter_col].reset_index(drop=True).astype(pd.Int64Dtype())
    df2_col = df2[jitter_col].reset_index(drop=True).astype(pd.Int64Dtype())
    if len(df1_col) == len(df2_col):
        diff = df1_col - df2_col
        diff_max = diff.abs().max()
        return pd.notna(diff_max) and diff_max < jitter_max
    return False


def ssf_start_duration(sid, ssf_df):
    clock_duration = ssf_df['clock'].max() + sid.clockq
    next_clock_start = ssf_df['next_clock_start'].iat[-1]
    clock_start = ssf_df['clock_start'].iat[-1]
    if pd.notna(next_clock_start):
        if next_clock_start > clock_start:
            clock_duration = next_clock_start - clock_start - 1
    return (clock_start, clock_duration)


def pad_ssf_duration(sid, ssf_df):
    clock_start, clock_duration = ssf_start_duration(sid, ssf_df)
    normalized_ssf_df = ssf_df.drop(['ssf', 'clock_start', 'next_clock_start', 'hashid_clock'], axis=1)
    last_row_df = normalized_ssf_df[-1:].copy()
    last_row_df['clock'] = clock_duration
    end = last_row_df['clock'] + clock_start
    start = end - clock_duration

    for col, frame_calc in (
            ('vbi_frame', lambda x: calc_vbi_frame(sid, x)),
            ('pr_frame', lambda x: x.floordiv(last_row_df['rate']).astype(pd.Int64Dtype()))):
        last_row_df[col] = frame_calc(end) - frame_calc(start)

    last_row_df['pr_frame'].where(
        last_row_df['pr_frame'].notna(), last_row_df['vbi_frame'], inplace=True)
    last_row_df = last_row_df.astype(normalized_ssf_df.dtypes.to_dict())
    return pd.concat([normalized_ssf_df, last_row_df], ignore_index=True).reset_index(drop=True)


def normalize_ssf(sid, hashid_clock, hashid_noclock, ssf_df, remap_ssf_dfs, ssf_noclock_dfs, ssf_dfs, ssf_count):
    hashid = hash((hashid_clock, hashid_noclock))

    if hashid not in ssf_dfs:
        if hashid in remap_ssf_dfs:
            remapped_hashid = remap_ssf_dfs[hashid]
            hashid = remapped_hashid
        else:
            last_vbi_frame = ssf_df['vbi_frame'].iat[-1]
            remap_hashid_noclock = (last_vbi_frame, hashid_noclock)
            remapped_hashid = ssf_noclock_dfs.get(remap_hashid_noclock, None)
            if remapped_hashid is not None and jittermatch_df(ssf_dfs[remapped_hashid][:-1], ssf_df, 'clock', 1024):
                remap_ssf_dfs[hashid] = remapped_hashid
                hashid = remapped_hashid
            else:
                ssf_dfs[hashid] = pad_ssf_duration(sid, ssf_df)
                ssf_noclock_dfs[remap_hashid_noclock] = hashid

    ssf_count[hashid] += 1
    return hashid


def state2ssfs(sid, df):
    ssf_log = []
    ssf_dfs = {}
    ssf_count = defaultdict(int)
    remap_ssf_dfs = {}
    ssf_noclock_dfs = {}

    for v, v_df in split_vdf(sid, df):
        ssfs = v_df['ssf'].nunique()
        logging.debug('splitting %u SSFs for voice %u', ssfs, v)
        for hashid_noclock, hashid_noclock_df in v_df.groupby(['hashid_noclock'], sort=False):
            for _, ssf_df in hashid_noclock_df.groupby(['ssf'], sort=False):
                hashid_clock = ssf_df['hashid_clock'].iat[0]
                hashid = normalize_ssf(sid, hashid_clock, hashid_noclock, ssf_df, remap_ssf_dfs, ssf_noclock_dfs, ssf_dfs, ssf_count)
                ssf_log.append({'clock': ssf_df['clock_start'].iat[0], 'hashid': hashid, 'voice': v})

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
