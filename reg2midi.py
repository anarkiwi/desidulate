#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

# https://codebase64.org/doku.php?id=base:building_a_music_routine
# http://www.ucapps.de/howto_sid_wavetables_1.html

import argparse
from collections import Counter
from sidlib import get_consolidated_changes, get_gate_events, get_reg_changes, get_reg_writes, get_sid, VOICES
from sidmidi import midi_path, SidMidiFile, ELECTRIC_SNARE, BASS_DRUM, LOW_TOM


parser = argparse.ArgumentParser(description='Convert vicesnd.sid log into a MIDI file')
parser.add_argument('--logfile', default='vicesnd.sid', help='log file to read')
parser.add_argument('--midifile', default='', help='MIDI file to write')
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


class SidSoundEvent:

    def __init__(self, percussion, sid, clockq, smf, voicenum, event_start, events):
        self.percussion = percussion
        self.voicenum = voicenum
        self.sid = sid
        self.clockq = clockq
        self.smf = smf
        self.event_start = event_start
        self.events = events
        self.waveforms = Counter()
        self.waveform_order = []
        self.noisephases = 0
        self.all_noise = False
        self.midi_notes = []
        self.midi_pitches = []
        self.voicestates = []

    def trim_gateoff(self):
        for i, clock_voicestate in enumerate(self.voicestates):
            clock, voicestate = clock_voicestate
            if not voicestate.gate and not voicestate.release:
                self.voicestates = self.voicestates[:i+1]
                break
        i = len(self.voicestates) - 1
        while i > 0 and self.voicestates[i][1].test:
            i -= 1
        if i:
            self.voicestates = self.voicestates[:i+2]

    def parse(self):
        audible_voicenums = set()
        for clock, _, state in self.events:
            self.voicestates.append((clock, state.voices[self.voicenum]))
            audible_voicenums = audible_voicenums.union(state.audible_voicenums())
        self.trim_gateoff()
        if self.voicenum in audible_voicenums:
            self.midi_notes = tuple(self.smf.get_midi_notes_from_events(self.sid, self.events, self.clockq))
            self.midi_pitches = tuple([midi_note[1] for midi_note in self.midi_notes])
            self.total_duration = sum(duration for _, _, duration, _, _ in self.midi_notes)
        if not self.midi_notes:
            return
        self.max_midi_note = max(self.midi_pitches)
        self.min_midi_note = min(self.midi_pitches)
        last_clock = None
        rel_clock = 0
        assert self.voicestates[0][1].gate_on()
        for clock, voicestate in self.voicestates:
            if last_clock is not None:
                rel_clock = clock - last_clock
            curr_waveforms = voicestate.flat_waveforms()
            for waveform in curr_waveforms:
                self.waveforms[waveform] += rel_clock
            if not self.waveform_order or self.waveform_order[-1] != curr_waveforms:
                self.waveform_order.append(curr_waveforms)
            last_clock = clock
        self.noisephases = len([waveforms for waveforms in self.waveform_order if 'noise' in waveforms])
        self.all_noise = set(self.waveforms.keys()) == {'noise'}

    def descending_pitches(self):
        return len(self.midi_pitches) > 2 and self.midi_pitches[0] > self.midi_pitches[-1]

    def smf_transcribe(self):
        if self.noisephases:
            if self.percussion:
                if self.all_noise:
                    for clock, _pitch, duration, velocity, _ in self.midi_notes:
                        self.smf.add_drum_noise_duration(clock, velocity, duration, self.voicenum)
                elif self.noisephases > 1:
                    for clock, _pitch, _duration, velocity, _ in self.midi_notes:
                        self.smf.add_drum_pitch(clock, ELECTRIC_SNARE, velocity, self.total_duration, self.voicenum)
                else:
                    clock, _pitch, _dutation, velocity, _ = self.midi_notes[0]
                    if self.descending_pitches():
                        # http://www.ucapps.de/howto_sid_wavetables_1.html
                        self.smf.add_drum_pitch(clock, BASS_DRUM, velocity, self.total_duration, self.voicenum)
                    else:
                        self.smf.add_drum_pitch(clock, LOW_TOM, velocity, self.total_duration, self.voicenum)
        else:
            for clock, pitch, duration, velocity, _ in self.midi_notes:
                self.smf.add_pitch(clock, pitch, velocity, duration, self.voicenum)


voicemask = set((int(v) for v in args.voicemask.split(',')))
sid = get_sid(args.pal)
clockq = sid.clock_frequency / 50
smf = SidMidiFile(sid, args.bpm, clockq)
reg_writes = get_reg_changes(get_reg_writes(args.logfile), voicemask=voicemask, minclock=args.minclock, maxclock=args.maxclock)
reg_writes_changes = get_consolidated_changes(reg_writes, voicemask)
mainevents, voiceevents = get_gate_events(reg_writes_changes, voicemask)

for voicenum, gated_voice_events in voiceevents.items():
    for event_start, events in gated_voice_events:
        sse = SidSoundEvent(args.percussion, sid, clockq, smf, voicenum, event_start, events)
        sse.parse()
        sse.smf_transcribe()

midifile = args.midifile
if not midifile:
    midifile = midi_path(args.logfile)

smf.write(midifile)
