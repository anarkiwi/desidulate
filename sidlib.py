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

from sidreg import VOICES, SidRegState, SidRegEvent, frozen_sid_state_factory


class SidWrap:

    def __init__(self, pal, model=ChipModel.MOS8580):
        if pal:
            self.clock_freq = SoundInterfaceDevice.PAL_CLOCK_FREQUENCY
            self.int_freq = 50.0
        else:
            self.clock_freq = SoundInterfaceDevice.NTSC_CLOCK_FREQUENCY
            self.int_freq = 60.0
        self.resid = SoundInterfaceDevice(model=model, clock_frequency=self.clock_freq)
        self.clockq = self.clock_freq / self.int_freq

    def clock_to_s(self, clock):
        return clock / self.clock_freq

    def clock_to_qn(self, clock, bpm):
        return self.clock_to_s(clock) * bpm / 60

    def clock_to_ticks(self, clock, bpm, tpqn):
        return self.clock_to_qn(clock, bpm) * tpqn

    def real_sid_freq(self, freq_reg):
        # http://www.sidmusic.org/sid/sidtech2.html
        return freq_reg * self.clock_freq / 16777216

    def clock_frame(self, clock):
        return round(clock / self.clockq)

    def nearest_frame_clock(self, clock):
        return round(self.clock_frame(clock) * self.clockq)

    def add_samples(self, offset):
        timeoffset_seconds = offset / self.clock_freq
        return self.resid.clock(timedelta(seconds=timeoffset_seconds))


def get_sid(pal):
    return SidWrap(pal)


# Read a VICE "-sounddev dump" register dump (emulator or vsid)
def get_reg_writes(sid, snd_log_name, skipsilence=1e6, minclock=0, maxclock=0, voicemask=VOICES, maxsilentclocks=0, truncate=1e6, passthrough=False):
    # TODO: fix minclock
    # TODO: fix maxsilentclocks
    # TODO: fix skipsilence
    state = SidRegState()
    df = pd.read_csv(
        snd_log_name,
        nrows=truncate,
        sep=' ',
        names=['clock_offset', 'reg', 'val'],
        dtype={'clock_offset': np.uint64, 'reg': np.uint8, 'val': np.uint8})
    df['clock'] = df['clock_offset'].cumsum()
    assert df['reg'].min() >= 0
    df = df[df['reg'] <= max(state.regstate)]
    if maxclock:
        df = df[df.clock <= maxclock]
    df['frame'] = df['clock'].floordiv(int(sid.clockq))
    df = df[['clock', 'clock_offset', 'frame', 'reg', 'val']]
    if passthrough:
        return df.to_numpy()
    # remove consecutive repeated register writes
    reg_dfs = []
    reg_cols = ['reg', 'val']
    for reg in sorted(df.reg.unique()):
        voicenum = state.reg_voicenum.get(reg, None)
        if voicenum is not None and voicenum not in voicemask:
            continue
        reg_df = df[df['reg'] == reg]
        reg_df = reg_df.loc[(reg_df[reg_cols].shift() != reg_df[reg_cols]).any(axis=1)]
        reg_dfs.append(reg_df)
    df = pd.concat(reg_dfs)
    df.set_index('clock')
    df = df.sort_index()
    # reset clock relative to 0
    df['clock'] -= df['clock'].min()
    df['frame'] -= df['frame'].min()
    df['clock_offset'] = df['clock'].diff().fillna(0).astype(np.uint64)
    # TODO: use precalculated gate mask
    # for voicenum in voicemask:
    #     gate_name = 'gate%u' % voicenum
    #     voice = state.voices[voicenum]
    #     control_reg = voice.regbase() + voice.CONTROL_REG
    #     gate_mask = (df['reg'] == control_reg)
    #     df[gate_name] = pd.UInt8Dtype()
    #     df.loc[gate_mask, gate_name] = df[gate_mask]['val'].values & 1
    return df


def add_clock_offset(df):
    df['clock_offset'] = df['clock'].sub(df['clock'].shift(1))
    df['clock_offset'] = df['clock_offset'].fillna(0)
    df = df.astype({'clock_offset': np.uint64})
    return df


