# Copyright 2020-2022 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

from collections import defaultdict
import numpy as np
import pandas as pd
from scipy import signal
from scipy.io import wavfile
from scipy.fft import rfft, rfftfreq  # pylint: disable=no-name-in-module
from pyresidfp import ControlBits, ModeVolBits, ResFiltBits, Voice


def psfromsamples(samplerate, samples, highpass=15):
    sos = signal.butter(10, highpass, 'hp', fs=samplerate, output='sos')
    data = signal.sosfilt(sos, samples)
    y = np.abs(rfft(data))
    x = rfftfreq(len(data), 1 / samplerate)
    e = defaultdict(int)
    for f, n in zip(x, y):
        if not n:
            continue
        e[f] = n
    return e


def readwav(wav_file_name):
    return wavfile.read(wav_file_name)


def psfromwav(wav_file_name):
    samplerate, data = readwav(wav_file_name)
    return psfromsamples(samplerate, data)


def mostf(wav_file_name, threshold=0.65):
    e = psfromwav(wav_file_name)
    s = sum(e.values())
    if not s:
        return 0
    t = 0
    for f, n in sorted(e.items()):
        t += (n / s)
        if t >= threshold:
            return f
    return f


def _loudest(e):
    for f, _ in sorted(e.items(), key=lambda x: x[1], reverse=True):
        return int(f)
    return 0


def loudestf(wav_file_name):
    e = psfromwav(wav_file_name)
    return _loudest(e)


def samples_loudestf(data, sample_rate):
    e = psfromsamples(sample_rate, data)
    return _loudest(e)


