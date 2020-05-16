#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

# https://codebase64.org/doku.php?id=base:building_a_music_routine
# http://www.ucapps.de/howto_sid_wavetables_1.html

import argparse
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

BASS_DRUM = 36
PEDAL_HIHAT = 44
CLOSED_HIHAT = 42
OPEN_HIHAT = 46
ACCOUSTIC_SNARE = 38
CRASH_CYMBAL1 = 49

for voicenum, gated_voice_events in voiceevents.items():
    for event_start, events in gated_voice_events:
        midi_notes = get_midi_notes_from_events(sid, events, clockq)
        if not midi_notes:
            continue
        midi_pitches = [midi_note[1] for midi_note in midi_notes]
        max_midi_note = max(midi_pitches)
        min_midi_note = min(midi_pitches)
        total_duration = sum(duration for _, _, duration, _ in midi_notes)
        voicestates = [state.voices[voicenum] for _, _, state in events]
        waveforms = set()
        for voicestate in voicestates:
            for waveform in ('noise', 'pulse', 'triangle', 'sawtooth'):
                if getattr(voicestate, waveform, None):
                    waveforms.add(waveform)
        noises = 'noise' in waveforms

        def add_pitch(clock, pitch, duration, track, channel, velocity=100):
            qn_clock = clock_to_qn(sid, clock, args.bpm)
            qn_duration = clock_to_qn(sid, duration, args.bpm)
            smf.addNote(track, channel, pitch, qn_clock, qn_duration, velocity)

        def add_noise_duration(clock, pitch, duration, track, channel, velocity=100):
            max_duration = clockq
            noise_pitch = None
            for noise_pitch in (PEDAL_HIHAT, CLOSED_HIHAT, OPEN_HIHAT, ACCOUSTIC_SNARE, CRASH_CYMBAL1):
                if duration <= max_duration:
                    break
                max_duration *= 2
            add_pitch(clock, noise_pitch, duration, track, channel, velocity=velocity)

        if noises:
            # https://en.wikipedia.org/wiki/General_MIDI#Percussion
            if waveforms == {'noise'}:
                for clock, _pitch, duration, _ in midi_notes:
                    add_noise_duration(clock, _pitch, duration, DRUM_TRACK_OFFSET + voicenum, DRUM_CHANNEL)
            else:
                for clock, _pitch, _duration, _ in midi_notes:
                    # if max_midi_note == 102 and min_midi_note == 53:
                    #     add_pitch(clock, 38, total_duration, DRUM_TRACK_OFFSET + voicenum, DRUM_CHANNEL)
                    # elif max_midi_note == 102 and min_midi_note == 56:
                    #     add_pitch(clock, 50, total_duration, DRUM_TRACK_OFFSET + voicenum, DRUM_CHANNEL)
                    # elif max_midi_note == 102 and min_midi_note == 42:
                    #     add_pitch(clock, 45, total_duration, DRUM_TRACK_OFFSET + voicenum, DRUM_CHANNEL)
                    add_pitch(clock, BASS_DRUM, total_duration, DRUM_TRACK_OFFSET + voicenum, DRUM_CHANNEL)
                    break
        else:
            for clock, pitch, duration, _ in midi_notes:
                add_pitch(clock, pitch, duration, voicenum-1, voicenum)


with open(args.midifile, 'wb') as midi_f:
    smf.writeFile(midi_f)
