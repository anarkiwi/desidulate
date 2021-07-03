# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import pandas as pd
from collections import defaultdict
from functools import lru_cache
from music21 import midi


A = 440
MIDI_N_TO_F = {n: (A / 32) * (2 ** ((n - 9) / 12)) for n in range(128)}
MIDI_F_TO_N = {f: n for n, f in MIDI_N_TO_F.items()}
DRUM_CHANNEL = 10
VOICES = 3

# https://en.wikipedia.org/wiki/General_MIDI#Percussion
BASS_DRUM = 36
PEDAL_HIHAT = 44
CLOSED_HIHAT = 42
OPEN_HIHAT = 46
HI_TOM = 50
LOW_TOM = 45
ACCOUSTIC_SNARE = 38
ELECTRIC_SNARE = 40
CRASH_CYMBAL1 = 49


class SidMidiFile:

    def __init__(self, sid, bpm, program=81, drum_program=0):
        self.sid = sid
        self.bpm = bpm
        self.program = program
        self.drum_program = drum_program
        self.pitches = defaultdict(list)
        self.drum_pitches = defaultdict(list)
        self.tpqn = 960

    def make_event(self, track, event_type, channel):
        event = midi.MidiEvent(track)
        event.type = event_type
        event.channel = channel
        return event

    def add_event(self, track, event, delta_clock, channel):
        dt = midi.DeltaTime(track)
        if delta_clock < 0 and delta_clock > -1:
            delta_clock = 0
        assert delta_clock >= 0, (track, event, delta_clock, channel)
        dt.time = round(delta_clock)
        dt.channel = channel
        track.events.append(dt)
        event.channel = channel
        track.events.append(event)

    def add_end_of_track(self, track, channel):
        eot = self.make_event(track, midi.MetaEvents.END_OF_TRACK, channel)
        eot.data = b''
        self.add_event(track, eot, 0, channel)
        track.updateEvents()

    def clock_to_ticks(self, clock):
        return self.sid.clock_to_ticks(clock, self.bpm, self.tpqn)

    def add_note(self, track, channel, pitch, velocity, last_clock, clock, duration):
        note_on = self.make_event(track, midi.ChannelVoiceMessages.NOTE_ON, channel)
        note_on.pitch = pitch
        note_on.velocity = velocity
        self.add_event(track, note_on, self.clock_to_ticks(clock - last_clock), channel)
        note_off = self.make_event(track, midi.ChannelVoiceMessages.NOTE_OFF, channel)
        note_off.pitch = pitch
        note_off.velocity = 0
        self.add_event(track, note_off, self.clock_to_ticks(duration), channel)
        return clock + duration

    def add_program_change(self, track, channel, program):
        pc = self.make_event(track, midi.ChannelVoiceMessages.PROGRAM_CHANGE, channel)
        pc.data = program
        self.add_event(track, pc, 0, channel)

    def write_pitches(self, smf_track, channel, program, voice_pitch_data):
        track = midi.MidiTrack(smf_track)
        self.add_program_change(track, channel, program)
        last_pitch_data = tuple()
        deoverlapped = []
        for pitch_data in sorted(voice_pitch_data, key=lambda x: x[0]):
            if last_pitch_data:
                last_clock, last_duration, last_pitch, last_velocity = last_pitch_data
                assert last_duration > 0, (last_pitch_data, pitch_data)
                clock, _, _, _ = pitch_data
                last_duration = min(last_duration, clock - last_clock)
                assert last_duration > 0, (last_duration, clock, last_clock, clock - last_clock)
                deoverlapped.append((last_clock, last_duration, last_pitch, last_velocity))
            last_pitch_data = pitch_data
        if deoverlapped:
            deoverlapped.append(last_pitch_data)
        last_clock = 0
        for pitch_data in deoverlapped:
            clock, duration, pitch, velocity = pitch_data
            assert velocity
            last_clock = self.add_note(track, channel, pitch, velocity, last_clock, clock, duration)
        self.add_end_of_track(track, channel)
        return track

    def write(self, file_name):
        trackmap = {}
        drummap = {}
        tracks = 0
        for voicenum, voice_pitch_data in self.pitches.items():
            if voice_pitch_data:
                tracks += 1
                trackmap[voicenum] = tracks
        for voicenum, voice_pitch_data in self.drum_pitches.items():
            if voice_pitch_data:
                tracks += 1
                drummap[voicenum] = tracks
        smf = midi.MidiFile()
        smf.ticksPerQuarterNote = self.tpqn
        smf.tracks.append(midi.MidiTrack(0))
        for voicenum, voice_pitch_data in self.pitches.items():
            if voice_pitch_data:
                channel = trackmap[voicenum]
                smf_track = channel - 1
                smf.tracks.append(self.write_pitches(
                    smf_track, channel, self.program, voice_pitch_data))
        for voicenum, voice_pitch_data in self.drum_pitches.items():
            if voice_pitch_data:
                smf_track = drummap[voicenum] - 1
                smf.tracks.append(self.write_pitches(
                    smf_track, DRUM_CHANNEL, self.drum_program, voice_pitch_data))
        smf.open(file_name, 'wb')
        smf.write()

    @lru_cache
    def closest_midi(self, sid_f):
        closest_midi_f = min(MIDI_N_TO_F.values(), key=lambda x: abs(x - sid_f))
        return (closest_midi_f, MIDI_F_TO_N[closest_midi_f])

    def add_pitch(self, voicenum, clock, duration, pitch, velocity):
        assert duration > 0, duration
        self.pitches[voicenum].append((clock, duration, pitch, velocity))

    def add_drum_pitch(self, voicenum, clock, duration, pitch, velocity):
        assert duration > 0, duration
        self.drum_pitches[voicenum].append((clock, duration, pitch, velocity))

    def sid_adsr_to_velocity(self, row):
        vel_nib = row.sus1
        if pd.isna(vel_nib):
            vel_nib = 15
        # Sustain approximates velocity, but if it's 0, then go with dec.
        # TODO: could use time in atk?
        if vel_nib == 0:
            # assert voice_state.atk == 0
            vel_nib = row.dec1
        velocity = int(vel_nib / 15 * 127)
        return velocity

    def get_note_starts(self, row_states):
        last_midi_n = None
        notes_starts = []
        last_clock = None
        sounding = False
        for row, row_waveforms in row_states:
            if not sounding:
                if row_waveforms and row.vol and not row.test1:
                    sounding = True
                else:
                    continue
            sid_f = row.real_freq
            _, closest_midi_n = self.closest_midi(sid_f)
            # TODO: add pitch bend if significantly different to canonical note.
            if closest_midi_n != last_midi_n and row_waveforms:
                velocity = self.sid_adsr_to_velocity(row)
                if velocity:
                    notes_starts.append((closest_midi_n, row.clock, sid_f, velocity))
                    last_midi_n = closest_midi_n
            last_clock = row.clock
        return notes_starts, last_clock

    @lru_cache
    def get_duration(self, clock, next_clock):
        return round((next_clock - clock) / self.sid.clockq) * self.sid.clockq

    def get_notes(self, notes_starts, last_clock):
        notes = []
        for i, note_clocks in enumerate(notes_starts):
            note, clock, sid_f, velocity = note_clocks
            try:
                next_clock = notes_starts[i + 1][1]
            except IndexError:
                next_clock = last_clock
            duration = self.get_duration(clock, next_clock)
            if duration:
                notes.append((clock, note, duration, velocity, sid_f))
        return notes

    # Convert gated voice events into possibly many MIDI notes
    def get_midi_notes_from_events(self, row_states):
        notes_starts, last_clock = self.get_note_starts(row_states)
        notes = self.get_notes(notes_starts, last_clock)
        return notes
