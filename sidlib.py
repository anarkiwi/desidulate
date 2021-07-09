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

# SSFs with vol modulation > than this, rejected
SKIP_VOL_MOD_HZ = 1000
# SSFs with pwduty modulation > than this, rejected
SKIP_PWDUTY_MOD_HZ = 256


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


def squeeze_diffs(df, diff_cols):
    return df.loc[(df[diff_cols].shift() != df[diff_cols]).any(axis=1)]


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

    def __init__(self, pal, model=ChipModel.MOS8580, sampling_frequency=22050):
        if pal:
            self.clock_freq = SoundInterfaceDevice.PAL_CLOCK_FREQUENCY
            self.int_freq = 50.0
        else:
            self.clock_freq = SoundInterfaceDevice.NTSC_CLOCK_FREQUENCY
            self.int_freq = 60.0
        self.freq_scaler = self.clock_freq / 16777216
        self.resid = SoundInterfaceDevice(
            model=model, clock_frequency=self.clock_freq,
            sampling_frequency=sampling_frequency)
        self.clockq = int(round(self.clock_freq / self.int_freq))
        self.attack_clock = {
            k: int(v / 1e3 * self.clock_freq) for k, v in self.ATTACK_MS.items()}
        self.decay_release_clock = {
            k: int(v / 1e3 * self.clock_freq) for k, v in self.DECAY_RELEASE_MS.items()}

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


def get_sid(pal):
    return SidWrap(pal)


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
            reg_df = squeeze_diffs(reg_df, reg_cols)
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
        if v_df[col].max() != 1:
            continue
        diff_gate_on = 'diff_on_%s' % col
        v_df[diff_gate_on] = v_df[col].astype(np.int8).diff(periods=1).fillna(0).astype(pd.Int8Dtype())
        v_df['ssf'] = v_df[diff_gate_on]
        v_df.loc[v_df['ssf'] != 1, ['ssf']] = 0
        v_df['ssf'] = v_df['ssf'].cumsum().astype(np.uint64)
        v_df.loc[(v_df['test1'] == 1) & (v_df['pulse1'] != 1), ['freq1', 'sync1', 'ring1', 'tri1', 'saw1', 'pulse1', 'noise1', 'pwduty1', 'freq3', 'test3']] = pd.NA
        v_df.loc[~((v_df['sync1'] == 1) | ((v_df['ring1'] == 1) & (v_df['tri1'] == 1))), ['freq3', 'test3']] = pd.NA
        v_df.loc[v_df['gate1'] == 0, ['atk1', 'dec1', 'sus1', 'rel1']] = pd.NA
        v_df.loc[(v_df['gate1'] == 0) & (v_df['tri1'] != 1) & (v_df['saw1'] != 1) & (v_df['noise1'] != 1) & (v_df['pulse1'] != 1), ['freq1']] = pd.NA
        v_df.loc[v_df['flt1'] != 1, fltcols] = pd.NA
        v_df.loc[v_df['pulse1'] != 1, ['pwduty1']] = pd.NA
        v_df = v_df.drop([diff_gate_on], axis=1)
        diff_cols = list(v_df.columns)
        diff_cols.remove('frame')
        v_df = squeeze_diffs(v_df, diff_cols)
        v_df = v_df[v_df.groupby('ssf', sort=False)['vol'].transform('max') > 0]
        v_df = v_df[v_df.groupby('ssf', sort=False)['test1'].transform('min') < 1]
        for ncol in ['freq1', 'pwduty1', 'vol']:
            v_df['%snunique' % ncol] = v_df.groupby(['ssf'], sort=False)[ncol].transform('nunique').astype(np.uint64)
        control_ignore_diff_cols = ['freq1', 'freq3', 'pwduty1', 'fltcoff']
        for col in control_ignore_diff_cols:
            diff_cols.remove(col)
        v_control_df = v_df.drop(control_ignore_diff_cols, axis=1).copy()
        v_control_df = squeeze_diffs(v_control_df, diff_cols)
        v_df['ssf_size'] = v_df.groupby(['ssf'], sort=False)['ssf'].transform('size').astype(np.uint64)
        v_control_df['ssf_size'] = v_control_df.groupby(['ssf'], sort=False)['ssf'].transform('size').astype(np.uint64)
        yield (v, v_df, v_control_df)


def jittermatch_df(df1, df2, jitter_col, jitter_max):
    if len(df1) != len(df2):
        return False
    df1_col = df1[jitter_col].astype(pd.Int64Dtype())
    df2_col = df2[jitter_col].astype(pd.Int64Dtype())
    diff = df1_col - df2_col
    diff_max = diff.abs().max()
    return pd.notna(diff_max) and diff_max < jitter_max


def mask_not_pulse(ssf_df):
    return ssf_df['tri1'].max() == 0 and ssf_df['saw1'].max() == 0 and ssf_df['noise1'].max() == 0


def fast_clock_diff(ssf_df, fast_mod_cycles):
    diffs = ssf_df['clock'].diff()
    if diffs.min() > fast_mod_cycles:
        return False
    if diffs.mean() < fast_mod_cycles:
        return True
    return diffs.quantile(0.95).mean() < fast_mod_cycles


