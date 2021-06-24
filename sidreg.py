# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABL E FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

# https://www.c64-wiki.com/wiki/SID

import copy
from functools import lru_cache

VOICES = frozenset([1, 2, 3])


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
        return hash((self.instance, tuple(sorted(self.regstate.items()))))

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
        super().__init__(instance)
        for reg in self._REGMAP:
            self._set(reg, 0)

    def regbase(self):
        return self.REGBASE + (self.instance - 1) * len(self._REGMAP)

    def bitmask(self, val, bits):
        return val & (2**bits - 1)

    def lohi(self, lo, hi, lobits, hibits):
        return (self.bitmask(self.regstate.get(hi, 0), hibits) << lobits) + self.bitmask(self.regstate.get(lo, 0), lobits)

    def lohi_attr(self, lo, hi, attr, lobits, hibits):
        val = self.lohi(lo, hi, lobits, hibits)
        assert val < 2**(lobits + hibits), val
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
       'freq',
       'pw_duty',
       'gate',
       'test',
       'noise',
       'pulse',
       'tri',
       'saw',
       'atk',
       'dec',
       'sus',
       'rel',
       'sync',
       'ring',
    ]

    sync_map = {
       1: 3,
       2: 1,
       3: 2,
    }

    CONTROL_REG = 4

    def __init__(self, voicenum):
        self.gate = None
        self.sync = None
        self.ring = None
        self.test = None
        self.atk = None
        self.dec = None
        self.sus = None
        self.rel = None
        super().__init__(voicenum)
        self.voicenum = voicenum

    def waveforms(self):
        return {waveform for waveform in ('tri', 'saw', 'pulse', 'noise') if getattr(self, waveform, None)}

    def flat_waveforms(self):
        return tuple(sorted(self.waveforms()))

    def any_waveform(self):
        return bool(self.waveforms())

    def sounding(self):
        return self.any_waveform() and not self.test

    def in_rel(self):
        return self.rel > 0 and not self.gate

    def synced_voicenums(self):
        if self.sync or (self.ring and getattr(self, 'tri', None)):
            return {self.sync_map[self.voicenum]}
        return set()


class SidVoiceRegState(SidVoiceRegStateMiddle):

    __slots__ = [
       'freq',
       'pw_duty',
       'dec',
       'atk',
       'sus',
       'rel',
       'gate',
       'sync',
       'ring',
       'test',
       'tri',
       'saw',
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
            5: self._atk_dec,
            6: self._sus_rel,
        }
        super().__init__(voicenum)
        self.voicenum = voicenum

    def _freq_descr(self):
        return self.lohi_attr(0, 1, 'freq', 8, 8)

    def _freq(self, reg):
        return (self._freq_descr(), {0, 1} - {reg})

    def _pwduty_descr(self):
        return self.lohi_attr(2, 3, 'pw_duty', 8, 4)

    def _pwduty(self, reg):
        return (self._pwduty_descr(), {2, 3} - {reg})

    def _atk_dec_descr(self):
        return self.byte2nib_literal(5, 'dec', 'atk')

    def _atk_dec(self, _):
        return (self._atk_dec_descr(), None)

    def _sus_rel_descr(self):
        return self.byte2nib_literal(6, 'rel', 'sus')

    def _sus_rel(self, _):
        return (self._sus_rel_descr(), None)

    def _control_descr(self):
        val = self.regstate[self.CONTROL_REG]
        return self.decodebits(val, {
            0: 'gate', 1: 'sync', 2: 'ring', 3: 'test',
            4: 'tri', 5: 'saw', 6: 'pulse', 7: 'noise'})

    def _control(self, _):
        return (self._control_descr(), None)


class SidFilterMainRegStateMiddle(SidRegHandler):

    REGBASE = 21
    NAME = 'main'

    filter_common = [
        'flt_res',
        'flt_coff',
        'flt_low',
        'flt_band',
        'flt_high',
    ]

    def voice_filtered(self, voicenum):
        filter_attr = 'flt%u' % voicenum
        return getattr(self, filter_attr)

    def voice_muted(self, voicenum):
        mute_attr = 'mute_voice%u' % voicenum
        return bool(getattr(self, mute_attr, False))

    def _voice_attrs(self, voicenum):
        return ['flt%u' % voicenum] + self.filter_common

    def diff_filter(self, voicenum, other):
        return self.diff_attr(self._voice_attrs(voicenum), other)

    def diff_filter_vol(self, voicenum, other):
        return self.diff_attr(['vol', 'mute3'] + self._voice_attrs(voicenum), other)


