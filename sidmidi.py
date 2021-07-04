# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

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

def closest_midi(sid_f):
    closest_midi_f = min(MIDI_N_TO_F.values(), key=lambda x: abs(x - sid_f))
    return (closest_midi_f, MIDI_F_TO_N[closest_midi_f])


class SidMidiFile:

    def __init__(self, sid, bpm, program=81, drum_program=0):
        self.sid = sid
        self.bpm = bpm
        self.program = program
        self.drum_program = drum_program
        self.pitches = defaultdict(list)
        self.drum_pitches = defaultdict(list)
        self.tpqn = 960
        self.sid_velocity = {i: int(i / 15 * 127) for i in range(16)}

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

    def add_pitch(self, voicenum, clock, duration, pitch, velocity):
        assert duration > 0, duration
        self.pitches[voicenum].append((clock, duration, pitch, velocity))

    def add_drum_pitch(self, voicenum, clock, duration, pitch, velocity):
        assert duration > 0, duration
        self.drum_pitches[voicenum].append((clock, duration, pitch, velocity))

    @lru_cache
    def vel_scale(self, x, x_max):
        return int((x / x_max) * 127)

    @lru_cache
    def neg_vel_scale(self, x, x_max):
        return int((1.0 - (x / x_max)) * 127)

    def sid_adsr_to_velocity(self, row, last_rel, last_gate_clock):
        if row.gate1:
            attack_clock = self.sid.attack_clock[row.atk1]
            if row.clock < attack_clock:
                return self.vel_scale(row.clock, attack_clock)
            decay_clock = self.sid.decay_release_clock[row.dec1]
            if row.clock < attack_clock + decay_clock:
                return self.neg_vel_scale(row.clock - attack_clock, decay_clock)
            return self.sid_velocity[row.sus1]
        rel_clock = self.sid.decay_release_clock[last_rel]
        if row.clock - last_gate_clock <= rel_clock:
            return self.neg_vel_scale(row.clock - last_gate_clock, rel_clock)
        return 0

    def get_sounding(self, row_states):
        for row, row_waveforms in row_states:
            if row_waveforms and row.vol and not row.test1:
                yield (row, row_waveforms)
                break
        for row, row_waveforms in row_states:
            yield (row, row_waveforms)

    def get_note_starts(self, row_states):
        last_note = None
        last_clock = None
        last_rel = None
        last_gate_clock = None
        notes_starts = []
        for row, row_waveforms in self.get_sounding(row_states):
            if row.gate1:
                last_rel = row.rel1
                last_gate_clock = row.clock
            if row_waveforms:
                # TODO: add pitch bend if significantly different to canonical note.
                # https://github.com/magenta/magenta/issues/1902
                if row.closest_note != last_note:
                    velocity = self.sid_adsr_to_velocity(row, last_rel, last_gate_clock)
                    if velocity:
                        notes_starts.append((row.clock, int(row.closest_note), velocity, row.real_freq))
                        last_note = row.closest_note
            last_clock = row.clock
        notes_starts.append((last_clock, None, None, None))
        return notes_starts

    @lru_cache
    def get_duration(self, clocks):
        return round(clocks / self.sid.clockq) * self.sid.clockq

    def get_notes(self, notes_starts):
        notes = []
        for i, note_clocks in enumerate(notes_starts[:-1]):
            clock, note, velocity, sid_f = note_clocks
            next_clock = notes_starts[i + 1][0]
            duration = self.get_duration(next_clock - clock)
            if duration:
                notes.append((clock, note, duration, velocity, sid_f))
        return notes

    # Convert gated voice events into possibly many MIDI notes
    def get_midi_notes_from_events(self, row_states):
        notes_starts = self.get_note_starts(row_states)
        notes = self.get_notes(notes_starts)
        return notes