def skip_ssf(ssf_df, vol_mod_cycles, pwduty_mod_cycles):
    # Skip SSFs with sample playback.
    if len(ssf_df) > 2 and ssf_df['frame'].nunique() > 3:
        # https://codebase64.org/doku.php?id=base:vicious_sid_demo_routine_explained
        # http://www.ffd2.com/fridge/chacking/c=hacking21.txt
        # http://www.ffd2.com/fridge/chacking/c=hacking20.txt
        # Skip SSFs with high rate volume changes.
        if ssf_df['volnunique'].max() > 2:
            vol_ssf_df = squeeze_diffs(ssf_df[['clock', 'vol']], ['vol'])
            if fast_clock_diff(vol_ssf_df, vol_mod_cycles):
                return True
        # Skip SSFs with high PW duty cycle changes
        elif mask_not_pulse(ssf_df) and ssf_df['pwduty1nunique'].max() > 1:
            pwduty_clock_df = squeeze_diffs(ssf_df[['clock', 'pwduty1']], ['pwduty1'])
            if fast_clock_diff(pwduty_clock_df, pwduty_mod_cycles):
                return True
    return False


def hash_series(s):
    n = s.to_numpy()
    return hash(n.tobytes())


def normalize_ssf(ssf_df, remap_ssf_dfs, ssf_noclock_dfs, ssf_dfs, ssf_count):
    hashid_noclock = hash_series(ssf_df['row_hash'])
    hashid_clock = hash_series(ssf_df['clock'])
    hashid = hash((hashid_clock, hashid_noclock))

    if hashid not in ssf_dfs:
        if hashid in remap_ssf_dfs:
            remapped_hashid = remap_ssf_dfs[hashid]
            hashid = remapped_hashid
        else:
            ssf_df['frame'] -= ssf_df['frame'].min()
            even_frame = int(ssf_df['frame'].max() / 2) * 2
            hashid_noclock = (hashid_noclock, even_frame)
            remapped_hashid = ssf_noclock_dfs.get(hashid_noclock, None)
            if remapped_hashid is not None and jittermatch_df(ssf_dfs[remapped_hashid], ssf_df, 'clock', 1024):
                remap_ssf_dfs[hashid] = remapped_hashid
                hashid = remapped_hashid
            else:
                ssf_dfs[hashid] = ssf_df.drop(['row_hash'], axis=1)
                ssf_noclock_dfs[hashid_noclock] = hashid

    ssf_count[hashid] +=1
    return hashid


def split_ssf(sid, df):
    ssf_log = []
    ssf_dfs = {}
    ssf_count = defaultdict(int)
    control_ssf_dfs = {}
    control_ssf_count = defaultdict(int)
    remap_ssf_dfs = {}
    ssf_noclock_dfs = {}
    skip_hashids = {}
    vol_mod_cycles = int(sid.clock_freq / SKIP_VOL_MOD_HZ)
    pwduty_mod_cycles = int(sid.clock_freq / SKIP_PWDUTY_MOD_HZ)

    for v, v_df, v_control_df in split_vdf(df):
        skip_ssfs = set()
        v_df['row_hash'] = v_df.drop(['frame', 'ssf', 'ssf_size'], axis=1).apply(lambda r: hash(tuple(r)), axis=1)
        v_control_df['row_hash'] = v_control_df.drop(['frame', 'ssf', 'ssf_size'], axis=1).apply(lambda r: hash(tuple(r)), axis=1)

        for _, size_ssf_df in v_df.groupby(['ssf_size']):
            for ssf, group_ssf_df in size_ssf_df.drop(['ssf_size'], axis=1).groupby(['ssf']):
                ssf_df = group_ssf_df.drop(['ssf'], axis=1).copy()
                ssf_df.reset_index(level=0, inplace=True)
                orig_clock = ssf_df['clock'].min()
                ssf_df['clock'] -= ssf_df['clock'].min()
                hashid = normalize_ssf(ssf_df, remap_ssf_dfs, ssf_noclock_dfs, ssf_dfs, ssf_count)
                if hashid:
                    if hashid not in skip_hashids:
                        skip_hashids[hashid] = skip_ssf(ssf_df, vol_mod_cycles, pwduty_mod_cycles)
                    if skip_hashids[hashid]:
                        skip_ssfs.add(ssf)
                    else:
                        ssf_log.append({'clock': orig_clock, 'hashid': hashid, 'voice': v})
        for _, size_ssf_df in v_control_df.groupby(['ssf_size']):
            for ssf, group_ssf_df in size_ssf_df.drop(['ssf_size'], axis=1).groupby(['ssf']):
                if ssf in skip_ssfs:
                    continue
                ssf_df = group_ssf_df.drop(['ssf'], axis=1).copy()
                ssf_df.reset_index(level=0, inplace=True)
                ssf_df['clock'] -= ssf_df['clock'].min()
                normalize_ssf(ssf_df, remap_ssf_dfs, ssf_noclock_dfs, control_ssf_dfs, control_ssf_count)

    skip_ssf_dfs = {}
    skip_ssf_count = {}
    skip_hashids = {hashid for hashid, skip in skip_hashids.items() if skip}
    for hashid in skip_hashids:
        skip_ssf_dfs[hashid] = ssf_dfs[hashid]
        skip_ssf_count[hashid] = ssf_count[hashid]
        del ssf_dfs[hashid]
        del ssf_count[hashid]

    for x, y in ((ssf_dfs, ssf_count),
                 (control_ssf_dfs, control_ssf_count),
                 (skip_ssf_dfs, skip_ssf_count)):
        for hashid, count in y.items():
            x[hashid]['count'] = count
            x[hashid]['hashid'] = hashid

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
    control_ssf_df = concat_dfs(control_ssf_dfs, control_ssf_count)
    skip_ssf_df = concat_dfs(skip_ssf_dfs, skip_ssf_count)
    return ssf_log_df, ssf_df, control_ssf_df, skip_ssf_df


def state2ssfs(sid, df):
    ssf_log_df, ssf_df, control_ssf_df, skip_ssf_df = split_ssf(sid, df)
    return ssf_log_df, ssf_df, control_ssf_df, skip_ssf_df
