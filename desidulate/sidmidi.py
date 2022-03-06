# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

from collections import defaultdict
from functools import lru_cache
from music21 import midi

DEFAULT_BPM=125

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
HIGH_TOM = 50
LOW_TOM = 45
ACCOUSTIC_SNARE = 38
ELECTRIC_SNARE = 40
CRASH_CYMBAL1 = 49


def midi_args(parser):
    parser.add_argument('--bpm', default=DEFAULT_BPM, type=int, help='MIDI BPM')
    parser.add_argument('--percussion', dest='percussion', action='store_true')
    parser.add_argument('--no-percussion', dest='percussion', action='store_false')
    parser.set_defaults(pal=True, percussion=True)


def closest_midi(sid_f):
    closest_midi_f = min(MIDI_N_TO_F.values(), key=lambda x: abs(x - sid_f))
    return (closest_midi_f, MIDI_F_TO_N[closest_midi_f])


def make_event(track, event_type, channel):
    event = midi.MidiEvent(track)
    event.type = event_type
    event.channel = channel
    return event


def add_event(track, event, delta_clock, channel):
    dt = midi.DeltaTime(track)
    if delta_clock < 0 and delta_clock > -1:
        delta_clock = 0
    assert delta_clock >= 0, (track, event, delta_clock, channel)
    dt.time = round(delta_clock)
    dt.channel = channel
    track.events.append(dt)
    event.channel = channel
    track.events.append(event)
    if event.isNoteOn() or event.isNoteOff():
        return 1
    return 0


def add_end_of_track(track, channel):
    eot = make_event(track, midi.MetaEvents.END_OF_TRACK, channel)
    eot.data = b''
    add_event(track, eot, 0, channel)
    track.updateEvents()
    return track


def track_zero():
    return add_end_of_track(midi.MidiTrack(0), 0)


def write_midi(file_name, tpqn, tracks):
    smf = midi.MidiFile()
    smf.ticksPerQuarterNote = tpqn
    smf.tracks.append(track_zero())
    for track in tracks:
        smf.tracks.append(track)
    smf.open(file_name, 'wb')
    smf.write()
    smf.close()


