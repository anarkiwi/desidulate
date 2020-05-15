# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.


from midiutil import MIDIFile
from sidlib import real_sid_freq

A = 440
MIDI_N_TO_F = {n: (A / 32) * (2 ** ((n - 9) / 12)) for n in range(128)}
MIDI_F_TO_N = {f: n for n, f in MIDI_N_TO_F.items()}
DRUM_TRACK = 3
DRUM_CHANNEL = 9


def get_midi_file(bpm):
    tracks = 3 + 1 # voices plus percussion.
    midi_file = MIDIFile(tracks)
    for i in range(tracks):
        midi_file.addTempo(i, time=0, tempo=bpm)
    return midi_file


def closest_midi(sid_f):
    closest_midi_f = min(MIDI_N_TO_F.values(), key=lambda x: abs(x - sid_f))
    return (closest_midi_f, MIDI_F_TO_N[closest_midi_f])


# Convert gated voice events into possibly many MIDI notes
def get_midi_notes_from_events(sid, events):
    last_sid_f = None
    last_midi_n = None
    notes_starts = []
    for clock, regevent, state in events:
        voicenum = regevent.voicenum
        voice_state = state.voices[voicenum]
        sid_f = real_sid_freq(sid, voice_state.frequency)
        closest_midi_f, closest_midi_n = closest_midi(sid_f)
        # TODO: add pitch bend if significantly different to canonical note.
        if closest_midi_n != last_midi_n and voice_state.any_waveform():
            notes_starts.append((closest_midi_n, clock, sid_f))
            last_midi_n = closest_midi_n
            last_sid_f = sid_f
    last_clock = clock
    notes = []
    for n, note_clocks in enumerate(notes_starts):
        note, clock, sid_f = note_clocks
        try:
            next_clock = notes_starts[n + 1][1]
        except IndexError:
            next_clock = last_clock
        duration = next_clock - clock
        if duration:
            notes.append((clock, note, duration, sid_f))
    return notes
