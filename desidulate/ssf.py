#!/usr/bin/python3

# Copyright 2020-2022 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

# https://codebase64.org/doku.php?id=base:building_a_music_routine
# http://www.ucapps.de/howto_sid_wavetables_1.html

from collections import Counter
from itertools import groupby
import pandas as pd
from desidulate.fileio import out_path, read_csv
from desidulate.sidlib import set_sid_dtype, resampledf_to_pr
from desidulate.sidmidi import closest_midi, MEMBRANE_DRUM_MAP, CYMBAL_DRUMS
from desidulate.sidwav import state2samples, samples_loudestf, readwav

INITIAL_FRAMES = 4


def add_freq_notes_df(sid, ssfs_df):
    real_freqs = {
        freq: freq * sid.freq_scaler for freq in ssfs_df['freq1'].unique() if pd.notna(freq)}
    closest_notes = {
        real_freq: closest_midi(real_freq)[1] for real_freq in real_freqs.values()}
    freq_map = [
        (freq, real_freq, closest_notes[real_freq]) for freq, real_freq in real_freqs.items()]
    freq_map.extend([(pd.NA, pd.NA, pd.NA)])
    freq_notes_df = pd.DataFrame.from_records(
        freq_map, columns=['freq1', 'real_freq', 'closest_note']).astype(pd.Float64Dtype())
    freq_notes_df['freq1'] = freq_notes_df['freq1'].astype(pd.UInt16Dtype())
    freq_notes_df['closest_note'] = freq_notes_df['closest_note'].astype(pd.UInt8Dtype())
    return set_sid_dtype(ssfs_df).merge(freq_notes_df, how='left', on='freq1')


