#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

# https://codebase64.org/doku.php?id=base:building_a_music_routine
# http://www.ucapps.de/howto_sid_wavetables_1.html

import argparse
from collections import Counter
from sidlib import get_consolidated_changes, get_gate_events, get_reg_changes, get_reg_writes, VOICES
from sidmidi import SidMidiFile, ELECTRIC_SNARE, BASS_DRUM, LOW_TOM
from sidwav import get_sid


parser = argparse.ArgumentParser(description='Convert vicesnd.sid log into a MIDI file')
parser.add_argument('--logfile', default='vicesnd.sid', help='log file to read')
parser.add_argument('--midifile', default='reg2midi.mid', help='MIDI file to write')
parser.add_argument('--voicemask', default=','.join((str(v) for v in VOICES)), help='command separated list of SID voices to use')
parser.add_argument('--minclock', default=0, type=int, help='start rendering from this clock value')
parser.add_argument('--maxclock', default=0, type=int, help='if > 0, stop rendering at this clock value')
parser.add_argument('--bpm', default=125, type=int, help='MIDI BPM')
parser.add_argument('--percussion', dest='percussion', action='store_true')
parser.add_argument('--no-percussion', dest='percussion', action='store_false')
pal_parser = parser.add_mutually_exclusive_group(required=False)
pal_parser.add_argument('--pal', dest='pal', action='store_true', help='Use PAL clock')
pal_parser.add_argument('--ntsc', dest='pal', action='store_false', help='Use NTSC clock')
parser.set_defaults(pal=True, percussion=True)
args = parser.parse_args()
voicemask = set((int(v) for v in args.voicemask.split(',')))

sid = get_sid(pal=args.pal)
clockq = sid.clock_frequency / 50
smf = SidMidiFile(sid, args.bpm, clockq)
reg_writes = get_reg_changes(get_reg_writes(args.logfile), voicemask=voicemask, minclock=args.minclock, maxclock=args.maxclock)
reg_writes_changes = get_consolidated_changes(reg_writes, voicemask)
mainevents, voiceevents = get_gate_events(reg_writes_changes, voicemask)

for voicenum, gated_voice_events in voiceevents.items():
    for event_start, events in gated_voice_events:
        midi_notes = smf.get_midi_notes_from_events(sid, events, clockq)
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
            for waveform in voicestate.waveforms():
                waveforms[waveform] += (clock - last_clock)
                curr_waveform.append(waveform)
            curr_waveform = tuple(curr_waveform)
            if not waveform_order or waveform_order[-1] != curr_waveform:
                waveform_order.append(curr_waveform)
            last_clock = clock
        noisephases = len([curr_waveform for curr_waveform in waveform_order if 'noise' in curr_waveform])
        noises = noisephases > 0
        all_noise = set(waveforms.keys()) == {'noise'}

        def descending(pitches):
            return pitches[0] > pitches[-1]

        if noises:
            if args.percussion:
                if all_noise:
                    for clock, _pitch, duration, velocity, _ in midi_notes:
                        smf.add_drum_noise_duration(clock, velocity, duration, voicenum)
                elif noisephases > 1:
                    for clock, _pitch, _duration, velocity, _ in midi_notes:
                        smf.add_drum_pitch(clock, ELECTRIC_SNARE, velocity, total_duration, voicenum)
                else:
                    clock, _pitch, _dutation, velocity, _ = midi_notes[0]
                    if descending(midi_pitches) and len(midi_pitches) > 2:
                        # http://www.ucapps.de/howto_sid_wavetables_1.html
                        smf.add_drum_pitch(clock, BASS_DRUM, velocity, total_duration, voicenum)
                    else:
                        smf.add_drum_pitch(clock, LOW_TOM, velocity, total_duration, voicenum)
        else:
            for clock, pitch, duration, velocity, _ in midi_notes:
                smf.add_pitch(clock, pitch, velocity, duration, voicenum)

smf.write(args.midifile)
