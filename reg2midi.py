#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

# https://codebase64.org/doku.php?id=base:building_a_music_routine
# http://www.ucapps.de/howto_sid_wavetables_1.html

import argparse
import csv
import io
from collections import Counter, defaultdict
from sidlib import get_consolidated_changes, get_gate_events, get_reg_changes, get_reg_writes, get_sid, VOICES
from sidmidi import midi_path, out_path, SidMidiFile, ELECTRIC_SNARE, BASS_DRUM, LOW_TOM


parser = argparse.ArgumentParser(description='Convert vicesnd.sid log into a MIDI file')
parser.add_argument('logfile', default='vicesnd.sid', help='log file to read')
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

clock_consolidate = 256
single_patches = {}
multi_patches = {}
patch_count = Counter()


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
        self.voice_filtered = False

    def trim_gateoff(self):
        for i, clock_voicestate_state in enumerate(self.voicestates):
            _, voicestate, state = clock_voicestate_state
            if not voicestate.gate and not voicestate.release:
                self.voicestates = self.voicestates[:i+1]
                break
            if state.mainreg.voice_filtered(self.voicenum):
                self.voice_filtered = True
        i = len(self.voicestates) - 1
        while i > 0 and self.voicestates[i][1].test:
            i -= 1
        if i:
            self.voicestates = self.voicestates[:i+2]

    def normalize_voicenum(self, voicenum):
        if voicenum == self.voicenum:
            return 1
        return 3

    def parse(self):
        audible_voicenums = set()
        synced_voicenums = set()
        for clock, _, state in self.events:
            voicestate = state.voices[self.voicenum]
            audible_voicenums = audible_voicenums.union(state.audible_voicenums())
            synced_voicenums = synced_voicenums.union(voicestate.synced_voicenums())
            self.voicestates.append((clock, voicestate, state))
        self.trim_gateoff()
        if self.voicenum in audible_voicenums:
            self.midi_notes = tuple(self.smf.get_midi_notes_from_events(self.sid, self.events, self.clockq))
            self.midi_pitches = tuple([midi_note[1] for midi_note in self.midi_notes])
            self.total_duration = sum(duration for _, _, duration, _, _ in self.midi_notes)
        if not self.midi_notes:
            return
        voicenums = {self.voicenum}.union(synced_voicenums)
        if len(voicenums) > 1:
            assert len(voicenums) == 2
        self.max_midi_note = max(self.midi_pitches)
        self.min_midi_note = min(self.midi_pitches)
        last_clock = None
        rel_clock = 0
        assert self.voicestates[0][1].gate_on()
        orig_diffs = defaultdict(list)
        last_state = None
        first_state = None
        for clock, voicestate, state in self.voicestates:
            if last_clock is not None:
                rel_clock = clock - last_clock
            else:
                first_state = state
            curr_waveforms = voicestate.flat_waveforms()
            for waveform in curr_waveforms:
                self.waveforms[waveform] += rel_clock
            if not self.waveform_order or self.waveform_order[-1] != curr_waveforms:
                self.waveform_order.append(curr_waveforms)
            if last_state:
                diff = {}
                for voicenum in voicenums:
                    voicestate_now = state.voices[voicenum]
                    last_voicestate = last_state.voices[voicenum]
                    voice_diff = voicestate_now.diff(last_voicestate)
                    voice_diff = {'%s%u' % (k, self.normalize_voicenum(voicenum)): v for k, v in voice_diff.items()}
                    diff.update(voice_diff)
                if self.voice_filtered:
                    filter_diff = state.mainreg.diff_filter(self.voicenum, last_state.mainreg)
                    filter_voice_key = 'filter_voice%u' % self.voicenum
                    val = filter_diff.get(filter_voice_key, None)
                    if val is not None:
                        del filter_diff[filter_voice_key]
                        filter_diff['filter_voice%u' % self.normalize_voicenum(self.voicenum)] = val
                    diff.update(filter_diff)
                clock_diff = round((clock - event_start) / clock_consolidate) * clock_consolidate
                orig_diffs[clock_diff].append(diff)
            last_clock = clock
            last_state = state
        self.noisephases = len([waveforms for waveforms in self.waveform_order if 'noise' in waveforms])
        self.all_noise = set(self.waveforms.keys()) == {'noise'}

        first_row = {'clock': 0}
        fieldnames = ['clock']
        if first_state:
            for voicenum in voicenums:
                voicestate = first_state.voices[voicenum]
                for field in voicestate.voice_regs:
                    val = getattr(voicestate, field)
                    field = '%s%u' % (field, self.normalize_voicenum(voicenum))
                    fieldnames.append(field)
                    first_row[field] = val
            for field in first_state.mainreg.filter_common:
                val = getattr(first_state.mainreg, field)
                fieldnames.append(field)
                first_row[field] = val
            filter_voice_key = 'filter_voice%u' % self.normalize_voicenum(self.voicenum)
            fieldnames.append(filter_voice_key)
            first_row[filter_voice_key] = getattr(first_state.mainreg, 'filter_voice%u' % self.voicenum)

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(first_row)
        for clock, diffs in orig_diffs.items():
            row = {'clock': clock}
            full_diff = {}
            for diff in diffs:
                for field, val in diff.items():
                    if field not in full_diff:
                        full_diff[field] = val
                    else:
                        full_diff[field] += val
            row.update(full_diff)
            writer.writerow(row)
        csv_txt = buffer.getvalue()
        hash_csv_txt = hash(csv_txt)
        if len(voicenums) == 1:
            single_patches[hash_csv_txt] = csv_txt
        else:
            multi_patches[hash_csv_txt] = csv_txt
        patch_count[hash_csv_txt] += 1

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

for (ext, patches) in (('single_patches.txt', single_patches), ('multi_patches.txt', multi_patches)):
    if not patches:
        continue
    out_filename = out_path(args.logfile, ext)
    first_csv_txt = list(patches.values())[0]
    reader = csv.DictReader(io.StringIO(first_csv_txt))
    first_row = next(reader)
    fieldnames = list(reader.fieldnames)

    with open(out_filename, 'w') as f:
        writer = csv.DictWriter(f, fieldnames=['hashid', 'count'] + fieldnames, dialect='unix', quoting=csv.QUOTE_NONE)
        writer.writeheader()
        for hashid, count in sorted(patch_count.items(), key=lambda x: x[1], reverse=True):
            if hashid in patches:
                csv_txt = patches[hashid]
                reader = csv.DictReader(io.StringIO(csv_txt))
                for row in reader:
                    row.update({
                        'hashid': hashid,
                        'count': patch_count[hashid],
                    })
                    writer.writerow(row)
