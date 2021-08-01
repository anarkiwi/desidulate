#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

# https://codebase64.org/doku.php?id=base:building_a_music_routine
# http://www.ucapps.de/howto_sid_wavetables_1.html

from collections import Counter
from itertools import groupby
import pandas as pd
from fileio import out_path
from sidlib import set_sid_dtype
from sidmidi import ELECTRIC_SNARE, BASS_DRUM, LOW_TOM, PEDAL_HIHAT, CLOSED_HIHAT, OPEN_HIHAT, ACCOUSTIC_SNARE, CRASH_CYMBAL1, closest_midi


class SidSoundFragment:

    @staticmethod
    def _waveform_state(ssf):
        return [frozenset(
            waveform[:-1] for waveform in ('noise1', 'pulse1', 'tri1', 'saw1') if pd.notna(getattr(row, waveform)) and getattr(row, waveform) > 0) for row in ssf.itertuples()]

    def __init__(self, percussion, sid, smf, df):
        self.df = df.fillna(method='ffill')
        self.percussion = percussion
        waveform_states = self._waveform_state(self.df)
        self.waveform_order = tuple([frozenset(i[0]) for i in groupby(waveform_states)])
        self.waveforms = frozenset().union(*self.waveform_order)
        self.noisephases = len([waveforms for waveforms in self.waveform_order if 'noise' in waveforms])
        self.all_noise = self.waveforms == {'noise'}
        self.midi_notes = tuple(smf.get_midi_notes_from_events(zip(self.df.itertuples(), waveform_states)))
        self.midi_pitches = tuple([midi_note[2] for midi_note in self.midi_notes])
        self.total_duration = 0
        self.max_midi_note = 0
        self.min_midi_note = 0
        self.initial_midi_pitches = []
        if self.midi_notes:
            self.initial_midi_pitches = tuple([midi_note[2] for midi_note in self.midi_notes if midi_note[1] <= 2])
            self.total_duration = sum(duration for _, _, _, duration, _, _ in self.midi_notes)
            self.max_midi_note = max(self.midi_pitches)
            self.min_midi_note = min(self.midi_pitches)
        self.initial_pitch_drop = 0
        if len(self.initial_midi_pitches) > 2:
            first_pitch = self.initial_midi_pitches[0]
            last_pitch = self.initial_midi_pitches[-1]
            pitch_diff = round((first_pitch - last_pitch) / 12)
            if (first_pitch > last_pitch and
                    pitch_diff and
                    tuple(sorted(self.initial_midi_pitches, reverse=True)) == self.initial_midi_pitches):
                self.initial_pitch_drop = pitch_diff
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
        clock, _frame, _pitch, _duration, velocity, _ = self.midi_notes[0]

        if not (self.noisephases or self.initial_pitch_drop):
            for clock, _frame, pitch, duration, velocity, _ in self.midi_notes:
                assert duration > 0, self.midi_notes
                self.pitches.append(
                    (clock, duration, pitch, velocity))
            return

        if not self.percussion:
            return

        # TODO: pitched percussion.
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

    def smf_transcribe(self, smf, first_clock, voicenum):
        for clock, duration, pitch, velocity in self.pitches:
            smf.add_pitch(voicenum, first_clock + clock, duration, pitch, velocity)
        for clock, duration, pitch, velocity in self.drum_pitches:
            smf.add_drum_pitch(voicenum, first_clock + clock, duration, pitch, velocity)


def add_freq_notes_df(sid, ssfs_df):
    real_freqs = {freq: freq * sid.freq_scaler for freq in ssfs_df['freq1'].unique() if pd.notna(freq)}
    closest_notes = {real_freq: closest_midi(real_freq)[1] for real_freq in real_freqs.values()}
    freq_map = [(freq, real_freq, closest_notes[real_freq]) for freq, real_freq in real_freqs.items()]
    freq_map.extend([(pd.NA, pd.NA, pd.NA)])
    freq_notes_df = pd.DataFrame.from_records(freq_map, columns=['freq1', 'real_freq', 'closest_note']).astype(pd.Float64Dtype())
    freq_notes_df['freq1'] = freq_notes_df['freq1'].astype(pd.UInt16Dtype())
    freq_notes_df['closest_note'] = freq_notes_df['closest_note'].astype(pd.UInt8Dtype())
    return set_sid_dtype(ssfs_df).merge(freq_notes_df, how='left', on='freq1')


class SidSoundFragmentParser:

    def __init__(self, logfile, percussion, sid):
        self.logfile = logfile
        self.percussion = percussion
        self.sid = sid
        self.ssf_dfs = {}
        self.patch_count = Counter()

    def read_patches(self):
        patch_log = out_path(self.logfile, 'ssf.xz')
        ssfs_df = add_freq_notes_df(self.sid, pd.read_csv(patch_log, dtype=pd.Int64Dtype()))
        for hashid, ssf_df in ssfs_df.groupby('hashid', sort=False):
            self.patch_count[hashid] = ssf_df['count'].max()
            self.ssf_dfs[hashid] = ssf_df.drop(['hashid', 'count'], axis=1)
