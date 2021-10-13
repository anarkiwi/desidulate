# Copyright 2020 Josh Bailey (josh@vandervecken.com)

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

SID_SAMPLE_FREQ = 11025
MAX_UPDATE_CYCLES = 2048


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
def reg2state(sid, snd_log_name, nrows=(10 * 1e6)):

    def compress_writes():
        logging.debug('reading %s', snd_log_name)
        df = pd.read_csv(
            snd_log_name,
            sep=' ',
            names=['clock_offset', 'reg', 'val'],
            dtype={'clock_offset': np.uint64, 'reg': np.uint8, 'val': np.uint8},
            nrows=nrows)
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
        df['clock'] -= df['clock'].min()
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
    logging.debug('%u rows from %s after compression', len(df), snd_log_name)
    return df


def split_vdf(sid, df):
    fltcols = [col for col in df.columns if col.startswith('flt') and not col[-1].isdigit()]

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

    def hash_vdf(vdf):
        uniq = vdf.drop(['clock', 'ssf', 'clock_start', 'frame'], axis=1).drop_duplicates(ignore_index=True)
        uniq['row_hash'] = uniq.apply(hash_tuple, axis=1)
        logging.debug('%u unique voice states', len(uniq))
        merge_cols = list(uniq.columns)
        merge_cols.remove('row_hash')
        vdf = vdf.merge(uniq, how='left', on=merge_cols)
        vdf['hashid_noclock'] = vdf.groupby(['ssf'], sort=False)['row_hash'].transform(hash_tuple).astype(np.int64)
        vdf.drop(['row_hash'], inplace=True, axis=1)
        return vdf

    def coalesce_near_writes(vdf, near, v):
        logging.debug('coalescing near %u register writes to voice %u', near, v)
        vdf = vdf.reset_index()
        drop_cols = ['clock_diff']
        vdf['clock_diff'] = vdf['clock'].astype(np.int64).diff(periods=-1).astype(pd.Int64Dtype())
        coalesce_cond = (vdf['clock_diff'] < 0) & (vdf['clock_diff'] > -near)
        for b2_reg in ('freq1', 'pwduty1', 'freq3', 'fltcoff'):
            i = 0
            b2_shift = '%s_shift' % b2_reg
            drop_cols.append(b2_shift)
            vdf[b2_shift] = vdf[b2_reg].shift(-1)
            while True:
                i += 1
                logging.debug('coalesce %s pass %u for voice %u', b2_reg, i, v)
                vdf.loc[coalesce_cond, [b2_reg]] = vdf[b2_shift]
                vdf[b2_shift] = vdf[b2_reg].shift(-1)
                if len(vdf[(vdf[b2_reg] != vdf[b2_shift]) & coalesce_cond]):
                    continue
                break
        vdf = vdf.drop(drop_cols, axis=1).set_index('clock')
        return vdf

    for v in (1, 2, 3):
        logging.debug('splitting voice %u', v)
        if df['gate%u' % v].max() == 0:
            continue
        cols = v_cols(v)
        v_df = df[cols].copy()
        v_df.columns = renamed_cols(v, cols)
        v_df = set_sid_dtype(v_df)

        v_df = coalesce_near_writes(v_df, 16, v)

        # split on gate on transitions into SSFs
        logging.debug('splitting to SSFs for voice %u', v)
        v_df['diff_gate1'] = v_df['gate1'].astype(np.int8).diff(periods=1).fillna(0).astype(pd.Int8Dtype()).fillna(0)
        v_df['ssf'] = v_df['diff_gate1']
        v_df.loc[v_df['ssf'] != 1, ['ssf']] = 0
        v_df['ssf'] = v_df['ssf'].cumsum().astype(np.uint64)

        # Skip SSFs with sample playback.
        # http://www.ffd2.com/fridge/chacking/c=hacking20.txt
        # http://www.ffd2.com/fridge/chacking/c=hacking21.txt
        # https://codebase64.org/doku.php?id=base:vicious_sid_demo_routine_explained
        # https://bitbucket.org/wothke/websid/src/master/docs/digi-samples.txt
        # for col, diff_limit in (('vol', 1), ('test1', 2)):
        #    before = v_df['ssf'].nunique()
        #    v_df['coldiff'] = v_df.groupby(['ssf'], sort=False)[col].transform(
        #        lambda x: len(x[x.diff() != 0]))
        #    v_df = v_df[v_df['coldiff'].isna() | (v_df['coldiff'] <= diff_limit)]
        #    v_df = v_df.drop(['coldiff'], axis=1)
        #    after = v_df['ssf'].nunique()
        #    logging.debug('discarded %u SSFs with %s modulation for voice %u', before - after, col, v)

        logging.debug('removing redundant state for voice %u', v)
        mod_cols = ['freq3', 'test3', 'sync1', 'ring1']

        # remove non-pulse waveform state, while test1 test
        v_df.loc[(v_df['test1'] == 1) & (v_df['pulse1'] != 1), ['freq1', 'tri1', 'saw1', 'pulse1', 'noise1', 'flt1'] + mod_cols] = pd.NA
        # remove modulator voice state while sync1/ring1 not set
        v_df.loc[~((v_df['sync1'] == 1) | ((v_df['ring1'] == 1) & (v_df['tri1'] == 1))), mod_cols] = pd.NA
        # remove carrier state when waveform 0
        v_df.loc[~((v_df['tri1'] == 1) | (v_df['saw1'] == 1) | (v_df['noise1'] == 1) | (v_df['pulse1'] == 1)), ['freq1', 'flt1'] + mod_cols] = pd.NA
        # remove filter state when no filter.
        v_df.loc[(v_df['flt1'] == 0) | v_df['flt1'].isna(), fltcols] = pd.NA
        # remove pwduty state when no pulse1 set.
        v_df.loc[(v_df['pulse1'] == 0) | v_df['pulse1'].isna(), ['pwduty1']] = pd.NA

        # select ADS from when gate on
        logging.debug('removing redundant ADSR for voice %u', v)
        if v_df['ssf'].max() > 1:
            ads_df = v_df[v_df['diff_gate1'] == 1][['ssf', 'atk1', 'dec1', 'sus1']]
            # select R from when gate off
            r_df = v_df[v_df['diff_gate1'] == -1][['ssf', 'rel1']]
            v_df = v_df.drop(['atk1', 'dec1', 'sus1', 'rel1'], axis=1)
            v_df = v_df.reset_index()
            v_df = v_df.merge(ads_df, on='ssf', right_index=False)
            v_df = v_df.merge(r_df, on='ssf', right_index=False)
            v_df.loc[v_df['diff_gate1'] != 1, ['atk1', 'dec1', 'sus1', 'rel1']] = pd.NA
        else:
            v_df = v_df.reset_index()
        v_df = v_df.drop(['diff_gate1'], axis=1)

        # extract only changes
        logging.debug('extracting only state changes for voice %u (rows before %u)', v, len(v_df))
        v_df = v_df.set_index('clock')
        v_df = squeeze_diffs(v_df, v_df.columns)
        logging.debug('extracted only state changes for voice %u (rows after %u)', v, len(v_df))

        # remove empty SSFs
        logging.debug('removing empty SSFs for voice %u', v)
        for col in ('vol', 'gate1', 'freq1'):
            v_df = v_df[v_df.groupby('ssf', sort=False)[col].transform('max') > 0]

        logging.debug('calculating clock for voice %u', v)
        v_df.reset_index(level=0, inplace=True)
        v_df['clock_start'] = v_df.groupby(['ssf'], sort=False)['clock'].transform('min')
        v_df['clock'] = v_df.groupby(['ssf'], sort=False)['clock'].transform(lambda x: x - x.min())
        v_df['frame'] = v_df['clock'].floordiv(int(sid.clockq))

        # for col in ('freq1', 'pwduty1', 'fltcoff'):
        #     v_df['coldiff'] = v_df[col].diff()
        #     v_df['maxdiff'] = v_df[v_df['coldiff'] > 0].groupby(['ssf'], sort=False)['clock'].transform(lambda x: sum(x.diff() >= MAX_UPDATE_CYCLES))
        #     v_df['mindiff'] = v_df[v_df['coldiff'] > 0].groupby(['ssf'], sort=False)['clock'].transform(lambda x: sum(x.diff() < MAX_UPDATE_CYCLES))
        #     discard_ssfs = set(v_df[v_df['maxdiff'] < v_df['mindiff']]['ssf'].unique())
        #     if discard_ssfs:
        #         v_df = v_df[~v_df['ssf'].isin(discard_ssfs)]
        #     v_df = v_df.drop(['coldiff', 'mindiff', 'maxdiff'], axis=1)
        #     logging.debug('discarded %s high update %s rate (%u cycles max) SSFs for voice %u', len(discard_ssfs), col, MAX_UPDATE_CYCLES, v)

        #before = v_df['ssf'].nunique()
        #v_df = v_df[v_df.groupby('ssf', sort=False)['clock'].transform('max') > (sid.clockq / 2)]
        #after =  v_df['ssf'].nunique()
        #logging.debug('removed %u half frame SSFs for voice %u', before - after, v)

        # calculate row hashes
        logging.debug('calculating row hashes for voice %u', v)
        v_df = hash_vdf(v_df)

        # normalize clock, calculate clock hashes
        logging.debug('calculating clock hashes for voice %u', v)
        v_df['hashid_clock'] = v_df.groupby(['ssf'], sort=False)['clock'].transform(hash_tuple).astype(np.int64)

        yield (v, v_df)


