# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import numpy as np
import scipy.io.wavfile


def make_wav_from_reg(sid, writes, wav_file_name, padclock):
    lastevent = 0
    raw_samples = sid.add_samples(padclock)

    for clock, reg, val in writes:
        ts_offset = clock - lastevent
        lastevent = clock
        sid.resid.write_register(reg, val)
        raw_samples.extend(sid.add_samples(ts_offset))

    raw_samples.extend(sid.add_samples(padclock))

    scipy.io.wavfile.write(
        wav_file_name, int(sid.resid.sampling_frequency), np.array(raw_samples, dtype=np.float32) / 2**15)
