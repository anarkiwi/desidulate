# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABL E FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from collections import defaultdict
from datetime import timedelta
import pandas as pd
import numpy as np
from pyresidfp import SoundInterfaceDevice
from pyresidfp.sound_interface_device import ChipModel


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


class SidWrap:

    release_ms = {
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

    def __init__(self, pal, model=ChipModel.MOS8580, sampling_frequency=22050):
        if pal:
            self.clock_freq = SoundInterfaceDevice.PAL_CLOCK_FREQUENCY
            self.int_freq = 50.0
        else:
            self.clock_freq = SoundInterfaceDevice.NTSC_CLOCK_FREQUENCY
            self.int_freq = 60.0
        self.resid = SoundInterfaceDevice(
            model=model, clock_frequency=self.clock_freq,
            sampling_frequency=sampling_frequency)
        self.clockq = int(round(self.clock_freq / self.int_freq))
        self.release_clock = {
            k: int(v / 1e3 * self.clock_freq) for k, v in self.release_ms.items()}

    def clock_to_s(self, clock):
        return clock / self.clock_freq

    def clock_to_qn(self, clock, bpm):
        return self.clock_to_s(clock) * bpm / 60

    def clock_to_ticks(self, clock, bpm, tpqn):
        return self.clock_to_qn(clock, bpm) * tpqn

    def real_sid_freq(self, freq_reg):
        # http://www.sidmusic.org/sid/sidtech2.html
        return freq_reg * self.clock_freq / 16777216

    def add_samples(self, offset):
        timeoffset_seconds = offset / self.clock_freq
        return self.resid.clock(timedelta(seconds=timeoffset_seconds))


def get_sid(pal):
    return SidWrap(pal)


def hash_df(df):
    rows_hash = pd.Series((hash(r) for r in df.itertuples(index=False, name=None)))
    return hash(tuple(rows_hash))


# Read a VICE "-sounddev dump" register dump (emulator or vsid)
def reg2state(sid, snd_log_name, nrows=(10 * 1e6)):

    def compress_writes():
        df = pd.read_csv(
            snd_log_name,
            sep=' ',
            names=['clock_offset', 'reg', 'val'],
            dtype={'clock_offset': np.uint64, 'reg': np.uint8, 'val': np.uint8},
            nrows=nrows)
        df['clock'] = df['clock_offset'].cumsum()
        df['frame'] = df['clock'].floordiv(int(sid.clockq))
        assert df['reg'].min() >= 0
        df = df[['clock', 'frame', 'reg', 'val']]
        # remove consecutive repeated register writes
        reg_dfs = []
        reg_cols = ['reg', 'val']
        for reg in sorted(df.reg.unique()):
            reg_df = df[df['reg'] == reg]
            reg_df = reg_df.loc[(reg_df[reg_cols].shift() != reg_df[reg_cols]).any(axis=1)]
            reg_dfs.append(reg_df)
        df = pd.concat(reg_dfs)
        df['clock'] -= df['clock'].min()
        df['frame'] -= df['frame'].min()
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
        for b, name in enumerate(
                ['gate', 'sync', 'ring', 'test', 'tri', 'saw', 'pulse', 'noise']):
            set_bit(reg_df, control, b, '%s%u' % (name, v))
        set_hi_lo_nib(reg_df, reg_df[vb + 5], 'atk%u' % v, 'dec%u' % v)
        set_hi_lo_nib(reg_df, reg_df[vb + 6], 'sus%u' % v, 'rel%u' % v)

    def set_common(reg_df):
        main = reg_df[24]
        reg_df['vol'] = main & 15
        set_bits(reg_df, main, ['fltlo', 'fltband', 'flthi', 'mute3'], start=4)
        filter_route = reg_df[23]
        set_bits(reg_df, filter_route, ['flt1', 'flt2', 'flt3', 'fltext'])
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
        return reg_df.drop(all_regs, axis=1)

    df = compress_writes()
    reg_df = decode_regs(df)
    df = df.drop(['reg', 'val'], axis=1).join(reg_df, on='clock')
    return df


def split_vdf(df):
    fltcols = [col for col in df.columns if col.startswith('flt') and not col[-1].isdigit()]
    v_dfs = {}

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

    for v in (1, 2, 3):
        if df['gate%u' % v].max() == 0:
            continue
        cols = v_cols(v)
        v_df = df[cols].copy()
        v_df.columns = renamed_cols(v, cols)
        v_df = set_sid_dtype(v_df)
        col = 'gate1'
        diff_gate_on = 'diff_on_%s' % col
        v_df[diff_gate_on] = v_df[col].astype(np.int8).diff(periods=1).fillna(0).astype(pd.Int8Dtype())
        v_df['ssf'] = v_df[diff_gate_on]
        v_df.loc[v_df['ssf'] != 1, ['ssf']] = 0
        v_df['ssf'] = v_df['ssf'].cumsum().astype(np.uint64)
        v_df.loc[(v_df['test1'] == 1) & (v_df['pulse1'] != 1), ['freq1', 'sync1', 'ring1', 'tri1', 'saw1', 'pulse1', 'noise1', 'pwduty1', 'freq3', 'test3']] = pd.NA
        v_df.loc[~((v_df['sync1'] == 1) | ((v_df['ring1'] == 1) & (v_df['tri1'] == 1))), ['freq3', 'test3']] = pd.NA
        v_df.loc[v_df['gate1'] == 0, ['atk1', 'dec1', 'sus1', 'rel1']] = pd.NA
        v_df.loc[v_df['flt1'] != 1, fltcols] = pd.NA
        v_df.loc[v_df['pulse1'] != 1, ['pwduty1']] = pd.NA
        v_df = v_df.drop([diff_gate_on], axis=1)
        diff_cols = list(v_df.columns)
        diff_cols.remove('frame')
        v_df = v_df.loc[(v_df[diff_cols].shift() != v_df[diff_cols]).any(axis=1)]
        v_df = v_df[v_df.groupby('ssf', sort=False)['vol'].transform('max') > 0]
        v_df = v_df[v_df.groupby('ssf', sort=False)['test1'].transform('min') < 1]
        v_df['ssf_size'] = v_df.groupby(['ssf'], sort=False)['ssf'].transform('size').astype(np.uint64)
        yield (v, v_df)


def jittermatch_df(df1, df2, jitter_col, jitter_max):
    if len(df1) != len(df2):
        return False
    df1_col = df1[jitter_col].astype(pd.Int64Dtype())
    df2_col = df2[jitter_col].astype(pd.Int64Dtype())
    diff = df1_col - df2_col
    diff_max = diff.abs().max()
    return pd.notna(diff_max) and diff_max < jitter_max


def split_ssf(df):
    ssf_log = []
    ssf_dfs = {}
    ssf_count = defaultdict(int)

    for v, v_df in split_vdf(df):
        for _, size_ssf_df in v_df.groupby(['ssf_size'], sort=False):
            remap_ssf_dfs = {}
            ssf_noclock_dfs = {}
            for _, group_ssf_df in size_ssf_df.drop(['ssf_size'], axis=1).groupby(['ssf'], sort=False):
                ssf_df = group_ssf_df.drop(['ssf'], axis=1).copy()
                ssf_df.reset_index(level=0, inplace=True)
                orig_clock = ssf_df['clock'].min()
                ssf_df['clock'] -= ssf_df['clock'].min()
                ssf_df['frame'] -= ssf_df['frame'].min()
                hashid = hash_df(ssf_df)
                if hashid not in ssf_dfs:
                    if hashid in remap_ssf_dfs:
                        remapped_hashid = remap_ssf_dfs[hashid]
                        hashid = remapped_hashid
                    else:
                        ssf_noclock_df = ssf_df.drop(['clock', 'frame'], axis=1)
                        hashid_noclock = hash_df(ssf_noclock_df)
                        remapped_hashid = ssf_noclock_dfs.get(hashid_noclock, None)
                        if remapped_hashid is not None and jittermatch_df(ssf_dfs[remapped_hashid], ssf_df, 'clock', 1024):
                            remap_ssf_dfs[hashid] = remapped_hashid
                            hashid = remapped_hashid
                        else:
                            ssf_dfs[hashid] = ssf_df
                            ssf_noclock_dfs[hashid_noclock] = hashid

                ssf_count[hashid] += 1
                ssf_log.append({'clock': orig_clock, 'hashid': hashid, 'voice': v})
    return ssf_log, ssf_dfs, ssf_count


def state2ssfs(df, sid):
    ssf_log, ssf_dfs, ssf_count = split_ssf(df)

    for hashid, count in ssf_count.items():
        ssf_dfs[hashid]['count'] = count
        ssf_dfs[hashid]['hashid'] = hashid

    if ssf_log:
        ssf_log_df = pd.DataFrame(
            ssf_log, dtype=pd.Int64Dtype()).set_index('clock').sort_index()
        ssf_df = pd.concat([
            ssf_dfs[hashid] for hashid, count in sorted(ssf_count.items(), key=lambda x: x[1], reverse=True)]).set_index('hashid')
        return ssf_log_df, ssf_df
    return None, None
