# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABL E FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

# https://www.c64-wiki.com/wiki/SID

import copy
from functools import lru_cache

VOICES = {1, 2, 3}

class SidRegEvent:

    __slots__ = [
        'reg',
        'descr',
        'voicenum',
        'otherreg',
    ]

    def __init__(self, reg, descr, voicenum=None, otherreg=None):
        self.reg = reg
        self.descr = descr
        self.voicenum = voicenum
        self.otherreg = otherreg

    def __str__(self):
        return '%.2x %s voicenum %s otherreg %s' % (self.reg, self.descr, self.voicenum, self.otherreg)

    def __repr__(self):
        return self.__str__()


@lru_cache(maxsize=None)
def sid_reg_event_factory(reg, descr, voicenum=None, otherreg=None):
    return SidRegEvent(reg, descr, voicenum=voicenum, otherreg=otherreg)


class SidRegStateBase:

    __slots__ = [
        'regstate',
        'instance',
    ]

    _REGMAP = {}

    def __init__(self, instance=0):
        self.instance = instance
        self.regstate = {}

    def regdump(self):
        return ''.join(('%2.2x' % int(j) for _, j in sorted(self.regstate.items())))

    def __hash__(self):
        return '%2.2x%s' % (self.instance, self.regdump())

    def __str__(self):
        return self.regdump()

    def diff_attr(self, attrs, other):
        diff_attrs = {}
        for attr in attrs:
            mine = getattr(self, attr)
            others = getattr(other, attr)
            if mine != others:
                diff_attrs[attr] = mine - others
        return diff_attrs


class SidRegHandler(SidRegStateBase):

    __slots__ = [
        'regstate',
        'instance',
        '_REGMAP',
    ]

    REGBASE = 0
    NAME = 'unknown'

    def __init__(self, instance=0):
        super(SidRegHandler, self).__init__(instance)
        for reg in self._REGMAP:
            self._set(reg, 0)

    def regbase(self):
        return self.REGBASE + (self.instance - 1) * len(self._REGMAP)

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
        descr, otherreg = self._REGMAP[reg](reg)
        preamble = '%s %u %.2x -> %.2x' % (self.NAME, self.instance, val, reg)
        if otherreg is not None:
            otherreg = list(otherreg)[0] + self.regbase()
        return (preamble, descr, otherreg)

    def set(self, reg, val):
        reg -= self.regbase()
        return self._set(reg, val)


class SidVoiceRegStateMiddle(SidRegHandler):

    voice_regs = [
       'frequency',
       'pw_duty',
       'attack',
       'decay',
       'sustain',
       'release',
       'gate',
       'sync',
       'ring',
       'test',
       'triangle',
       'sawtooth',
       'pulse',
       'noise',
    ]

    def __init__(self, voicenum):
        super(SidVoiceRegStateMiddle, self).__init__(voicenum)
        self.voicenum = voicenum
        self.gate = None
        self.sync = None
        self.ring = None
        self.test = None
        self.attack = None
        self.decay = None
        self.sustain = None
        self.release = None

    def waveforms(self):
        return {waveform for waveform in ('triangle', 'sawtooth', 'pulse', 'noise') if getattr(self, waveform, None)}

    def flat_waveforms(self):
        return tuple(sorted(self.waveforms()))

    def any_waveform(self):
        return bool(self.waveforms())

    def gate_on(self):
        # https://codebase64.org/doku.php?id=base:classic_hard-restart_and_about_adsr_in_generally
        if self.test:
            return False
        if not self.gate:
            return False
        return True

    def in_release(self):
        return self.release > 0 and not self.gate_on()

    def synced_voicenums(self):
        voicenums = set()
        sync_voicenum = self.voicenum + 2
        if sync_voicenum > len(VOICES):
            sync_voicenum -= len(VOICES)
        if self.sync or self.ring:
            voicenums.add(sync_voicenum)
        return voicenums


class SidVoiceRegState(SidVoiceRegStateMiddle):

    __slots__ = [
       'frequency',
       'pw_duty',
       'decay',
       'attack',
       'sustain',
       'release',
       'gate',
       'sync',
       'ring',
       'test',
       'triangle',
       'sawtooth',
       'pulse',
       'noise',
       'voicenum',
       '_REGMAP',
    ]

    REGBASE = 0
    NAME = 'voice'

    def __init__(self, voicenum):
        self._REGMAP = {
            0: self._freq,
            1: self._freq,
            2: self._pwduty,
            3: self._pwduty,
            4: self._control,
            5: self._attack_decay,
            6: self._sustain_release,
        }
        super(SidVoiceRegState, self).__init__(voicenum)
        self.voicenum = voicenum

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


class SidFilterMainRegStateMiddle(SidRegHandler):

    REGBASE = 21
    NAME = 'main'

    filter_common = [
        'filter_res',
        'filter_cutoff',
        'filter_low',
        'filter_band',
        'filter_high',
    ]

    def voice_filtered(self, voicenum):
        filter_attr = 'filter_voice%u' % voicenum
        return getattr(self, filter_attr)

    def voice_muted(self, voicenum):
        mute_attr = 'mute_voice%u' % voicenum
        return bool(getattr(self, mute_attr, False))

    def diff_filter(self, voicenum, other):
        return self.diff_attr(self.filter_common + ['filter_voice%u' % voicenum], other)


