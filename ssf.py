#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

# https://codebase64.org/doku.php?id=base:building_a_music_routine
# http://www.ucapps.de/howto_sid_wavetables_1.html

from collections import Counter, defaultdict
import numpy as np
import pandas as pd
from fileio import out_path
from sidmidi import ELECTRIC_SNARE, BASS_DRUM, LOW_TOM


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
        self.voice_filtered = False
        self.total_duration = 0
        self.max_midi_note = 0
        self.min_midi_note = 0
        self.single_patches = single_patches
        self.multi_patches = multi_patches
        self.patch_count = patch_count
        self.voicestates = [(clock, frame, state, state.voices[self.voicenum]) for clock, frame, state in events]

    def trim_gateoff(self):
        for i, clock_voicestate_state in enumerate(self.voicestates):
            _, _, state, voicestate = clock_voicestate_state
            if not voicestate.gate and not voicestate.rel:
                self.voicestates = self.voicestates[:i+1]
                break
        i = len(self.voicestates) - 1
        while i > 0 and self.voicestates[i][3].test:
            i -= 1
        if i:
            self.voicestates = self.voicestates[:i+2]

    def normalize_voicenum(self, voicenum):
        if voicenum == self.voicenum:
            return 1
        return 3

    def _patchcsv(self, voicenums, fieldnames, first_row, orig_diffs):
        rows = [first_row]
        for frame_clock, clock_diffs in orig_diffs.items():
            first_clock = None
            for clock, diff in clock_diffs:
                if first_clock is None:
                    diff['clock'] = frame_clock
                    first_clock = clock
                else:
                    diff['clock'] = frame_clock + (clock - first_clock)
                rows.append(diff)
        df = pd.DataFrame(rows, columns=fieldnames, dtype=pd.Int64Dtype())
        for voicenum in voicenums:
            voicenum = self.normalize_voicenum(voicenum)
            if df['pulse%u' % voicenum].max() == 0:
                df['pw_duty%u' % voicenum] = np.nan
        hashid = hash(tuple(df.itertuples(index=False, name=None)))
        return (df, hashid)

    def _parsedf(self, voicenums):
        assert self.voicestates[0][3].gate
        for _, _, state, _ in self.voicestates:
            if state.mainreg.voice_filtered(self.voicenum):
                self.voice_filtered = True
                break
        first_event = self.voicestates[0]
        event_start, first_frame, first_state, _ = first_event
        last_clock = 0
        orig_diffs = defaultdict(list)
        last_state = None
        for clock, frame, state, voicestate in self.voicestates:
            rel_clock = clock - last_clock
            curr_waveforms = voicestate.flat_waveforms()
            for waveform in curr_waveforms:
                self.waveforms[waveform] += rel_clock
            if not self.waveform_order or self.waveform_order[-1] != curr_waveforms:
                self.waveform_order.append(curr_waveforms)
            if last_state:
                diff = {}
                for voicenum in voicenums:
                    voicestate_now = state.voices[voicenum]
                    last_voicestate = last_state.voices[voicenum]
                    voice_diff = voicestate_now.diff(last_voicestate)
                    voice_diff = {'%s%u' % (k, self.normalize_voicenum(voicenum)): v for k, v in voice_diff.items()}
                    diff.update(voice_diff)
                if self.voice_filtered:
                    filter_diff = state.mainreg.diff_filter_vol(self.voicenum, last_state.mainreg)
                    flt_v_key = 'flt%u' % self.voicenum
                    val = filter_diff.get(flt_v_key, None)
                    if val is not None:
                        del filter_diff[flt_v_key]
                        filter_diff['flt%u' % self.normalize_voicenum(self.voicenum)] = val
                    diff.update(filter_diff)
                frame_clock = (frame - first_frame) * self.sid.clockq
                orig_diffs[frame_clock].append((clock, diff))
            last_clock = clock
            last_state = state

        self.noisephases = len([waveforms for waveforms in self.waveform_order if 'noise' in waveforms])
        self.all_noise = set(self.waveforms.keys()) == {'noise'}

        first_row = {'clock': 0}
        fieldnames = ['clock']
        if first_state:
            for voicenum in voicenums:
                voicestate = first_state.voices[voicenum]
                for field in voicestate.voice_regs:
                    val = getattr(voicestate, field)
                    field = '%s%u' % (field, self.normalize_voicenum(voicenum))
                    fieldnames.append(field)
                    first_row[field] = val
            flt_v_key = 'flt%u' % self.normalize_voicenum(self.voicenum)
            fieldnames.append(flt_v_key)
            for field in first_state.mainreg.filter_common + ['vol']:
                val = getattr(first_state.mainreg, field)
                fieldnames.append(field)
                first_row[field] = val
            first_row[flt_v_key] = getattr(first_state.mainreg, 'flt%u' % self.voicenum)
        return (fieldnames, first_row, orig_diffs)

    def parse(self):
        self.trim_gateoff()
        audible_voicenums = set().union(*[state.audible_voicenums() for _, _, state, _ in self.voicestates])
        if self.voicenum not in audible_voicenums:
            return
        self.midi_notes = tuple(self.smf.get_midi_notes_from_events(self.sid, self.voicestates))
        if not self.midi_notes:
            return
        synced_voicenums = set().union(*[voicestate.synced_voicenums() for _, _, _, voicestate in self.voicestates])
        voicenums = {self.voicenum}.union(synced_voicenums)
        assert len(voicenums) in (1, 2)
        self.midi_pitches = tuple([midi_note[1] for midi_note in self.midi_notes])
        self.total_duration = sum(duration for _, _, duration, _, _ in self.midi_notes)
        self.max_midi_note = max(self.midi_pitches)
        self.min_midi_note = min(self.midi_pitches)
        fieldnames, first_row, orig_diffs = self._parsedf(voicenums)
        df, hashid = self._patchcsv(voicenums, fieldnames, first_row, orig_diffs)
        if hashid not in self.patch_count:
            if len(voicenums) == 1:
                self.single_patches[hashid] = df
            else:
                self.multi_patches[hashid] = df
        self.patch_count[hashid] += 1

    def descending_pitches(self):
        return len(self.midi_pitches) > 2 and self.midi_pitches[0] > self.midi_pitches[-1]

    def smf_transcribe(self):
        if self.noisephases:
            if self.percussion:
                clock, _pitch, _duration, velocity, _ = self.midi_notes[0]

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
                self.smf.add_pitch(self.voicenum, clock, duration, pitch, velocity)
