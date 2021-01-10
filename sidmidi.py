# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.


from collections import defaultdict
from midiutil import MIDIFile
from sidlib import real_sid_freq, clock_to_qn


A = 440
MIDI_N_TO_F = {n: (A / 32) * (2 ** ((n - 9) / 12)) for n in range(128)}
MIDI_F_TO_N = {f: n for n, f in MIDI_N_TO_F.items()}
DRUM_CHANNEL = 9
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

    def __init__(self, sid, bpm, clockq, program=81, drum_program=0):
        self.sid = sid
        self.bpm = bpm
        self.clockq = clockq
        self.program = program
        self.drum_program = drum_program
        self.pitches = defaultdict(list)
        self.drum_pitches = defaultdict(list)

    def write_pitches(self, smf, smf_track, channel, program, voice_pitch_data):
        smf.addTempo(smf_track, time=0, tempo=self.bpm)
        smf.addProgramChange(smf_track, channel, time=0, program=program)
        for pitch_data in voice_pitch_data:
            pitch, qn_clock, qn_duration, velocity = pitch_data
            assert velocity
            smf.addNote(smf_track, channel, pitch, qn_clock, qn_duration, velocity)

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
        smf = MIDIFile(tracks)
        for voicenum, voice_pitch_data in self.pitches.items():
            if voice_pitch_data:
                channel = trackmap[voicenum]
                smf_track = channel - 1
                self.write_pitches(smf, smf_track, channel, self.program, voice_pitch_data)
        for voicenum, voice_pitch_data in self.drum_pitches.items():
            if voice_pitch_data:
                smf_track = drummap[voicenum] - 1
                self.write_pitches(smf, smf_track, DRUM_CHANNEL, self.drum_program, voice_pitch_data)
        with open(file_name, 'wb') as midi_f:
            smf.writeFile(midi_f)

    def closest_midi(self, sid_f):
        closest_midi_f = min(MIDI_N_TO_F.values(), key=lambda x: abs(x - sid_f))
        return (closest_midi_f, MIDI_F_TO_N[closest_midi_f])

    def add_pitch(self, clock, pitch, velocity, duration, voicenum):
        qn_clock = clock_to_qn(self.sid, clock, self.bpm)
        qn_duration = clock_to_qn(self.sid, duration, self.bpm)
        self.pitches[voicenum].append((pitch, qn_clock, qn_duration, velocity))

    def add_drum_pitch(self, clock, pitch, velocity, duration, voicenum):
        qn_clock = clock_to_qn(self.sid, clock, self.bpm)
        qn_duration = clock_to_qn(self.sid, duration, self.bpm)
        self.drum_pitches[voicenum].append((pitch, qn_clock, qn_duration, velocity))

    def add_drum_noise_duration(self, clock, velocity, duration, voicenum):
        max_duration = self.clockq
        noise_pitch = None
        for noise_pitch in (PEDAL_HIHAT, CLOSED_HIHAT, OPEN_HIHAT, ACCOUSTIC_SNARE, CRASH_CYMBAL1):
            if duration <= max_duration:
                break
            max_duration *= 2
        self.add_drum_pitch(clock, noise_pitch, velocity, duration, voicenum)

    def sid_adsr_to_velocity(self, voice_state):
        vel_nib = voice_state.sustain
        # Sustain approximates velocity, but if it's 0, then go with decay.
        if vel_nib == 0:
            # assert voice_state.attack == 0
            vel_nib = voice_state.decay
        velocity = int(vel_nib / 15 * 127)
        return velocity

    # Convert gated voice events into possibly many MIDI notes
    def get_midi_notes_from_events(self, sid, events, clockq):
        last_midi_n = None
        notes_starts = []
        for clock, regevent, state in events:
            clock = int(clock / clockq) * clockq
            voicenum = regevent.voicenum
            voice_state = state.voices[voicenum]
            sid_f = real_sid_freq(sid, voice_state.frequency)
            _closest_midi_f, closest_midi_n = self.closest_midi(sid_f)
            velocity = self.sid_adsr_to_velocity(voice_state)
            # TODO: add pitch bend if significantly different to canonical note.
            if closest_midi_n != last_midi_n and voice_state.any_waveform() and velocity:
                notes_starts.append((closest_midi_n, clock, sid_f, velocity))
                last_midi_n = closest_midi_n
            last_clock = clock
        notes = []
        for i, note_clocks in enumerate(notes_starts):
            note, clock, sid_f, velocity = note_clocks
            try:
                next_clock = notes_starts[i + 1][1]
            except IndexError:
                next_clock = last_clock
            duration = next_clock - clock
            if not duration:
                continue
            duration = round(duration / clockq) * clockq
            notes.append((clock, note, duration, velocity, sid_f))
        return notes
