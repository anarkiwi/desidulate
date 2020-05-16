# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.


from midiutil import MIDIFile
from sidlib import real_sid_freq

A = 440
MIDI_N_TO_F = {n: (A / 32) * (2 ** ((n - 9) / 12)) for n in range(128)}
MIDI_F_TO_N = {f: n for n, f in MIDI_N_TO_F.items()}
DRUM_TRACK_OFFSET = 2
DRUM_CHANNEL = 9
VOICES = 3


def get_midi_file(bpm, program=81):
    midi_file = MIDIFile(VOICES * 2)
    for i in range(1, VOICES + 1):
        midi_file.addTempo(i, time=0, tempo=bpm)
        midi_file.addProgramChange(i-1, i, time=0, program=program)
        midi_file.addTempo(i + DRUM_TRACK_OFFSET, time=0, tempo=bpm)
    return midi_file


def closest_midi(sid_f):
    closest_midi_f = min(MIDI_N_TO_F.values(), key=lambda x: abs(x - sid_f))
    return (closest_midi_f, MIDI_F_TO_N[closest_midi_f])


# Convert gated voice events into possibly many MIDI notes
def get_midi_notes_from_events(sid, events, clockq):
    last_midi_n = None
    notes_starts = []
    for clock, regevent, state in events:
        clock = round(clock / clockq) * clockq
        voicenum = regevent.voicenum
        voice_state = state.voices[voicenum]
        sid_f = real_sid_freq(sid, voice_state.frequency)
        _closest_midi_f, closest_midi_n = closest_midi(sid_f)
        # TODO: add pitch bend if significantly different to canonical note.
        if closest_midi_n != last_midi_n and voice_state.any_waveform():
            notes_starts.append((closest_midi_n, clock, sid_f))
        last_clock = clock
    notes = []
    for i, note_clocks in enumerate(notes_starts):
        note, clock, sid_f = note_clocks
        try:
            next_clock = notes_starts[i + 1][1]
        except IndexError:
            next_clock = last_clock
        duration = next_clock - clock
        if not duration:
            continue
        duration = round(duration / clockq) * clockq
        notes.append((clock, note, duration, sid_f))
    return notes