class SidFilterMainRegState(SidFilterMainRegStateMiddle):

    __slots__ = [
        '_REGMAP',
        'vol',
        'flt_res',
        'flt1',
        'flt2',
        'flt3',
        'flt_ext',
        'flt_coff',
        'flt_low',
        'flt_band',
        'flt_high',
        'mute3'
    ]

    def __init__(self, instance=0):
        self._REGMAP = {
            0: self._filtercutoff,
            1: self._filtercutoff,
            2: self._filterresonanceroute,
            3: self._filtermain,
        }
        self.vol = 0
        self.flt_res = 0
        super().__init__(instance)

    def regbase(self):
        return self.REGBASE

    def _filtercutoff(self, reg):
        return (self.lohi_attr(0, 1, 'flt_coff', 3, 8), {0, 1} - {reg})

    def _filterresonanceroute(self, _):
        route, self.flt_res = self.byte2nib(2)
        descr = {'flt_res': '%.2x' % self.flt_res}
        descr.update(self.decodebits(route, {
            0: 'flt1', 1: 'flt2', 2: 'flt3', 3: 'flt_ext'}))
        return (descr, None)

    def _filtermain(self, _):
        self.vol, filtcon = self.byte2nib(3)
        descr = {'main_vol': '%.2x' % self.vol}
        descr.update(self.decodebits(filtcon, {
            0: 'flt_low', 1: 'flt_band', 2: 'flt_high', 3: 'mute3'}))
        return(descr, None)


class SidRegStateMiddle(SidRegStateBase):

    __slots__ = [
        'voices',
        'reg_voicenum',
        'regstate',
        'mainreg',
    ]

    def __init__(self, instance=0):
        super().__init__(instance)
        self.voices = {}
        self.reg_voicenum = {}
        self.mainreg = None

    def gates_on(self):
        return {voicenum for voicenum in self.voices if self.voices[voicenum].gate}

    def audible_voicenums(self, prevstate):
        audible = copy.copy(VOICES)
        for voicenum in VOICES:
            voicestate = self.voices[voicenum]
            if self.mainreg.voice_muted(voicenum) or voicestate.test:
                audible -= {voicenum}
                continue
            if not voicestate.gate:
                prevvoicestate = None
                if prevstate:
                    prevvoicestate = prevstate.voices[voicenum]
                if prevvoicestate is None or not (prevvoicestate.gate and prevvoicestate.rel > 0):
                    audible -= {voicenum}
                    continue
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
        super().__init__(instance)
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
        return ' '.join([self.voices[voicenum].regdump() for voicenum in sorted(VOICES)] + [self.mainreg.regdump()])


class FrozenSidVoiceRegState(SidVoiceRegStateMiddle):

    __slots__ = [
       'freq',
       'pw_duty',
       'dec',
       'atk',
       'sus',
       'rel',
       'gate',
       'sync',
       'ring',
       'test',
       'tri',
       'saw',
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
        'flt_res',
        'flt1',
        'flt2',
        'flt3',
        'flt_ext',
        'flt_coff',
        'flt_low',
        'flt_band',
        'flt_high',
        'mute3',
        'regstate',
   ]

    def __init__(self, mainstate):
        for slot in self.__slots__:
            setattr(self, slot, getattr(mainstate, slot))

    def set(self, reg, val):
        raise NotImplementedError


def frozen_factory_hash(statehash, state, statecache, stateclass):
    if statehash not in statecache:
        statecache[statehash] = stateclass(state)
    return statecache[statehash]


def frozen_factory(state, statecache, stateclass):
    return frozen_factory_hash(
        state.__hash__(), state, statecache, stateclass)

frozen_voice_state = {}
frozen_main_state = {}
frozen_regstate = {}

class FrozenSidRegState(SidRegStateMiddle):

    __slots__ = [
        'voices',
        'mainreg',
        'reg_voicenum',
        'regstate',
    ]

    def __init__(self, state):
        super().__init__(state.instance)
        self.voices = {
            voicenum: frozen_factory(voicestate, frozen_voice_state, FrozenSidVoiceRegState)
            for voicenum, voicestate in state.voices.items()}
        self.mainreg = frozen_factory(state.mainreg, frozen_main_state, FrozenSidFilterMainRegState)
        self.regstate = frozen_factory_hash(hash(tuple(sorted(state.regstate))), state.regstate, frozen_regstate, dict)
        self.reg_voicenum = copy.copy(state.reg_voicenum)

    def set(self, reg, val):
        raise NotImplementedError


frozen_sid_state = {}

def frozen_sid_state_factory(state):
    return frozen_factory(state, frozen_sid_state, FrozenSidRegState)