class SidFilterMainRegState(SidFilterMainRegStateMiddle):

    __slots__ = [
        '_REGMAP',
        'vol',
        'filter_res',
        'filter_voice1',
        'filter_voice2',
        'filter_voice3',
        'filter_external',
        'filter_cutoff',
        'filter_low',
        'filter_band',
        'filter_high',
        'mute_voice3'
    ]

    def __init__(self, instance=0):
        self._REGMAP = {
            0: self._filtercutoff,
            1: self._filtercutoff,
            2: self._filterresonanceroute,
            3: self._filtermain,
        }
        self.vol = 0
        self.filter_res = 0
        super(SidFilterMainRegState, self).__init__(instance)

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


class SidRegStateMiddle(SidRegStateBase):

    __slots__ = [
        'voices',
        'reg_voicenum',
        'regstate',
        'mainreg',
    ]

    def __init__(self, instance=0):
        super(SidRegStateMiddle, self).__init__(instance)
        self.voices = {}
        self.reg_voicenum = {}
        self.mainreg = None

    def gates_on(self):
        return {voicenum for voicenum in self.voices if self.voices[voicenum].gate_on()}

    def audible_voicenums(self):
        audible = copy.copy(VOICES)
        for voicenum in VOICES:
            voicestate = self.voices[voicenum]
            if not voicestate.gate or voicestate.test or self.mainreg.voice_muted(voicenum):
                audible -= {voicenum}
                continue
            synced_voicenums = voicestate.synced_voicenums()
            if synced_voicenums:
                audible -= synced_voicenums
        return audible


class SidRegState(SidRegStateMiddle):

    __slots__ = [
       '_reghandlers',
       '_last_descr',
       'voices',
       'reg_voicenum',
       'mainreg',
    ]

    def __init__(self, instance=0):
        super(SidRegState, self).__init__(instance)
        self._reghandlers = {}
        for voicenum in VOICES:
            voice = SidVoiceRegState(voicenum)
            regbase = voice.regbase()
            for voicereg in voice._REGMAP:
                reg = regbase + voicereg
                self._reghandlers[reg] = voice
                self.reg_voicenum[reg] = voicenum
            self.voices[voicenum] = voice
        self.mainreg = SidFilterMainRegState()
        regbase = self.mainreg.regbase()
        for i in self.mainreg._REGMAP:
            self._reghandlers[regbase + i] = self.mainreg
        self.regstate = {i: 0 for i in self._reghandlers}
        self._last_descr = {i: {} for i in self._reghandlers}

    def _descr_diff(self, last_descr, descr):
        descr_diff = {k: v for k, v in descr.items() if v != last_descr.get(k, None)}
        descr_txt = ' '.join(('%s: %s' % (k, v) for k, v in sorted(descr_diff.items())))
        return descr_txt

    def set(self, reg, val):
        handler = self._reghandlers[reg]
        preamble, descr, otherreg = handler.set(reg, val)
        if self.regstate[reg] == val:
            return None
        descr_txt = self._descr_diff(self._last_descr[reg], descr)
        event = sid_reg_event_factory(
            reg,
            ' '.join((preamble, descr_txt)),
            voicenum=self.reg_voicenum.get(reg, None),
            otherreg=otherreg)
        self.regstate[reg] = val
        self._last_descr[reg] = descr
        return event

    def __str__(self):
        return ' '.join((self.voices[voicenum].regdump() for voicenum in sorted(VOICES)) + (self.mainreg.regdump(),))


class FrozenSidVoiceRegState(SidVoiceRegStateMiddle):

    __slots__ = [
       'frequency',
       'pw_duty',
       'decay',
       'attack',
       'sustain',
       'release',
       'gate',
       'sync',
       'ring',
       'test',
       'triangle',
       'sawtooth',
       'pulse',
       'noise',
       'voicenum',
       'instance',
       'regstate',
    ]

    def __init__(self, voicestate):
        for slot in self.__slots__:
            setattr(self, slot, getattr(voicestate, slot))

    def set(self, reg, val):
        raise NotImplementedError

    def diff(self, other):
        return self.diff_attr([slot for slot in self.__slots__ if not slot.startswith('reg')], other)


class FrozenSidFilterMainRegState(SidFilterMainRegStateMiddle):

    __slots__ = [
        'instance',
        'vol',
        'filter_res',
        'filter_voice1',
        'filter_voice2',
        'filter_voice3',
        'filter_external',
        'filter_cutoff',
        'filter_low',
        'filter_band',
        'filter_high',
        'mute_voice3',
        'regstate',
   ]

    def __init__(self, mainstate):
        for slot in self.__slots__:
            setattr(self, slot, getattr(mainstate, slot))

    def set(self, reg, val):
        raise NotImplementedError


def frozen_factory(state, statecache, stateclass):
   statehash = state.__hash__()
   if statehash not in statecache:
       statecache[statehash] = stateclass(state)
   return statecache[statehash]

frozen_voice_state = {}
frozen_main_state = {}

class FrozenSidRegState(SidRegStateMiddle):

    __slots__ = [
        'voices',
        'mainreg',
        'reg_voicenum',
        'regstate',
    ]

    def __init__(self, state):
        super(FrozenSidRegState, self).__init__(state.instance)
        self.voices = {
            voicenum: frozen_factory(voicestate, frozen_voice_state, FrozenSidVoiceRegState)
            for voicenum, voicestate in state.voices.items()}
        self.mainreg = frozen_factory(state.mainreg, frozen_main_state, FrozenSidFilterMainRegState)
        self.regstate = copy.copy(state.regstate)
        self.reg_voicenum = copy.copy(state.reg_voicenum)

    def set(self, reg, val):
        raise NotImplementedError


frozen_sid_state = {}

def frozen_sid_state_factory(state):
    return frozen_factory(state, frozen_sid_state, FrozenSidRegState)