def write_reg_writes(snd_log_name, reg_writes):
    reg_writes = add_clock_offset(reg_writes)
    reg_writes = reg_writes[['clock_offset', 'reg', 'val']]
    reg_writes.to_csv(snd_log_name, header=0, index=False)


def debug_raw_reg_writes(reg_writes):
    state = SidRegState()
    for row in reg_writes.itertuples():
        regevent = state.set(row.reg, row.val)
        if regevent:
            regs = [state.mainreg] + [state.voices[i] for i in state.voices]
            regdumps = tuple([reg.regdump() for reg in regs])
            active_voices = ','.join((str(voicenum) for voicenum in sorted(state.gates_on())))
            yield (row.clock, row.reg, row.val) + (active_voices,) + regdumps + (regevent,)


def debug_reg_writes(sid, reg_writes, consolidate_mb_clock=10):
    # TODO: fix consolidate_mb_clock
    for regevents in debug_raw_reg_writes(reg_writes):
        clock, reg, val, active_voices, main_regdump, voice1_regdump, voice2_regdump, voice3_regdump, regevent = regevents
        if isinstance(regevent, SidRegEvent):
            descr = regevent.descr
        line_items = (
            '%9u' % clock,
            '%6.2f' % sid.clock_to_s(clock),
            '%2u' % reg,
            '%3u' % val,
            '%6s' % active_voices,
            '%s' % main_regdump,
            '%s' % voice1_regdump,
            '%s' % voice2_regdump,
            '%s' % voice3_regdump,
            descr,
        )
        yield '\t'.join([str(i) for i in line_items])


def get_events(reg_writes):
    state = SidRegState()
    for row in reg_writes.itertuples():
        regevent = state.set(row.reg, row.val)
        if regevent:
            frozen_state = frozen_sid_state_factory(state)
            yield (row.clock, row.frame, regevent, frozen_state)


# consolidate events across multiple byte writes (e.g. collapse update of voice freq to one event)
def get_consolidated_changes(reg_writes, reg_write_clock_timeout):
    pendingevent = []
    for event in get_events(reg_writes):
        clock, frame, regevent, _state = event
        if pendingevent:
            pendingclock, _frame, pendingregevent, _pendingstate = pendingevent
            age = clock - pendingclock
            if age > reg_write_clock_timeout:
                yield pendingevent
                pendingevent = None
            elif regevent.otherreg == pendingregevent.reg:
                if age < reg_write_clock_timeout:
                    yield event
                    pendingevent = None
                    continue
            else:
                yield pendingevent
                pendingevent = None
        if regevent.otherreg is not None:
            pendingevent = event
            continue
        yield event


# bracket voice events by gate status changes.
def get_gate_events(reg_writes, reg_write_clock_timeout=64):
    voiceeventstack = defaultdict(list)

    def despool_events(voicenum):
        despooled = None
        if voiceeventstack[voicenum]:
            first_event = voiceeventstack[voicenum][0]
            _, _, first_state = first_event
            if first_state.voices[voicenum].gate:
                despooled = (voicenum, voiceeventstack[voicenum])
            voiceeventstack[voicenum] = []
        return despooled

    def append_event(voicenum, clock, frame, state):
        voiceeventstack[voicenum].append((clock, frame, state))

    for event in get_consolidated_changes(reg_writes, reg_write_clock_timeout):
        clock, frame, regevent, state = event
        voicenum = regevent.voicenum
        if voicenum is not None:
            last_voiceevent = None
            last_gate = None
            if voiceeventstack[voicenum]:
                last_voiceevent = voiceeventstack[voicenum][-1]
                _, _, last_state = last_voiceevent
                last_gate = last_state.voices[voicenum].gate
            voice_state = state.voices[voicenum]
            gate = voice_state.gate
            if last_gate is not None and last_gate != gate:
                if gate:
                    despooled = despool_events(voicenum)
                    if despooled:
                        yield despooled
                append_event(voicenum, clock, frame, state)
                continue
            if gate or voice_state.in_rel():
                append_event(voicenum, clock, frame, state)

    for voicenum in voiceeventstack:
        despooled = despool_events(voicenum)
        if despooled:
            yield despooled
