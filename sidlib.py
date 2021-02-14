# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABL E FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import gzip
import os

from sidreg import VOICES, SidRegState, frozen_sid_state_factory

class SidWrap:

    def __init__(self, pal):
        if pal:
            self.clock_frequency = 985248.0 # SoundInterfaceDevice.PAL_CLOCK_FREQUENCY
        else:
            self.clock_frequency = 1022730.0 # SoundInterfaceDevice.NTSC_CLOCK_FREQUENCY


def get_sid(pal):
    return SidWrap(pal)


# http://www.sidmusic.org/sid/sidtech2.html
def real_sid_freq(sid, freq_reg):
    return freq_reg * sid.clock_frequency / 16777216

def clock_to_s(sid, clock):
    return clock / sid.clock_frequency

def clock_to_qn(sid, clock, bpm):
    return clock_to_s(sid, clock) * bpm / 60

def file_reader(snd_log_name):
    snd_log_name = os.path.expanduser(snd_log_name)
    if snd_log_name.endswith('.gz'):
        return gzip.open(snd_log_name, 'rb')
    return open(snd_log_name)


# Read a VICE "-sounddev dump" register dump (emulator or vsid)
def get_reg_writes(snd_log_name, skipsilence=1e6):
    maxreg = max(SidRegState().regstate)
    writes = []
    clock = 0
    silenceskipped = False
    with file_reader(snd_log_name) as snd_log:
        for line in snd_log:
            ts_offset, reg, val = (int(i) for i in line.strip().split())
            assert val >= 0 and reg <= 255, val
            # skip first pause of > 1e6
            if ts_offset > skipsilence and not silenceskipped:
                continue
            clock += ts_offset
            if reg <= maxreg:
                assert reg >= 0 and reg <= maxreg, reg
                writes.append((clock, reg, val))
    return writes


def write_reg_writes(snd_log_name, reg_writes):
    with open(snd_log_name, 'w') as snd_log_f:
        last_clock = 0
        for clock, reg, val in reg_writes:
            rel_clock = clock - last_clock
            last_clock = clock
            snd_log_f.write(' '.join((str(i) for i in (rel_clock, reg, val))) + '\n')


def get_reg_changes(reg_writes, voicemask=VOICES, minclock=0, maxclock=0, maxsilentclocks=0):
    change_only_writes = []
    state = SidRegState()
    relative_clock = 0
    last_any_gate_on = None
    for clock, reg, val in reg_writes:
        regevent = state.set(reg, val)
        if clock < minclock:
            continue
        if maxclock and clock > maxclock:
            break
        if not regevent:
            continue
        if regevent.voicenum and regevent.voicenum not in voicemask:
            continue
        gates_on_now = state.gates_on()
        if maxsilentclocks and not gates_on_now:
            if last_any_gate_on and clock - last_any_gate_on > maxsilentclocks:
                break
        if gates_on_now:
            last_any_gate_on = clock
        if not change_only_writes and minclock:
            relative_clock = clock
            for reg_pre, val_pre in state.regstate.items():
                reg_pre_voicenum = state.reg_voicenum(reg_pre)
                if reg_pre_voicenum is None or reg_pre_voicenum in voicemask:
                    change_only_writes.append((clock - relative_clock, reg_pre, val_pre))
        change_only_writes.append((clock - relative_clock, reg, val))
    return change_only_writes


