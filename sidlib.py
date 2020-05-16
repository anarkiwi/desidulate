# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABL E FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import copy

VOICES = {1, 2, 3}

# https://www.c64-wiki.com/wiki/SID


class SidRegEvent:

    def __init__(self, reg, descr, voicenum=None, otherreg=None):
        self.reg = reg
        self.descr = descr
        self.voicenum = voicenum
        self.otherreg = otherreg

    def __str__(self):
        return '%.2x %s voicenum %s otherreg %s' % (self.reg, self.descr, self.voicenum, self.otherreg)

    def __repr__(self):
        return self.__str__()


class SidRegStateBase:

    def __init__(self):
        self.regstate = {}

    def hashreg(self):
        return ''.join(('%2.2x' % int(j) for _, j in sorted(self.regstate.items())))

    def __eq__(self, other):
        return self.hashreg() == other.hashreg()

    def __ne__(self, other):
        return not self.__eq__(other)


class SidRegHandler(SidRegStateBase):

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
        return {attr: '%.2x' % val}

    def byte2nib(self, reg):
        val = self.regstate.get(reg, 0)
        lo, hi = val & 0x0f, val >> 4
        return (lo, hi)

    def byte2nib_literal(self, reg, lo_lit, hi_lit):
        lo, hi = self.byte2nib(reg)
        descrs = {}
        for lit, val in ((lo_lit, lo), (hi_lit, hi)):
            setattr(self, lit, val)
            descrs[lit] = '%.2x' % val
        return descrs

    def decodebits(self, val, decodemap):
        bstates = {}
        for b in decodemap:
            attr = decodemap[b]
            bval = int(bool(val & 2**b))
            setattr(self, attr, bval)
            bstates[attr] = '%u' % bval
        return bstates

    def _set(self, reg, val):
        self.regstate[reg] = val
        descr, otherreg = self.REGMAP[reg](reg)
        preamble = '%s %u %.2x -> %.2x' % (self.NAME, self.instance, val, reg)
        if otherreg is not None:
            otherreg = list(otherreg)[0] + self.regbase()
        return (preamble, descr, otherreg)

    def set(self, reg, val):
        reg -= self.regbase()
        return self._set(reg, val)


class SidVoiceRegState(SidRegHandler):

    REGBASE = 0
    NAME = 'voice'


    def _freq_descr(self):
        return self.lohi_attr(0, 1, 'frequency')

    def _freq(self, reg):
        return (self._freq_descr(), {0, 1} - {reg})

    def _pwduty_descr(self):
        return self.lohi_attr(2, 3, 'pw_duty')

    def _pwduty(self, reg):
        return (self._pwduty_descr(), {2, 3} - {reg})

    def _attack_decay_descr(self):
        return self.byte2nib_literal(5, 'decay', 'attack')

    def _attack_decay(self, _):
        return (self._attack_decay_descr(), None)

    def _sustain_release_descr(self):
        return self.byte2nib_literal(6, 'release', 'sustain')

    def _sustain_release(self, _):
        return (self._sustain_release_descr(), None)

    def _control_descr(self):
        val = self.regstate[4]
        return self.decodebits(val, {
            0: 'gate', 1: 'sync', 2: 'ring', 3: 'test',
            4: 'triangle', 5: 'sawtooth', 6: 'pulse', 7: 'noise'})

    def _control(self, _):
        return (self._control_descr(), None)

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

    def any_waveform(self):
        return self.triangle or self.sawtooth or self.pulse or self.noise



class SidFilterMainRegState(SidRegHandler):

    REGBASE = 21
    NAME = 'main'

    def regbase(self):
        return self.REGBASE

    def _filtercutoff(self, reg):
        return (self.lohi_attr(0, 1, 'filter_cutoff'), {0, 1} - {reg})

    def _filterresonanceroute(self, _):
        route, self.filter_res = self.byte2nib(2)
        descr = {'filter_res': '%.2x' % self.filter_res}
        descr.update(self.decodebits(route, {
            0: 'filter_voice1', 1: 'filter_voice2', 2: 'filter_voice3', 3: 'filter_external'}))
        return (descr, None)

    def _filtermain(self, _):
        self.vol, filtcon = self.byte2nib(3)
        descr = {'main_vol': '%.2x' % self.vol}
        descr.update(self.decodebits(filtcon, {
            0: 'filter_low', 1: 'filter_band', 2: 'filter_high', 3: 'mute_voice3'}))
        return(descr, None)

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


class SidRegState(SidRegStateBase):

    def __init__(self):
        self.reghandlers = {}
        self.voices = {}
        self.voicereg = {}
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
        self.last_descr = {i: {} for i in self.reghandlers}

    def reg_voicenum(self, reg):
        handler = self.reghandlers[reg]
        if isinstance(handler, SidVoiceRegState):
            return handler.voicenum
        return None

    def descr_diff(self, _reg, last_descr, descr):
        descr_diff = {}
        descr_diff = {k: v for k, v in descr.items() if v != last_descr.get(k, None)}
        descr_txt = ' '.join(('%s: %s' % (k, v) for k, v in sorted(descr_diff.items())))
        return descr_txt

    def set(self, reg, val):
        voicenum = None
        handler = self.reghandlers[reg]
        if isinstance(handler, SidVoiceRegState):
            voicenum = handler.voicenum
        preamble, descr, otherreg = handler.set(reg, val)
        if self.regstate[reg] == val:
            return None
        descr_txt = self.descr_diff(reg, self.last_descr[reg], descr)
        self.regstate[reg] = val
        self.last_descr[reg] = descr
        return SidRegEvent(reg, ' '.join((preamble, descr_txt)), voicenum=voicenum, otherreg=otherreg)

    def hashreg(self):
        return hash(frozenset(self.regstate.items()))


# http://www.sidmusic.org/sid/sidtech2.html
def real_sid_freq(sid, freq_reg):
    return freq_reg * sid.clock_frequency / 16777216

def clock_to_s(sid, clock):
    return clock / sid.clock_frequency

def clock_to_qn(sid, clock, bpm):
    return clock_to_s(sid, clock) * bpm / 60


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


def write_reg_writes(snd_log_name, reg_writes):
    with open(snd_log_name, 'w') as snd_log_f:
        last_clock = 0
        for clock, reg, val in reg_writes:
            rel_clock = clock - last_clock
            last_clock = clock
            snd_log_f.write(' '.join((str(i) for i in (rel_clock, reg, val))) + '\n')


def gates_on(state):
    return {voicenum for voicenum in state.voices if state.voices[voicenum].gate}


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
        gates_on_now = gates_on(state)
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
        active_voices = ','.join((str(voicenum) for voicenum in sorted(gates_on(state))))
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
    statecache = {}
    for clock, reg, val in writes:
        regevent = state.set(reg, val)
        if not regevent:
            continue
        if regevent.voicenum and regevent.voicenum not in voicemask:
            continue
        hashedreg = state.hashreg()
        if hashedreg not in statecache:
            statecache[hashedreg] = copy.deepcopy(state)
        events.append((clock, reg, val, regevent, statecache[hashedreg]))
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

    def gate_on(voice_state):
        if voice_state.test:
            return False
        if not voice_state.gate:
            return False
        return True

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
                last_gate = gate_on(last_state.voices[voicenum])
            voice_state = state.voices[voicenum]
            gate = gate_on(voice_state)
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
