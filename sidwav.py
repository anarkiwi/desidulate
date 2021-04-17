# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

from collections import defaultdict
import numpy as np
import pandas as pd
import scipy.io.wavfile
from pyresidfp import Voice, ControlBits, ModeVolBits


def control_reg(voicenum, voicestate):
    return ControlBits(
        (ControlBits.GATE.value * voicestate['gate%u' % voicenum]) |
        (ControlBits.SYNC.value * voicestate['sync%u' % voicenum]) |
        (ControlBits.RING_MOD.value * voicestate['ring%u' % voicenum]) |
        (ControlBits.TEST.value * voicestate['test%u' % voicenum]) |
        (ControlBits.TRIANGLE.value * voicestate['tri%u' % voicenum]) |
        (ControlBits.SAWTOOTH.value * voicestate['saw%u' % voicenum]) |
        (ControlBits.PULSE.value * voicestate['pulse%u' % voicenum]) |
        (ControlBits.NOISE.value * voicestate['noise%u' % voicenum]))


def filter_coff_reg(voicestate):
    return voicestate['flt_coff'] & (2 ** 11 - 1)


def filtermodevol_reg(voicestate):
    return ModeVolBits(
        (ModeVolBits.BP.value * voicestate['flt_band']) |
        (ModeVolBits.HP.value * voicestate['flt_high']) |
        (ModeVolBits.LP.value * voicestate['flt_low'])).value + voicestate['vol']


def nib2byte(hi, lo):
    return (hi << 4) + lo


def filterres_reg(voicenum, voicestate):
    return nib2byte(voicestate['flt_res'], voicestate['flt%u' % voicenum])


def attack_decay(voicenum, voicestate):
    return nib2byte(voicestate['atk%u' % voicenum], voicestate['dec%u' % voicenum])


def sustain_release(voicenum, voicestate):
    return nib2byte(voicestate['sus%u' % voicenum], voicestate['rel%u' % voicenum])


def freq(voicenum, voicestate):
    return voicestate['freq%u' % voicenum]


def pw_duty(voicenum, voicestate):
    return voicestate['pw_duty%u' % voicenum]


def df2samples(df, sid):
    raw_samples = []
    lastclock = 0
    sidstate = defaultdict(int)
    sid.resid.reset()
    sid.add_samples(sid.clock_freq)

    for df_row in df.to_dict(orient='records'):
        row = {k: int(v) for k, v in df_row.items() if not pd.isnull(v)}
        ts_offset = row['clock'] - lastclock
        raw_samples.extend(sid.add_samples(ts_offset))
        for f in set(row.keys()) - {'hashid', 'count', 'clock'}:
            sidstate[f] += row[f]

        sid.resid.filter_cutoff(filter_coff_reg(sidstate))
        sid.resid.Filter_Mode_Vol = filtermodevol_reg(sidstate)

        for voice in (Voice.ONE, Voice.THREE):
            voicenum = voice.value + 1
            sid.resid.Filter_Res_Filt = filterres_reg(voicenum, sidstate)
            sid.resid.oscillator(voice, freq(voicenum, sidstate))
            sid.resid.pulse_width(voice, pw_duty(voicenum, sidstate))
            sid.resid.attack_decay(voice, attack_decay(voicenum, sidstate))
            sid.resid.sustain_release(voice, sustain_release(voicenum, sidstate))
            sid.resid.control(voice, control_reg(voicenum, sidstate))

        lastclock = row['clock']

    return raw_samples


def df2wav(df, sid, wavfile):
    raw_samples = df2samples(df, sid)
    if raw_samples:
        write_wav(wavfile, sid, np.array(raw_samples, dtype=np.int16))


def generate_samples(sid, reg_writes, padclock, maxsilentclocks):
    for sample in sid.add_samples(padclock):
        yield sample

    lastloud = 0

    for row in reg_writes.itertuples():
        for sample in sid.add_samples(row.clock_offset):
            if abs(sample) > 256:
                lastloud = row.clock
            yield sample
        if row.clock - lastloud > maxsilentclocks:
            break
        sid.resid.write_register(row.reg, row.val)

    for sample in sid.add_samples(padclock):
        yield sample


def write_wav(wav_file_name, sid, raw_samples):
    scipy.io.wavfile.write(wav_file_name, int(sid.resid.sampling_frequency), raw_samples)


def make_wav_from_reg(sid, reg_writes, wav_file_name, padclock, maxsilentclocks):
    write_wav(wav_file_name, sid, np.fromiter(generate_samples(sid, reg_writes, padclock, maxsilentclocks), count=-1, dtype=np.int16))