def read_midi(file_name):
    input_mf = midi.MidiFile()
    input_mf.open(file_name)
    input_mf.read()
    input_mf.close()
    return input_mf


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
        self.one_4n_clocks = sid.qn_to_clock(1, self.bpm)
        self.one_2n_clocks = self.one_4n_clocks * 2
        self.one_8n_clocks = self.one_4n_clocks / 2
        self.one_16n_clocks = self.one_4n_clocks / 4

    @lru_cache
    def vel_scale(self, x, x_max):
        return int((x / x_max) * 127)

    @lru_cache
    def neg_vel_scale(self, x, x_max):
        return int((1.0 - (x / x_max)) * 127)

    @lru_cache
    def get_duration(self, clocks):
        return round(clocks / self.sid.clockq) * self.sid.clockq

    #@lru_cache
    def sid_adsr_to_velocity(self, clock, last_gate_clock, atk1, dec1, sus1, rel1, gate1):
        if gate1:
            attack_clock = self.sid.attack_clock[atk1]
            decay_clock = attack_clock + self.sid.decay_release_clock[dec1]
            if atk1 and clock < attack_clock:
                return self.vel_scale(clock, attack_clock)
            elif dec1 and clock < decay_clock:
                decay_time = clock - attack_clock
                return self.neg_vel_scale(decay_time, decay_clock)
            return self.sid_velocity[sus1]
        if last_gate_clock is not None:
            rel_clock = self.sid.decay_release_clock[rel1]
            rel_time = clock - last_gate_clock
            if rel_time < rel_clock:
                return self.neg_vel_scale(rel_time, rel_clock)
        return 0

    def clock_to_ticks(self, clock):
        return self.sid.clock_to_ticks(clock, self.bpm, self.tpqn)

    def add_note(self, track, channel, pitch, velocity, last_clock, clock, duration):
        note_on = make_event(track, midi.ChannelVoiceMessages.NOTE_ON, channel)
        note_on.pitch = pitch
        note_on.velocity = velocity
        add_event(track, note_on, self.clock_to_ticks(clock - last_clock), channel)
        note_off = make_event(track, midi.ChannelVoiceMessages.NOTE_OFF, channel)
        note_off.pitch = pitch
        note_off.velocity = 0
        add_event(track, note_off, self.clock_to_ticks(duration), channel)
        return clock + duration

    def add_program_change(self, track, channel, program):
        pc = make_event(track, midi.ChannelVoiceMessages.PROGRAM_CHANGE, channel)
        pc.data = program
        add_event(track, pc, 0, channel)

    def deoverlap_pitches(self, voice_pitch_data):
        deoverlapped = []
        if voice_pitch_data:
            clock_order = sorted(voice_pitch_data, key=lambda x: x[0])
            last_pitch_data = clock_order[-1]
            deoverlapped = []
            for i, pitch_data in enumerate(clock_order[:-1]):
                next_pitch_data = clock_order[i+1]
                clock, duration, pitch, velocity = pitch_data
                next_clock = next_pitch_data[0]
                duration = min(duration, next_clock - clock)
                assert duration > 0, (pitch_data, next_pitch_data)
                deoverlapped.append((clock, duration, pitch, velocity))
            deoverlapped.append(last_pitch_data)
        return deoverlapped

    def write_pitches(self, smf_track, channel, program, voice_pitch_data):
        track = midi.MidiTrack(smf_track)
        self.add_program_change(track, channel, program)
        last_clock = 0
        for pitch_data in self.deoverlap_pitches(voice_pitch_data):
            clock, duration, pitch, velocity = pitch_data
            assert velocity
            last_clock = self.add_note(track, channel, pitch, velocity, last_clock, clock, duration)
        add_end_of_track(track, channel)
        return track

    def write(self, file_name):
        track_pitches = []

        for voicenum, voice_pitch_data in self.pitches.items():
            if voice_pitch_data:
                track_pitches.append((None, self.program, voice_pitch_data))
        for voicenum, voice_pitch_data in self.drum_pitches.items():
            if voice_pitch_data:
                track_pitches.append((DRUM_CHANNEL, self.drum_program, voice_pitch_data))

        tracks = []
        for smf_track, pitches in enumerate(track_pitches, start=1):
            channel, program, voice_pitch_data = pitches
            if channel is None:
                channel = smf_track
            tracks.append(self.write_pitches(
                smf_track, channel, program, voice_pitch_data))
        write_midi(file_name, self.tpqn, tracks)

    def add_pitch(self, voicenum, clock, duration, pitch, velocity):
        assert duration > 0, duration
        self.pitches[voicenum].append((clock, duration, pitch, velocity))

    def add_drum_pitch(self, voicenum, clock, duration, pitch, velocity):
        assert duration > 0, duration
        self.drum_pitches[voicenum].append((clock, duration, pitch, velocity))

    def get_note_starts(self, row_states):
        last_note = None
        last_clock = None
        last_gate_clock = None
        notes_starts = []
        first_row = None
        for row, row_waveforms in row_states:
            clock = row.Index
            if first_row is None:
                first_row = row
            if row.gate1:
                last_gate_clock = clock
            if row_waveforms and not row.test1:
                # TODO: add pitch bend if significantly different to canonical note.
                # https://github.com/magenta/magenta/issues/1902
                if row.closest_note != last_note:
                    atk1, dec1, sus1, rel1 = (first_row.atk1, first_row.dec1, first_row.sus1, first_row.rel1)
                    velocity = self.sid_adsr_to_velocity(clock, last_gate_clock, atk1, dec1, sus1, rel1, row.gate1)
                    assert velocity >= 0 and velocity <= 127, (velocity, row)
                    if velocity:
                        notes_starts.append((clock, row.vbi_frame, int(row.closest_note), velocity, row.real_freq))
                        last_note = row.closest_note
            last_clock = clock
        notes_starts.append((last_clock, None, None, None, None))
        return notes_starts

    def get_notes(self, notes_starts):
        notes = []
        for i, note_clocks in enumerate(notes_starts[:-1]):
            clock, vbi_frame, note, velocity, sid_f = note_clocks
            next_clock = notes_starts[i + 1][0]
            duration = self.get_duration(next_clock - clock)
            if duration:
                notes.append((clock, vbi_frame, note, duration, velocity, sid_f))
        return notes

    # Convert gated voice events into possibly many MIDI notes
    def get_midi_notes_from_events(self, row_states):
        notes_starts = self.get_note_starts(row_states)
        notes = self.get_notes(notes_starts)
        return notes
