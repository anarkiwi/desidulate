# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import numpy as np
import scipy.io.wavfile


def generate_samples(sid, reg_writes, padclock):
    lastevent = 0
    for sample in sid.add_samples(padclock):
        yield sample

    for _, row in reg_writes.iterrows():
        clock_offset = row.clock - lastevent
        lastevent = row.clock
        for sample in sid.add_samples(clock_offset):
            yield sample
        sid.resid.write_register(row.reg, row.val)

    for sample in sid.add_samples(padclock):
        yield sample


def make_wav_from_reg(sid, reg_writes, wav_file_name, padclock):
    scipy.io.wavfile.write(
        wav_file_name,
        int(sid.resid.sampling_frequency),
        np.fromiter(generate_samples(sid, reg_writes, padclock), count=-1, dtype=np.float32) / 2**15)
