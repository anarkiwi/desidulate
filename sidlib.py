# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABL E FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import copy

VOICES = {1, 2, 3}


class SidRegEvent:

    def __init__(self, reg, descr, voicenum=None, otherreg=None):
        self.reg = reg
        self.descr = descr
        self.voicenum = voicenum
        self.otherreg = otherreg

    def __str__(self):
        return '%x %s %s %s' % (self.reg, self.descr, self.voicenum, self.otherreg)


class SidRegHandler:

    REGBASE = 0
    NAME = 'unknown'
    REGMAP = {}

    def __init__(self, instance=0):
        self.instance = instance
        self.regstate = {}
        for reg in self.REGMAP:
            self._set(reg, 0)

    def regbase(self):
        return self.REGBASE + (self.instance - 1) * len(self.REGMAP)

    def lohi(self, lo, hi):
        return (self.regstate.get(hi, 0) << 8) + self.regstate.get(lo, 0)

    def lohi_attr(self, lo, hi, attr):
        val = self.lohi(lo, hi)
        setattr(self, attr, val)
        return '%s %x' % (attr, val)

    def byte2nib(self, reg):
        val = self.regstate[reg]
        lo, hi = val & 0x0f, val >> 4
        return (lo, hi)

    def byte2nib_literal(self, reg, lo_lit, hi_lit):
        lo, hi = self.byte2nib(reg)
        descrs = []
        for lit, val in ((lo_lit, lo), (hi_lit, hi)):
            setattr(self, lit, val)
            descrs.append('%s: %x' % (lit, val))
        return ', '.join(descrs)

    def decodebits(self, val, decodemap):
        bstates = []
        for b in decodemap:
            attr = decodemap[b]
            bval = int(bool(val & 2**b))
            setattr(self, attr, bval)
            bstates.append('%s: %u' % (attr, bval))
        return ', '.join(bstates)

    def _set(self, reg, val):
        self.regstate[reg] = val
        decoded, otherreg = self.REGMAP[reg](reg)
        descr = '%s %u %s val %x -> reg %x' % (self.NAME, self.instance, decoded, val, reg)
        return (descr, otherreg)

    def set(self, reg, val):
        reg -= self.regbase()
        return self._set(reg, val)


class SidVoiceRegState(SidRegHandler):

    REGBASE = 0
    NAME = 'voice'

    def _freq(self, reg):
        return (self.lohi_attr(0, 1, 'frequency'), {0, 1} - {reg})

    def _pwduty(self, reg):
        return (self.lohi_attr(2, 3, 'pw_duty'), {2, 3} - {reg})

    def _attack_decay(self, _):
        return (self.byte2nib_literal(5, 'decay', 'attack'), None)

    def _sustain_release(self, _):
        return (self.byte2nib_literal(6, 'release', 'sustain'), None)

    def _control(self, _):
        val = self.regstate[4]
        return (self.decodebits(val, {
            0: 'gate', 1: 'sync', 2: 'ring', 3: 'test',
            4: 'triangle', 5: 'sawtooth', 6: 'pulse', 7: 'noise'}), None)

    def __init__(self, instance):
        self.REGMAP = {
            0: self._freq,
            1: self._freq,
            2: self._pwduty,
            3: self._pwduty,
            4: self._control,
            5: self._attack_decay,
            6: self._sustain_release,
        }
        super(SidVoiceRegState, self).__init__(instance)
        self.voicenum = instance



class SidFilterMainRegState(SidRegHandler):

    REGBASE = 21
    NAME = 'main'

    def regbase(self):
        return self.REGBASE

    def _filtercutoff(self, reg):
        return (self.lohi_attr(0, 1, 'filter_cutoff'), {0, 1} - {reg})

    def _filterresonanceroute(self, _):
        route, self.filter_res = self.byte2nib(2)
        return ('filter res %x, route %s' % (self.filter_res, self.decodebits(route, {
            0: 'filter_voice1', 1: 'filter_voice2', 2: 'filter_voice3',
            3: 'filter_external'})), None)

    def _filtermain(self, _):
        self.vol, filtcon = self.byte2nib(3)
        return ('vol %x, filter type %s' % (self.vol, self.decodebits(filtcon, {
            0: 'filter_low', 1: 'filter_band', 2: 'filter_high', 3: 'mute_voice3'})), None)

    def __init__(self, instance=0):
        self.REGMAP = {
            0: self._filtercutoff,
            1: self._filtercutoff,
            2: self._filterresonanceroute,
            3: self._filtermain,
        }
        self.vol = 0
        self.filter_res = 0
        super(SidFilterMainRegState, self).__init__(instance)