def jittermatch_df(df1, df2, jitter_col, jitter_max):
    df1_col = df1[jitter_col].reset_index(drop=True).astype(pd.Int64Dtype())
    df2_col = df2[jitter_col].reset_index(drop=True).astype(pd.Int64Dtype())
    if len(df1_col) == len(df2_col):
        diff = df1_col - df2_col
        diff_max = diff.abs().max()
        return pd.notna(diff_max) and diff_max < jitter_max
    return False


def normalize_ssf(hashid_clock, hashid_noclock, ssf_df, remap_ssf_dfs, ssf_noclock_dfs, ssf_dfs, ssf_count):
    hashid = hash((hashid_clock, hashid_noclock))

    if hashid not in ssf_dfs:
        if hashid in remap_ssf_dfs:
            remapped_hashid = remap_ssf_dfs[hashid]
            hashid = remapped_hashid
        else:
            last_even_frame = ssf_df['frame'].iat[-1]
            remap_hashid_noclock = (last_even_frame, hashid_noclock)
            remapped_hashid = ssf_noclock_dfs.get(remap_hashid_noclock, None)
            if remapped_hashid is not None and jittermatch_df(ssf_dfs[remapped_hashid], ssf_df, 'clock', 1024):
                remap_ssf_dfs[hashid] = remapped_hashid
                hashid = remapped_hashid
            else:
                ssf_dfs[hashid] = ssf_df.drop(['ssf', 'clock_start', 'hashid_clock', 'hashid_noclock'], axis=1).reset_index(drop=True)
                ssf_noclock_dfs[remap_hashid_noclock] = hashid

    ssf_count[hashid] +=1
    return hashid


def state2ssfs(sid, df):
    ssf_log = []
    ssf_dfs = {}
    ssf_count = defaultdict(int)
    remap_ssf_dfs = {}
    ssf_noclock_dfs = {}

    for v, v_df in split_vdf(sid, df):
        ssfs = v_df['ssf'].max()
        if pd.isna(ssfs):
            continue
        logging.debug('splitting %u SSFs for voice %u', ssfs, v)
        for hashid_noclock, hashid_noclock_df in v_df.groupby(['hashid_noclock'], sort=False):
            for _, ssf_df in hashid_noclock_df.groupby(['ssf'], sort=False):
                hashid_clock = ssf_df['hashid_clock'].iat[0]
                hashid = normalize_ssf(hashid_clock, hashid_noclock, ssf_df, remap_ssf_dfs, ssf_noclock_dfs, ssf_dfs, ssf_count)
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
