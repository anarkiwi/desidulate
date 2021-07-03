#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

# https://codebase64.org/doku.php?id=base:building_a_music_routine
# http://www.ucapps.de/howto_sid_wavetables_1.html

from collections import Counter, defaultdict
import pandas as pd
from fileio import out_path
from sidmidi import ELECTRIC_SNARE, BASS_DRUM, LOW_TOM, PEDAL_HIHAT, CLOSED_HIHAT, OPEN_HIHAT, ACCOUSTIC_SNARE, CRASH_CYMBAL1


def waveform_state(ssf):
    return [frozenset(
        waveform[:-1] for waveform in ('noise1', 'pulse1', 'tri1', 'saw1') if pd.notna(getattr(row, waveform)) and getattr(row, waveform) > 0) for row in  ssf.itertuples()]


class SidSoundFragment:

    def __init__(self, percussion, sid, smf, df):
        self.df = df.fillna(method='ffill')
        self.percussion = percussion
        waveform_states = waveform_state(df)
        self.midi_notes = tuple(smf.get_midi_notes_from_events(zip(self.df.itertuples(), waveform_states)))
        self.midi_pitches = []
        self.total_duration = 0
        self.max_midi_note = 0
        self.min_midi_note = 0
        self.initial_midi_pitches = []
        if self.midi_notes:
            self.midi_pitches = tuple([midi_note[1] for midi_note in self.midi_notes])
            self.initial_midi_pitches = tuple([midi_note[1] for midi_note in self.midi_notes if midi_note[0] < 2 * 1e5])
            self.total_duration = sum(duration for _, _, duration, _, _ in self.midi_notes)
            self.max_midi_note = max(self.midi_pitches)
            self.min_midi_note = min(self.midi_pitches)
        last_clock = 0
        self.waveforms = defaultdict(int)
        self.waveform_order = []
        for row, row_waveforms in zip(self.df.itertuples(), waveform_states):
            rel_clock = row.clock - last_clock
            for waveform in row_waveforms:
                self.waveforms[waveform] += rel_clock
            if ((self.waveform_order and self.waveform_order[-1] != row_waveforms) or
                  (not self.waveform_order and row_waveforms)):
                self.waveform_order.append(row_waveforms)
            last_clock = row.clock
        self.waveforms = frozenset(self.waveforms.keys())
        self.noisephases = len([waveforms for waveforms in self.waveform_order if 'noise' in waveforms])
        self.all_noise = self.waveforms == {'noise'}
        self.initial_pitch_drop = False
        if len(self.initial_midi_pitches) > 2:
            first_pitch = self.initial_midi_pitches[0]
            last_pitch = self.initial_midi_pitches[-1]
            if first_pitch > last_pitch and first_pitch - last_pitch > 12:
                self.initial_pitch_drop = True
        self.drum_pitches = []
        self.pitches = []
        self._set_pitches(sid)

    def drum_noise_duration(self, sid, duration):
        max_duration = sid.clockq
        noise_pitch = None
        for noise_pitch in (PEDAL_HIHAT, CLOSED_HIHAT, OPEN_HIHAT, ACCOUSTIC_SNARE, CRASH_CYMBAL1):
            if duration <= max_duration:
                break
            max_duration *= 2
        return noise_pitch

    def _set_pitches(self, sid):
        if not self.midi_notes:
            return
        clock, _pitch, _duration, velocity, _ = self.midi_notes[0]

        if self.noisephases or self.initial_pitch_drop:
            if self.percussion:
                if self.all_noise:
                    self.drum_pitches.append(
                        (clock, self.total_duration, self.drum_noise_duration(sid, self.total_duration), velocity))
                elif self.noisephases > 1:
                    self.drum_pitches.append(
                        (clock, self.total_duration, ELECTRIC_SNARE, velocity))
                else:
                    if self.initial_pitch_drop:
                        # http://www.ucapps.de/howto_sid_wavetables_1.html
                        self.drum_pitches.append(
                            (clock, self.total_duration, BASS_DRUM, velocity))
                    else:
                        self.drum_pitches.append(
                            (clock, self.total_duration, LOW_TOM, velocity))
        else:
            for clock, pitch, duration, velocity, _ in self.midi_notes:
                assert duration > 0, self.midi_notes
                self.pitches.append(
                    (clock, duration, pitch, velocity))

    def smf_transcribe(self, smf, first_clock, voicenum):
        for clock, duration, pitch, velocity in self.pitches:
            smf.add_pitch(voicenum, first_clock + clock, duration, pitch, velocity)
        for clock, duration, pitch, velocity in self.drum_pitches:
            smf.add_drum_pitch(voicenum, first_clock + clock, duration, pitch, velocity)


class SidSoundFragmentParser:

    def __init__(self, logfile, percussion, sid):
        self.logfile = logfile
        self.percussion = percussion
        self.sid = sid
        self.ssf_dfs = {}
        self.patch_count = Counter()

    def read_patches(self):
        patch_log = out_path(self.logfile, 'ssf.xz')
        ssfs_df = pd.read_csv(patch_log, dtype=pd.Int64Dtype())
        ssfs_df['real_freq'] = ssfs_df['freq1'] * self.sid.freq_scaler
        for hashid, ssf_df in ssfs_df.groupby('hashid', sort=False):
            self.patch_count[hashid] = ssf_df['count'].max()
            self.ssf_dfs[hashid] = ssf_df.drop(['hashid', 'count'], axis=1).astype(pd.UInt64Dtype())
