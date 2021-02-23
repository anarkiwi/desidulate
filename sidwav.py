# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

from datetime import timedelta
import numpy as np
import scipy.io.wavfile
# https://github.com/packet23/pyresidfp
from pyresidfp import SoundInterfaceDevice
from pyresidfp.sound_interface_device import ChipModel


def get_sid(model=ChipModel.MOS8580, pal=True):
    if pal:
        freq = SoundInterfaceDevice.PAL_CLOCK_FREQUENCY
    else:
        freq = SoundInterfaceDevice.NTSC_CLOCK_FREQUENCY
    return SoundInterfaceDevice(model=model, clock_frequency=freq)


def make_wav_from_reg(sid, writes, wav_file_name, padclock):
    lastevent = 0
    raw_samples = []

    def add_samples(offset):
        timeoffset_seconds = offset / sid.clock_freq
        raw_samples.extend(sid.clock(timedelta(seconds=timeoffset_seconds)))

    add_samples(padclock)

    for clock, reg, val in writes:
        ts_offset = clock - lastevent
        lastevent = clock
        sid.write_register(reg, val)
        add_samples(ts_offset)

    add_samples(padclock)

    scipy.io.wavfile.write(
        wav_file_name, int(sid.sampling_freq), np.array(raw_samples, dtype=np.float32) / 2**15)