def debug_reg_writes(sid, reg_writes, consolidate_mb_clock=10):
    state = SidRegState()
    raw_regevents = []
    for clock, reg, val in reg_writes:
        regevent = state.set(reg, val)
        regs = [state.mainreghandler] + [state.voices[i] for i in state.voices]
        hashregs = tuple([reg.hashreg() for reg in regs])
        active_voices = ','.join((str(voicenum) for voicenum in sorted(state.gates.on())))
        raw_regevents.append((clock, reg, val) + (active_voices,) + hashregs + (regevent,))
    lines = []
    for i, regevents in enumerate(raw_regevents):
        clock, reg, val, active_voices, main_hashreg, voice1_hashreg, voice2_hashreg, voice3_hashreg, regevent = regevents
        try:
            next_regevents = raw_regevents[i + 1]
        except IndexError:
            next_regevents = None
        descr = ''
        if regevent:
            descr = regevent.descr
        if next_regevents:
            next_clock = next_regevents[0]
            next_regevent = next_regevents[-1]
            if next_regevent and regevent and next_regevent.reg == regevent.otherreg and next_clock - clock < consolidate_mb_clock:
                descr = ''
        line_items = (
            '%9u' % clock,
            '%6.2f' % clock_to_s(sid, clock),
            '%2u' % reg,
            '%3u' % val,
            '%6s' % active_voices,
            '%s' % main_hashreg,
            '%s' % voice1_hashreg,
            '%s' % voice2_hashreg,
            '%s' % voice3_hashreg,
            descr,
        )
        lines.append('\t'.join([str(i) for i in line_items]))
    return lines


def get_events(writes, voicemask=VOICES):
    events = []
    state = SidRegState()
    for clock, reg, val in writes:
        regevent = state.set(reg, val)
        if not regevent:
            continue
        if regevent.voicenum and regevent.voicenum not in voicemask:
            continue
        frozen_state = frozen_sid_state_factory(state)
        events.append((clock, reg, val, regevent, frozen_state))
    return events


# consolidate events across multiple byte writes (e.g. collapse update of voice frequency to one event)
def get_consolidated_changes(writes, voicemask=VOICES, reg_write_clock_timeout=64):
    pendingevent = None
    consolidated = []
    for event in get_events(writes, voicemask=voicemask):
        clock, _, _, regevent, state = event
        event = (clock, regevent, state)
        if pendingevent is not None:
            pendingclock, pendingregevent, _pendingstate = pendingevent
            age = clock - pendingclock
            if age > reg_write_clock_timeout:
                consolidated.append(pendingevent)
                pendingevent = None
            elif regevent.otherreg == pendingregevent.reg:
                if age < reg_write_clock_timeout:
                    consolidated.append(event)
                    pendingevent = None
                    continue
            else:
                consolidated.append(pendingevent)
                pendingevent = None
        if regevent.otherreg is not None:
            pendingevent = event
            continue
        consolidated.append(event)
    return sorted(consolidated, key=lambda x: x[0])


# bracket voice events by gate status changes.
def get_gate_events(reg_writes, voicemask):
    mainevents = []
    voiceevents = {v: [] for v in voicemask}
    voiceeventstack = {v: [] for v in voicemask}

    def despool_events(voicenum):
        if voiceeventstack[voicenum]:
            first_event = voiceeventstack[voicenum][0]
            first_clock, _, first_state = first_event
            if first_state.voices[voicenum].gate:
                voiceevents[voicenum].append((first_clock, voiceeventstack[voicenum]))
            voiceeventstack[voicenum] = []

    def append_event(voicenum, event):
        voiceeventstack[voicenum].append(event)

    for event in reg_writes:
        _clock, regevent, state = event
        voicenum = regevent.voicenum
        if voicenum is None:
            mainevents.append(event)
        else:
            last_voiceevent = None
            last_gate = None
            if voiceeventstack[voicenum]:
                last_voiceevent = voiceeventstack[voicenum][-1]
                _, _, last_state = last_voiceevent
                last_gate = last_state.voices[voicenum].gate_on()
            voice_state = state.voices[voicenum]
            gate = voice_state.gate_on()
            if last_gate is not None and last_gate != gate:
                if gate:
                    despool_events(voicenum)
                    append_event(voicenum, event)
                else:
                    append_event(voicenum, event)
                continue
            if gate or (voice_state.release > 0 and not voice_state.test):
                append_event(voicenum, event)

    for voicenum in voicemask:
        despool_events(voicenum)
    return mainevents, voiceevents
