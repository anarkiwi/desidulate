# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import numpy as np
import pandas as pd
import scipy.io.wavfile
from sox.transform import Transformer
from pyresidfp import ControlBits, ModeVolBits, ResFiltBits, Voice


def mostf(self, threshold=0.65):
    transf = Transformer()
    ps = transf.power_spectrum(self.wav_file_name)
    e = {f: n for f, n in ps if n}
    s = sum(e.values())
    if not s:
        return 0
    t = 0
    for f, n in sorted(e.items()):
        t += (n / s)
        if t >= threshold:
            return f
    return f


def state2samples(orig_df, sid):

    def nib2byte(hi, lo):
        return (int(hi) << 4) + int(lo)

    def control(gate, sync, ring, test, tri, saw, pulse, noise):
        return int(
            int(ControlBits.GATE.value * gate) |
            int(ControlBits.SYNC.value * sync) |
            int(ControlBits.RING_MOD.value * ring) |
            int(ControlBits.TEST.value * test) |
            int(ControlBits.TRIANGLE.value * tri) |
            int(ControlBits.SAWTOOTH.value * saw) |
            int(ControlBits.PULSE.value * pulse) |
            int(ControlBits.NOISE.value * noise))

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
            int(ResFiltBits.Filt1.value * row.flt1) |
            int(ResFiltBits.Filt2.value * row.flt2) |
            int(ResFiltBits.Filt3.value * row.flt3) |
            int(ResFiltBits.FiltEX.value * row.fltext)) + (int(row.fltres) << 4)

    def main(row):
        sid.resid.Filter_Mode_Vol = (
            int(ModeVolBits.LP.value * row.fltlo) |
            int(ModeVolBits.BP.value * row.fltband) |
            int(ModeVolBits.HP.value * row.flthi) |
            int(ModeVolBits.THREE_OFF.value * row.mute3)) + int(row.vol)

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
        'fltcoff': lambda row: sid.resid.filter_cutoff(int(row.fltcoff)),
        'flthi': main,
        'fltlo': main,
        'fltres': flt,
        'fltext': flt,
        'freq1': lambda row: sid.resid.oscillator(Voice.ONE, int(row.freq1)),
        'freq2': lambda row: sid.resid.oscillator(Voice.TWO, int(row.freq2)),
        'freq3': lambda row: sid.resid.oscillator(Voice.THREE, int(row.freq3)),
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
        'pwduty1': lambda row: sid.resid.pulse_width(Voice.ONE, int(row.pwduty1)),
        'pwduty2': lambda row: sid.resid.pulse_width(Voice.TWO, int(row.pwduty2)),
        'pwduty3': lambda row: sid.resid.pulse_width(Voice.THREE, int(row.pwduty3)),
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
    raw_samples = []

    row = df.iloc[0]
    for k, f in funcs.items():
        f(row)

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
    df = df.join(diff_df)

    for row in df[1:].itertuples():
        raw_samples.extend(sid.add_samples(row.diff_clock))
        diffs_funcs = [funcs[v] for k, v in diff_cols.items() if getattr(row, k) != 0]
        for func in diffs_funcs:
            func(row)

    return np.array(raw_samples, dtype=np.int16)


def write_wav(wav_file_name, sid, raw_samples):
    scipy.io.wavfile.write(wav_file_name, int(sid.resid.sampling_frequency), raw_samples)


def df2wav(df, sid, wav_file_name):
    write_wav(wav_file_name, sid, state2samples(df, sid))
