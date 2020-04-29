# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.


from midiutil import MIDIFile

A = 440
MIDI_N_TO_F = {n: (A / 32) * (2 ** ((n - 9) / 12)) for n in range(128)}


def get_midi_file(bpm, voices):
    midi_file = MIDIFile(voices)
    for voice in range(1, voices+1):
        midi_file.addTempo(track=voice, time=0, tempo=bpm)
    return midi_file
