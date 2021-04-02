#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

# https://codebase64.org/doku.php?id=base:building_a_music_routine
# http://www.ucapps.de/howto_sid_wavetables_1.html

from collections import Counter, defaultdict
from functools import lru_cache
import numpy as np
import pandas as pd
from fileio import out_path
from sidmidi import ELECTRIC_SNARE, BASS_DRUM, LOW_TOM

cache = {}


def dump_patches(logfile, patch_count, patch_output):
    for ext_patches in patch_output:
        ext, patches = ext_patches
        if not patches:
            continue
        out_filename = out_path(logfile, ext)
        dfs = []
        for hashid, _ in sorted(patch_count.items(), key=lambda x: x[1], reverse=True):
            if hashid in patches:
                df = patches[hashid]
                df['hashid'] = hashid
                df['count'] = patch_count[hashid]
                dfs.append(df)
        df = pd.concat(dfs)
        cols = list(df.columns)
        cols.remove('hashid')
        cols.remove('count')
        df = df[['hashid', 'count'] + cols]
        df.to_csv(out_filename, index=False)


class SidSoundFragment:

    def __init__(self, percussion, sid, smf, voicenum, events, single_patches, multi_patches, patch_count):
        self.percussion = percussion
        self.voicenum = voicenum
        self.sid = sid
        self.smf = smf
        self.waveforms = Counter()
        self.waveform_order = []
        self.noisephases = 0
        self.all_noise = False
        self.midi_notes = []
        self.midi_pitches = []
        self.total_duration = 0
        self.max_midi_note = 0
        self.min_midi_note = 0
        self.single_patches = single_patches
        self.multi_patches = multi_patches
        self.patch_count = patch_count
        self.voicestates = [(clock, frame, state, state.voices[self.voicenum]) for clock, frame, state in events]
        self.first_clock = self.voicestates[0][0]

    def normalize_voicenum(self, voicenum):
        if voicenum == self.voicenum:
            return 1
        return 3

    @lru_cache
    def _rename_cols(self, cols):
        renamed_cols = []
        for col in cols:
            last_ch = col[-1]
            if last_ch.isdigit():
                renamed_cols.append(col.replace(last_ch, str(self.normalize_voicenum(int(last_ch)))))
            else:
                renamed_cols.append(col)
        return renamed_cols

    @lru_cache
    def _filter_cols(self, cols):
        return [col for col in cols if col.startswith('flt')]

    def _parsedf(self, voicenums):
        first_event = self.voicestates[0]
        _first_clock, first_frame, first_state, first_voicestate = first_event
        assert first_voicestate.gate

        first_row = {'clock': 0}
        fieldnames = ['clock']

        for voicenum in voicenums:
            voicestate = first_state.voices[voicenum]
            for field in voicestate.voice_regs:
                val = getattr(voicestate, field)
                field = '%s%u' % (field, voicenum)
                fieldnames.append(field)
                first_row[field] = val
            flt_v_key = 'flt%u' % voicenum
            fieldnames.append(flt_v_key)
            first_row[flt_v_key] = getattr(first_state.mainreg, flt_v_key)
        for field in first_state.mainreg.filter_common + ['vol']:
            val = getattr(first_state.mainreg, field)
            fieldnames.append(field)
            first_row[field] = val

        last_state = first_state
        orig_diffs = defaultdict(list)
        voice_sounding = {v: first_state.voices[v].sounding() for v in voicenums}
        reg_total = defaultdict(int)

        for clock, frame, state, voicestate in self.voicestates[1:]:
            diff = {}
            assert not state.mainreg.mute3
            for voicenum in voicenums:
                voicestate_now = state.voices[voicenum]
                last_voicestate = last_state.voices[voicenum]
                voice_diff = voicestate_now.diff(last_voicestate)
                voice_diff = {'%s%u' % (k, voicenum): v for k, v in voice_diff.items()}
                filter_diff = state.mainreg.diff_filter_vol(voicenum, last_state.mainreg)
                if not voice_sounding[voicenum]:
                    if voicestate_now.sounding():
                       voice_sounding[voicenum] = True
                    else:
                       for k, v in voice_diff.items():
                           first_row[k] += v
                       continue
                diff.update(voice_diff)
                diff.update(filter_diff)
            frame_clock = (frame - first_frame) * self.sid.clockq
            orig_diffs[frame_clock].append((clock, diff))
            for k, v in diff.items():
                reg_total[k] += v
            if not voicestate.gate and voicestate.rel == 0:
                break
            last_state = state

        del_cols = set()
        filtered_voices = 0
        for voicenum in voicenums:
            pw_duty_col = 'pw_duty%u' % voicenum
            if reg_total[pw_duty_col] == 0:
                del_cols.add(pw_duty_col)
            flt_col = 'flt%u' % voicenum
            if reg_total[flt_col] == 0:
                del_cols.add(flt_col)
            else:
                filtered_voices += 1
        if filtered_voices == 0:
            del_cols.update(self._filter_cols(tuple(reg_total.keys())))

        rows = [first_row]
        for frame_clock, clock_diffs in orig_diffs.items():
            first_clock, _ = clock_diffs[0]
            for clock, diff in clock_diffs:
                diff = {k: v for k, v in diff.items() if k not in del_cols}
                if diff:
                    diff['clock'] = frame_clock + (clock - first_clock)
                    rows.append(diff)

        df = pd.DataFrame(rows, columns=fieldnames, dtype=pd.Int64Dtype())
        df.columns = self._rename_cols(tuple(df.columns))
        hashid = hash(tuple(df.itertuples(index=False, name=None)))

        return (df, hashid)

    def parse(self):
        audible_voicenums = frozenset().union(*[state.audible_voicenums() for _, _, state, _ in self.voicestates])
        if self.voicenum not in audible_voicenums:
            return
        synced_voicenums = frozenset().union(*[voicestate.synced_voicenums() for _, _, _, voicestate in self.voicestates])
        voicenums = frozenset({self.voicenum}).union(synced_voicenums)
        assert len(voicenums) in (1, 2)
        df, hashid = self._parsedf(voicenums)

        if hashid not in self.patch_count:
            self.midi_notes = tuple(self.smf.get_midi_notes_from_events(self.sid, self.first_clock, self.voicestates))
            if self.midi_notes:
                self.midi_pitches = tuple([midi_note[1] for midi_note in self.midi_notes])
                self.total_duration = sum(duration for _, _, duration, _, _ in self.midi_notes)
                self.max_midi_note = max(self.midi_pitches)
                self.min_midi_note = min(self.midi_pitches)
            last_clock = 0
            all_waveforms = frozenset({'%s1' % col for col in ('tri', 'saw', 'pulse', 'noise')})
            for row in df.itertuples():
                rel_clock = row.clock - last_clock
                waveforms = frozenset({col[:-1] for col in all_waveforms if pd.notna(getattr(row, col)) and getattr(row, col) == 1})
                for waveform in waveforms:
                    self.waveforms[waveform] += rel_clock
                if not self.waveform_order or self.waveform_order[-1] != waveforms:
                    self.waveform_order.append(waveforms)
                last_clock = row.clock
            self.noisephases = len([waveforms for waveforms in self.waveform_order if 'noise' in waveforms])
            self.all_noise = set(self.waveforms.keys()) == {'noise'}
            cache[hashid] = (self.waveforms, self.waveform_order, self.noisephases, self.all_noise, self.midi_pitches, self.total_duration, self.max_midi_note, self.min_midi_note, self.midi_notes)
            if len(voicenums) == 1:
                self.single_patches[hashid] = df
            else:
                self.multi_patches[hashid] = df
        else:
            self.waveforms, self.waveform_order, self.noisephases, self.all_noise, self.midi_pitches, self.total_duration, self.max_midi_note, self.min_midi_note, self.midi_notes = cache[hashid]
        self.patch_count[hashid] += 1

    def descending_pitches(self):
        return len(self.midi_pitches) > 2 and self.midi_pitches[0] > self.midi_pitches[-1]

    def smf_transcribe(self):
        if self.noisephases:
            if self.percussion:
                clock, _pitch, _duration, velocity, _ = self.midi_notes[0]
                clock += self.first_clock

                if self.all_noise:
                    self.smf.add_drum_noise_duration(self.voicenum, clock, self.total_duration, velocity)
                elif self.noisephases > 1:
                    self.smf.add_drum_pitch(self.voicenum, clock, self.total_duration, ELECTRIC_SNARE, velocity)
                else:
                    if self.descending_pitches():
                        # http://www.ucapps.de/howto_sid_wavetables_1.html
                        self.smf.add_drum_pitch(self.voicenum, clock, self.total_duration, BASS_DRUM, velocity)
                    else:
                        self.smf.add_drum_pitch(self.voicenum, clock, self.total_duration, LOW_TOM, velocity)
        else:
            for clock, pitch, duration, velocity, _ in self.midi_notes:
                clock += self.first_clock
                self.smf.add_pitch(self.voicenum, clock, duration, pitch, velocity)