def state2samples(orig_df, sid, skiptest=False, maxclock=None):

    def nib2byte(hi, lo):
        return (hi << 4) + lo

    def control(gate, sync, ring, test, tri, saw, pulse, noise):
        return (
            (ControlBits.GATE.value * gate) |
            (ControlBits.SYNC.value * sync) |
            (ControlBits.RING_MOD.value * ring) |
            (ControlBits.TEST.value * test) |
            (ControlBits.TRIANGLE.value * tri) |
            (ControlBits.SAWTOOTH.value * saw) |
            (ControlBits.PULSE.value * pulse) |
            (ControlBits.NOISE.value * noise))

    def control1(row):
        sid.resid.control(
            Voice.ONE, control(
                row.gate1, row.sync1, row.ring1, row.test1, row.tri1, row.saw1, row.pulse1, row.noise1))

    def control2(row):
        sid.resid.control(
            Voice.TWO, control(
                row.gate2, row.sync2, row.ring2, row.test2, row.tri2, row.saw2, row.pulse2, row.noise2))

    def control3(row):
        sid.resid.control(
            Voice.THREE, control(
                row.gate3, row.sync3, row.ring3, row.test3, row.tri3, row.saw3, row.pulse3, row.noise3))

    def flt(row):
        sid.resid.Filter_Res_Filt = (
            (ResFiltBits.Filt1.value * row.flt1) |
            (ResFiltBits.Filt2.value * row.flt2) |
            (ResFiltBits.Filt3.value * row.flt3) |
            (ResFiltBits.FiltEX.value * row.fltext)) + (row.fltres << 4)

    def main(row):
        sid.resid.Filter_Mode_Vol = (
            (ModeVolBits.LP.value * row.fltlo) |
            (ModeVolBits.BP.value * row.fltband) |
            (ModeVolBits.HP.value * row.flthi) |
            (ModeVolBits.THREE_OFF.value * row.mute3)) + row.vol

    funcs = {
        'atk1': lambda row: sid.resid.attack_decay(Voice.ONE, nib2byte(row.atk1, row.dec1)),
        'atk2': lambda row: sid.resid.attack_decay(Voice.TWO, nib2byte(row.atk2, row.dec2)),
        'atk3': lambda row: sid.resid.attack_decay(Voice.THREE, nib2byte(row.atk3, row.dec3)),
        'dec1': lambda row: sid.resid.attack_decay(Voice.ONE, nib2byte(row.atk1, row.dec1)),
        'dec2': lambda row: sid.resid.attack_decay(Voice.TWO, nib2byte(row.atk2, row.dec2)),
        'dec3': lambda row: sid.resid.attack_decay(Voice.THREE, nib2byte(row.atk3, row.dec3)),
        'flt1': flt,
        'flt2': flt,
        'flt3': flt,
        'fltband': main,
        'fltcoff': lambda row: sid.resid.filter_cutoff(row.fltcoff),
        'flthi': main,
        'fltlo': main,
        'fltres': flt,
        'fltext': flt,
        'freq1': lambda row: sid.resid.oscillator(Voice.ONE, row.freq1),
        'freq2': lambda row: sid.resid.oscillator(Voice.TWO, row.freq2),
        'freq3': lambda row: sid.resid.oscillator(Voice.THREE, row.freq3),
        'gate1': control1,
        'gate2': control2,
        'gate3': control3,
        'mute3': main,
        'noise1': control1,
        'noise2': control2,
        'noise3': control3,
        'pulse1': control1,
        'pulse2': control2,
        'pulse3': control3,
        'pwduty1': lambda row: sid.resid.pulse_width(Voice.ONE, row.pwduty1),
        'pwduty2': lambda row: sid.resid.pulse_width(Voice.TWO, row.pwduty2),
        'pwduty3': lambda row: sid.resid.pulse_width(Voice.THREE, row.pwduty3),
        'rel1': lambda row: sid.resid.sustain_release(Voice.ONE, nib2byte(row.sus1, row.rel1)),
        'rel2': lambda row: sid.resid.sustain_release(Voice.TWO, nib2byte(row.sus2, row.rel2)),
        'rel3': lambda row: sid.resid.sustain_release(Voice.THREE, nib2byte(row.sus3, row.rel3)),
        'ring1': control1,
        'ring2': control2,
        'ring3': control3,
        'saw1': control1,
        'saw2': control2,
        'saw3': control3,
        'sus1': lambda row: sid.resid.sustain_release(Voice.ONE, nib2byte(row.sus1, row.rel1)),
        'sus2': lambda row: sid.resid.sustain_release(Voice.TWO, nib2byte(row.sus2, row.rel2)),
        'sus3': lambda row: sid.resid.sustain_release(Voice.THREE, nib2byte(row.sus3, row.rel3)),
        'sync1': control1,
        'sync2': control2,
        'sync3': control3,
        'test1': control1,
        'test2': control2,
        'test3': control3,
        'tri1': control1,
        'tri2': control2,
        'tri3': control3,
        'vol': main,
    }

    sid.resid.reset()
    sid.add_samples(sid.clock_freq)
    df = orig_df.copy()
    for col in funcs:
        if col not in df:
            df[col] = 0
    df = df.fillna(0).astype(pd.Int64Dtype())
    df['clock'] = df.index
    if maxclock is not None:
        df = df[df['clock'] <= maxclock]

    raw_samples = []

    diff_cols = {}
    diffs = ['diff_clock']
    cols = ['clock']
    for col in df.columns:
        diff_col = 'diff_%s' % col
        if col in funcs:
            diff_cols[diff_col] = col
            diffs.append(diff_col)
            cols.append(col)
    diff_df = df[cols].diff().astype(pd.Int32Dtype())
    diff_df.columns = diffs
    diff_df['diff_funcs'] = np.empty((len(df), 0)).tolist()
    df = df.join(diff_df)
    drop_diff_cols = []
    for diff_col, col in diff_cols.items():
        diff_max = df[diff_col].abs().max()
        if pd.isna(diff_max) or diff_max == 0:
            drop_diff_cols.append(diff_col)
    for diff_col in drop_diff_cols:
        del diff_cols[diff_col]

    for diff_col, col in diff_cols.items():
        mask = (df[diff_col] != 0)
        func = funcs[col]
        df.loc[mask, 'diff_funcs'] = df.loc[mask, 'diff_funcs'].apply(lambda row: row + [func])

    diffs.remove('diff_clock')
    df['diff_clock'] = df['diff_clock'].fillna(0)
    dtypes = {'diff_clock': np.uint32, 'diff_funcs': object}
    for col in funcs:
        if col.startswith('freq') or col.startswith('pwduty') or col == 'fltcoff':
            dtypes[col] = np.uint16
            continue
        dtypes[col] = np.uint8
    df = df.drop(diffs, axis=1).astype(dtypes)

    row = df.iloc[0]
    for f in funcs.values():
        f(row)
    in_test = row.test1
    df = df[1:]

    if skiptest and in_test and not df.empty:
        for i, row in enumerate(df.itertuples(), start=1):
            sid.add_samples(row.diff_clock)
            for func in row.diff_funcs:
                func(row)
            if not row.test1:
                break
        df = df[i:]

    for row in df.itertuples():
        raw_samples.extend(sid.add_samples(row.diff_clock))
        for func in row.diff_funcs:
            func(row)

    if not raw_samples:
        raw_samples.extend(sid.add_samples(sid.clockq))

    return np.array(raw_samples, dtype=np.int16)


def write_wav(wav_file_name, sid, raw_samples):
    wavfile.write(wav_file_name, int(sid.resid.sampling_frequency), raw_samples)


def df2wav(df, sid, wav_file_name, skiptest=False):
    write_wav(wav_file_name, sid, state2samples(df, sid, skiptest=skiptest))
