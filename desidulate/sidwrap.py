# Copyright 2020-2022 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABL E FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import logging
from datetime import timedelta
from pyresidfp import SoundInterfaceDevice
from pyresidfp.sound_interface_device import ChipModel

SID_SAMPLE_FREQ = 11025


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

    def __init__(self, pal, cia, model, sampling_frequency):
        # https://codebase64.org/doku.php?id=magazines:chacking17
        # https://codebase64.org/doku.php?id=base:making_stable_raster_routines
        if pal:
            self.clock_freq = SoundInterfaceDevice.PAL_CLOCK_FREQUENCY
            self.raster_lines = 312
            self.cycles_per_line = 63
        else:
            self.clock_freq = SoundInterfaceDevice.NTSC_CLOCK_FREQUENCY
            self.raster_lines = 263
            self.cycles_per_line = 65
        self.freq_scaler = self.clock_freq / 16777216
        self.video_clockq = self.raster_lines * self.cycles_per_line

        if cia:
            self.clockq = cia
        else:
            self.clockq = self.video_clockq
        self.int_freq = self.clock_freq / self.clockq
        self.vid_int_freq = self.clock_freq / self.video_clockq

        us_per_sample = 1e6 / sampling_frequency
        us_per_cycle = 1e6 / self.clock_freq
        self.one_sample_cycles = int(us_per_sample / us_per_cycle)
        logging.info('one sample lasts %u cycles (one sample lasts %fus)', self.one_sample_cycles, us_per_sample)

        logging.info('using PR frequency %f Hz (%u cycles)', self.int_freq, self.clockq)
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


def get_sid(pal, cia, model=ChipModel.MOS8580, sampling_frequency=SID_SAMPLE_FREQ):
    return SidWrap(pal, cia, model, sampling_frequency)
