#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

# https://codebase64.org/doku.php?id=base:building_a_music_routine
# http://www.ucapps.de/howto_sid_wavetables_1.html

from collections import Counter, defaultdict
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

    def __init__(self, percussion, sid, smf, voicenum, event_start, events, single_patches, multi_patches, patch_count):
        self.percussion = percussion
        self.voicenum = voicenum
        self.sid = sid
        self.smf = smf
        self.event_start = event_start
        self.events = events
        self.waveforms = Counter()
        self.waveform_order = []
        self.noisephases = 0
        self.all_noise = False
        self.midi_notes = []
        self.midi_pitches = []
        self.voicestates = []
        self.voice_filtered = False
        self.total_duration = 0
        self.max_midi_note = 0
        self.min_midi_note = 0
        self.single_patches = single_patches
        self.multi_patches = multi_patches
        self.patch_count = patch_count

    def trim_gateoff(self):
        for i, clock_voicestate_state in enumerate(self.voicestates):
            _, voicestate, state = clock_voicestate_state
            if not voicestate.gate and not voicestate.rel:
                self.voicestates = self.voicestates[:i+1]
                break
            if state.mainreg.voice_filtered(self.voicenum):
                self.voice_filtered = True
        i = len(self.voicestates) - 1
        while i > 0 and self.voicestates[i][1].test:
            i -= 1
        if i:
            self.voicestates = self.voicestates[:i+2]

    def normalize_voicenum(self, voicenum):
        if voicenum == self.voicenum:
            return 1
        return 3

    def _patchcsv(self, fieldnames, first_row, orig_diffs):
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
        hashid = hash(tuple(df.itertuples(index=False, name=None)))
        return (df, hashid)

    def parse(self):
        audible_voicenums = set()
        synced_voicenums = set()
        for clock, _, state in self.events:
            voicestate = state.voices[self.voicenum]
            audible_voicenums = audible_voicenums.union(state.audible_voicenums())
            synced_voicenums = synced_voicenums.union(voicestate.synced_voicenums())
            self.voicestates.append((clock, voicestate, state))
        self.trim_gateoff()
        if self.voicenum in audible_voicenums:
            self.midi_notes = tuple(self.smf.get_midi_notes_from_events(self.sid, self.events))
            self.midi_pitches = tuple([midi_note[1] for midi_note in self.midi_notes])
            self.total_duration = sum(duration for _, _, duration, _, _ in self.midi_notes)
        if not self.midi_notes:
            return
        voicenums = {self.voicenum}.union(synced_voicenums)
        if len(voicenums) > 1:
            assert len(voicenums) == 2
        self.max_midi_note = max(self.midi_pitches)
        self.min_midi_note = min(self.midi_pitches)
        last_clock = None
        rel_clock = 0
        assert self.voicestates[0][1].gate
        orig_diffs = defaultdict(list)
        last_state = None
        first_state = None
        for clock, voicestate, state in self.voicestates:
            if last_clock is not None:
                rel_clock = clock - last_clock
            else:
                first_state = state
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
                clock_diff = clock - self.event_start
                frame_clock = self.sid.nearest_frame_clock(clock_diff)
                orig_diffs[frame_clock].append((clock, diff))
            last_clock = clock
            last_state = state

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

        df, hashid = self._patchcsv(fieldnames, first_row, orig_diffs)
        if len(voicenums) == 1:
            if hashid not in self.single_patches:
                self.single_patches[hashid] = df
        else:
            if hashid not in self.multi_patches:
                self.multi_patches[hashid] = df
        self.patch_count[hashid] += 1

        self.noisephases = len([waveforms for waveforms in self.waveform_order if 'noise' in waveforms])
        self.all_noise = set(self.waveforms.keys()) == {'noise'}


    def descending_pitches(self):
        return len(self.midi_pitches) > 2 and self.midi_pitches[0] > self.midi_pitches[-1]

    def smf_transcribe(self):
        # voicenum, clock, duration, pitch, velocity
        if self.noisephases:
            if self.percussion:
                if self.all_noise:
                    for clock, _pitch, duration, velocity, _ in self.midi_notes:
                        self.smf.add_drum_noise_duration(self.voicenum, clock, duration, velocity)
                elif self.noisephases > 1:
                    for clock, _pitch, _duration, velocity, _ in self.midi_notes:
                        self.smf.add_drum_pitch(self.voicenum, clock, self.total_duration, ELECTRIC_SNARE, velocity)
                else:
                    clock, _pitch, _dutation, velocity, _ = self.midi_notes[0]
                    if self.descending_pitches():
                        # http://www.ucapps.de/howto_sid_wavetables_1.html
                        self.smf.add_drum_pitch(self.voicenum, clock, self.total_duration, BASS_DRUM, velocity)
                    else:
                        self.smf.add_drum_pitch(self.voicenum, clock, self.total_duration, LOW_TOM, velocity)
        else:
            for clock, pitch, duration, velocity, _ in self.midi_notes:
                self.smf.add_pitch(self.voicenum, clock, duration, pitch, velocity)
