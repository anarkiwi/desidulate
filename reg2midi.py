#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

# https://codebase64.org/doku.php?id=base:building_a_music_routine
# http://www.ucapps.de/howto_sid_wavetables_1.html

import argparse
from collections import Counter
from sidlib import clock_to_qn, get_consolidated_changes, get_gate_events, get_reg_changes, get_reg_writes, VOICES
from sidmidi import get_midi_file, get_midi_notes_from_events, DRUM_TRACK_OFFSET, DRUM_CHANNEL
from sidwav import get_sid


parser = argparse.ArgumentParser(description='Convert vicesnd.sid log into a MIDI file')
parser.add_argument('--logfile', default='vicesnd.sid', help='log file to read')
parser.add_argument('--midifile', default='reg2midi.mid', help='MIDI file to write')
parser.add_argument('--voicemask', default=','.join((str(v) for v in VOICES)), help='command separated list of SID voices to use')
parser.add_argument('--minclock', default=0, type=int, help='start rendering from this clock value')
parser.add_argument('--maxclock', default=0, type=int, help='if > 0, stop rendering at this clock value')
parser.add_argument('--bpm', default=125, type=int, help='MIDI BPM')
pal_parser = parser.add_mutually_exclusive_group(required=False)
pal_parser.add_argument('--pal', dest='pal', action='store_true', help='Use PAL clock')
pal_parser.add_argument('--ntsc', dest='pal', action='store_false', help='Use NTSC clock')
parser.set_defaults(pal=True)
args = parser.parse_args()
voicemask = set((int(v) for v in args.voicemask.split(',')))

smf = get_midi_file(args.bpm)
sid = get_sid(pal=args.pal)
clockq = sid.clock_frequency / 50
reg_writes = get_reg_changes(get_reg_writes(args.logfile), voicemask=voicemask, minclock=args.minclock, maxclock=args.maxclock)
reg_writes_changes = get_consolidated_changes(reg_writes, voicemask)
mainevents, voiceevents = get_gate_events(reg_writes_changes, voicemask)

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

for voicenum, gated_voice_events in voiceevents.items():
    for event_start, events in gated_voice_events:
        midi_notes = get_midi_notes_from_events(sid, events, clockq)
        if not midi_notes:
            continue
        midi_pitches = [midi_note[1] for midi_note in midi_notes]
        max_midi_note = max(midi_pitches)
        min_midi_note = min(midi_pitches)
        total_duration = sum(duration for _, _, duration, _, _ in midi_notes)
        voicestates = [(clock, state.voices[voicenum]) for clock, _, state in events]
        waveforms = Counter()
        waveform_order = []
        last_clock = None
        for clock, voicestate in voicestates:
            if last_clock is None:
                last_clock = clock
            curr_waveform = []
            for waveform in ('noise', 'pulse', 'triangle', 'sawtooth'):
                if getattr(voicestate, waveform, None):
                    waveforms[waveform] += (clock - last_clock)
                    curr_waveform.append(waveform)
            curr_waveform = tuple(curr_waveform)
            if not waveform_order or waveform_order[-1] != curr_waveform:
                waveform_order.append(curr_waveform)
            last_clock = clock
        noisephases = len([curr_waveform for curr_waveform in waveform_order if 'noise' in curr_waveform])
        noises = noisephases > 0

        def add_pitch(clock, pitch, sustain, duration, track, channel):
            qn_clock = clock_to_qn(sid, clock, args.bpm)
            qn_duration = clock_to_qn(sid, duration, args.bpm)
            velocity = int(sustain / 15 * 127)
            smf.addNote(track, channel, pitch, qn_clock, qn_duration, velocity)

        def add_noise_duration(clock, sustain, duration, track, channel):
            max_duration = clockq
            noise_pitch = None
            for noise_pitch in (PEDAL_HIHAT, CLOSED_HIHAT, OPEN_HIHAT, ACCOUSTIC_SNARE, CRASH_CYMBAL1):
                if duration <= max_duration:
                    break
                max_duration *= 2
            add_pitch(clock, noise_pitch, sustain, duration, track, channel)

        def descending(pitches):
            return pitches[0] > pitches[-1]

        if noises:
            if set(waveforms.keys()) == {'noise'}:
                for clock, _pitch, duration, sustain, _ in midi_notes:
                    add_noise_duration(clock, sustain, duration, DRUM_TRACK_OFFSET + voicenum, DRUM_CHANNEL)
            else:
                for clock, _pitch, _duration, sustain, _ in midi_notes:
                    if noisephases > 1:
                        add_pitch(clock, ELECTRIC_SNARE, sustain, total_duration, DRUM_TRACK_OFFSET + voicenum, DRUM_CHANNEL)
                    elif descending(midi_pitches) and len(midi_pitches) > 2:
                        # http://www.ucapps.de/howto_sid_wavetables_1.html
                        add_pitch(clock, BASS_DRUM, sustain, total_duration, DRUM_TRACK_OFFSET + voicenum, DRUM_CHANNEL)
                    else:
                        add_pitch(clock, LOW_TOM, sustain, total_duration, DRUM_TRACK_OFFSET + voicenum, DRUM_CHANNEL)
        else:
            for clock, pitch, duration, sustain, _ in midi_notes:
                add_pitch(clock, pitch, sustain, duration, voicenum-1, voicenum)


with open(args.midifile, 'wb') as midi_f:
    smf.writeFile(midi_f)