class SidSoundFragment:

    @staticmethod
    def _waveform_state(ssf):
        return [frozenset(
            waveform[:-1] for waveform in ('noise1', 'pulse1', 'tri1', 'saw1')
            if pd.notna(getattr(row, waveform)) and getattr(row, waveform) > 0)
                for row in ssf.itertuples()]

    def __init__(self, percussion, sid, df, smf, wav_file=None, initial_frames=INITIAL_FRAMES):
        self.df = resampledf_to_pr(df)
        self.initial_clocks = sid.clockq * (initial_frames + 1)
        self.percussion = percussion
        waveform_states = self._waveform_state(self.df)
        self.waveform_order = tuple([frozenset(i[0]) for i in groupby(waveform_states)])
        self.waveforms = frozenset().union(*self.waveform_order)
        self.noisephases = len([waveforms for waveforms in self.waveform_order if 'noise' in waveforms])
        self.pulsephases = len([waveforms for waveforms in self.waveform_order if 'pulse' in waveforms])
        self.all_noise = self.waveforms == {'noise'}
        self.midi_notes = tuple(smf.get_midi_notes_from_events(zip(self.df.itertuples(), waveform_states)))
        self.midi_pitches = tuple([midi_note[1] for midi_note in self.midi_notes])
        self.total_duration = 0
        self.max_midi_note = 0
        self.min_midi_note = 0
        self.initial_midi_notes = []
        self.initial_midi_pitches = []
        if self.midi_notes:
            self.initial_midi_notes = tuple(
                [midi_note for midi_note in self.midi_notes if midi_note[0] < self.initial_clocks])
            self.initial_midi_pitches = tuple(
                [midi_note[1] for midi_note in self.initial_midi_notes])
            self.total_duration = sum(
                [midi_note[2] for midi_note in self.midi_notes])
            self.max_midi_note = max(self.midi_pitches)
            self.min_midi_note = min(self.midi_pitches)
        self.initial_pitch_drop = 0
        if len(self.initial_midi_pitches) >= 2:
            first_pitch = self.initial_midi_pitches[0]
            last_pitch = self.initial_midi_pitches[-1]
            pitch_diff = round((first_pitch - last_pitch) / 12)
            if first_pitch > last_pitch and pitch_diff:
                self.initial_pitch_drop = pitch_diff
        self.drum_pitches = []
        self.pitches = []
        self.drum_instrument = pd.NA
        self.loudestf = 0
        self.total_clocks = self.df.index[-1]
        self.one_2n_clocks = smf.one_2n_clocks
        self.one_4n_clocks = smf.one_4n_clocks
        self.one_8n_clocks = smf.one_8n_clocks
        self.one_16n_clocks = smf.one_16n_clocks
        if wav_file is not None:
            rate, samples = readwav(wav_file)
            max_samples = int(sid.clock_to_s(self.initial_clocks) * rate)
            self.samples = samples[:max_samples]
        else:
            rate = sid.resid.sampling_frequency
            self.samples = state2samples(self.df, sid, skiptest=True, maxclock=self.one_2n_clocks)
        if len(self.samples):
            self.loudestf = samples_loudestf(self.samples, rate)
            self._set_pitches(sid)
            if self.drum_pitches:
                self.drum_instrument = self.drum_pitches[0][2]
        else:
            self._set_nondrum_pitches()

    @staticmethod
    def drum_noise_duration(sid, duration):
        max_duration = sid.clockq
        noise_pitch = None
        for noise_pitch in CYMBAL_DRUMS:
            if duration <= max_duration:
                break
            max_duration *= 2
        return noise_pitch

    def _set_nondrum_pitches(self):
        for clock, pitch, duration, velocity, _ in self.midi_notes:
            assert duration > 0, self.midi_notes
            self.pitches.append((clock, duration, pitch, velocity))

    def _set_pitches(self, sid):
        if not self.midi_notes:
            return

        # Percussion must be no longer than one half note.
        if self.total_clocks <= self.one_2n_clocks:
            clock, _pitch, _duration, velocity, _ = self.midi_notes[0]

            # TODO: pitched noise percussion.
            if self.all_noise or self.noisephases > 1:
                self.drum_pitches.append(
                    (clock, self.total_duration, self.drum_noise_duration(sid, self.total_duration), velocity))
                return

            # Membrane percussion must be no longer than 1 quarter note.
            if self.total_clocks <= self.one_4n_clocks:
                if self.noisephases == 1 or self.initial_pitch_drop > 2:
                    for drum, drum_cutoff_hz in MEMBRANE_DRUM_MAP:
                        if self.loudestf < drum_cutoff_hz:
                            # http://www.ucapps.de/howto_sid_wavetables_1.html
                            self.drum_pitches.append(
                                (clock, self.total_duration, drum, velocity))
                            return

        self._set_nondrum_pitches()

    def smf_transcribe(self, smf, first_clock, voicenum):
        for clock, duration, pitch, velocity in self.pitches:
            smf.add_pitch(voicenum, first_clock + clock, duration, pitch, velocity)
        if self.percussion:
            for clock, duration, pitch, velocity in self.drum_pitches:
                smf.add_drum_pitch(voicenum, first_clock + clock, duration, pitch, velocity)

    def instrument(self, base_instrument):
        base_instrument.update({
            'drum_instrument': self.drum_instrument,
            'samples': len(self.samples),
            'loudestf': self.loudestf,
            'last_clock': self.df.index[-1],
            'initial_pitch_drop': self.initial_pitch_drop})
        return base_instrument


class SidSoundFragmentParser:

    def __init__(self, logfile, percussion, sid):
        self.logfile = logfile
        self.percussion = percussion
        self.sid = sid
        self.ssf_dfs = {}
        self.patch_count = Counter()

    def read_patches(self, dfext):
        patch_log = out_path(self.logfile, '.'.join(('ssf', dfext)))
        ssfs_df = add_freq_notes_df(self.sid, read_csv(patch_log, dtype=pd.Int64Dtype()))
        for hashid, ssf_df in ssfs_df.groupby('hashid', sort=False):
            self.patch_count[hashid] = ssf_df['count'].max()
            self.ssf_dfs[hashid] = ssf_df.drop(
                ['hashid', 'count'], axis=1).set_index('clock').fillna(method='ffill')