class SidRegState:

    def __init__(self):
        self.reghandlers = {}
        self.voices = {}
        for voicenum in VOICES:
            voice = SidVoiceRegState(voicenum)
            regbase = voice.regbase()
            for reg in voice.REGMAP:
                self.reghandlers[regbase + reg] = voice
            self.voices[voicenum] = voice
        self.mainreghandler = SidFilterMainRegState()
        regbase = self.mainreghandler.regbase()
        for i in self.mainreghandler.REGMAP:
            self.reghandlers[regbase + i] = self.mainreghandler
        self.regstate = {i: 0 for i in self.reghandlers}

    def set(self, reg, val):
        voicenum = None
        handler = self.reghandlers[reg]
        if isinstance(handler, SidVoiceRegState):
            voicenum = handler.voicenum
        regevent, otherreg = handler.set(reg, val)
        if otherreg:
            otherreg = list(otherreg)[0]
        if self.regstate[reg] == val:
            return None
        self.regstate[reg] = val
        return SidRegEvent(reg, regevent, voicenum=voicenum, otherreg=otherreg)


# http://www.sidmusic.org/sid/sidtech2.html
def real_sid_freq(sid, freq_reg):
    return freq_reg * sid.clock_frequency / 16777216


def clock_to_qn(sid, clock, bpm):
    return clock / sid.clock_frequency * bpm / 60


# Read a VICE "-sounddev dump" register dump (emulator or vsid)
def get_reg_writes(snd_log_name, skipsilence=1e6):
    state = SidRegState()
    maxreg = max(state.regstate)
    writes = []
    clock = 0
    silenceskipped = False
    with open(snd_log_name) as snd_log:
        for line in snd_log:
            ts_offset, reg, val = (int(i) for i in line.strip().split())
            assert reg >= 0 and reg <= maxreg, reg
            assert val >= 0 and reg <= 255, val
            # skip first pause of > 1e6
            if ts_offset > skipsilence and not silenceskipped:
                continue
            clock += ts_offset
            writes.append((clock, reg, val))
    return writes


def get_reg_changes(reg_writes, voicemask=VOICES):
    change_only_writes = []
    state = SidRegState()
    for clock, reg, val in reg_writes:
        regevent = state.set(reg, val)
        if not regevent:
            continue
        if regevent.voicenum and regevent.voicenum not in voicemask:
            continue
        change_only_writes.append((clock, reg, val))
    return change_only_writes


def get_events(writes, voicemask=VOICES):
    events = []
    state = SidRegState()
    for clock, reg, val in writes:
        regevent = state.set(reg, val)
        if not regevent:
            continue
        if regevent.voicenum and regevent.voicenum not in voicemask:
            continue
        events.append((clock, regevent, copy.deepcopy(state)))
    return events


def get_consolidated_changes(writes, reg_write_clock_timeout=16, voicemask=VOICES):
    pendingclock = 0
    pendingregevent = None
    consolidated = []
    for clock, regevent, state in get_events(writes, voicemask=voicemask):
        if pendingregevent:
            if regevent.otherreg == pendingregevent.reg and clock - pendingclock < reg_write_clock_timeout:
                consolidated.append((clock, regevent, state))
                pendingregevent = None
                continue
            consolidated.append((pendingclock, pendingregevent, state))
            pendingregevent = None
        if regevent.otherreg is not None:
            pendingregevent = regevent
            pendingclock = clock
            continue
        consolidated.append((clock, regevent, state))
    return consolidated
