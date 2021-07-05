#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.


import os
import sys
from collections import defaultdict
from music21 import midi
from sidmidi import track_zero, add_end_of_track, add_event


TSGRAN = 10
DRUMCHAN = 10

in_midi = sys.argv[1]
if not in_midi or not os.path.exists(in_midi):
    sys.exit(1)
in_midi = os.path.realpath(in_midi)
out_midi = in_midi.replace('.mid', '')

input_mf = midi.MidiFile()
input_mf.open(in_midi)
input_mf.read()
input_mf.close()

track_channel = {}
input_track_events = defaultdict(list)
drum_index = None
non_drum_index = None
non_drum_channel = None
track_notes = defaultdict(set)

for track in sorted(input_mf.tracks, key=lambda t: t.index):
    channels = {event.channel for event in track.events if event.channel is not None}
    assert len(channels) <= 1, channels
    index = track.index
    channel = None
    if channels:
        channel = list(channels)[0]

        if channel == DRUMCHAN:
            if drum_index is None:
                drum_index = index
            else:
                index = drum_index
        else:
            if non_drum_index is None:
                non_drum_index = index
                non_drum_channel = channel
            else:
                index = non_drum_index
                channel = non_drum_channel
    track_channel[index] = channel
    clock = 0
    offsets = set()
    for event in track.events:
        if event.isDeltaTime():
            offset = round(event.time / TSGRAN) * TSGRAN
            offsets.add(offset)
            clock += offset
        else:
            assert event.time == 0
            event.channel = channel
            if event.type == midi.MetaEvents.END_OF_TRACK:
                continue
            input_track_events[index].append((clock, event))
            if event.isNoteOn() and event.pitch:
                track_notes[index].add(event.pitch)


output_track_events = defaultdict(list)
for index, events in input_track_events.items():
    notes = sorted(track_notes[index])
    if notes and track_channel[index] != DRUMCHAN:
        last_note = notes[0]
        note_split = last_note
        note_diff = 0
        track_channel[1] = 1
        track_channel[2] = 2
        note_split = 60
        #for note in notes:
        #    if note - last_note > note_diff and note >= 60:
        #        note_split = note
        #        note_diff = note - last_note
        #    last_note = note
        for clock, event in events:
            if event.isNoteOn() or event.isNoteOff():
                if event.pitch <= note_split:
                    output_track_events[1].append((clock, event))
                else:
                    output_track_events[2].append((clock, event))
            else:
                output_track_events[1].append((clock, event))
                output_track_events[2].append((clock, event))

    else:
        output_track_events[index] = events

for index in output_track_events:
    output_track_events[index] = sorted(output_track_events[index], key=lambda t: t[0])


def events_to_track(index, channel, events):

    track = midi.MidiTrack(index=index)
    last_clock = 0
    note_events = 0
    for clock, event in sorted(events, key=lambda t: t[0]):
        if event.type == midi.MetaEvents.END_OF_TRACK:
            continue
        delta_clock = clock - last_clock
        last_clock = clock
        note_events += add_event(track, event, delta_clock, channel)

    add_end_of_track(track, channel)
    return track, note_events


def write_track(basename, track_type, index, tpqn, track):
    output_mf = midi.MidiFile()
    output_mf.open('%s-%s-%u.mid' % (basename, track_type, index), 'wb')
    output_mf.ticksPerQuarterNote = tpqn
    output_mf.tracks.append(track_zero())
    output_mf.tracks.append(track)
    output_mf.write()


tpqn = input_mf.ticksPerQuarterNote
gapbars = 2

for index, events in output_track_events.items():
    if index:
        channel = track_channel[index]
        if channel == DRUMCHAN:
            track_type = 'drum'
        elif channel == 1:
            track_type = 'bass'
        else:
            track_type = 'lead'

        non_notes = []
        for clock, event in events:
            if event.isNoteOn() or event.isNoteOff():
                break
            non_notes.append((clock, event))

        partitions = []
        notes_playing = set()
        last_clock = events[0][0]
        noteevents = 0
        firstnoteclock = None
        for i, pair in enumerate(events):
            clock, event = pair
            event_gap = (clock - last_clock) / 960 / 4
            if not notes_playing and noteevents and (event_gap > gapbars):
                partitions.append(i)
            last_clock = clock
            if event.isNoteOn():
                notes_playing.add(event.pitch)
                noteevents += 1
                if firstnoteclock is None:
                    firstnoteclock = clock
            elif event.isNoteOff() and event.pitch in notes_playing:
                notes_playing.remove(event.pitch)
                noteevents += 1
        if partitions:
            lasti = 0
            for n, i in enumerate(partitions):
                partevents = events[lasti:i]
                partclock = partevents[0][0]
                if lasti:
                    partevents = [(partclock, y) for _, y in non_notes] + partevents
                    partevents = [(x - partclock, y) for x, y in partevents]
                else:
                    partevents = non_notes + [(x - firstnoteclock, y) for x, y in partevents if x]
                lasti = i
                track, note_events = events_to_track(index, channel, partevents)
                if note_events:
                    write_track(out_midi, track_type, n, tpqn, track)
        else:
            events = non_notes + [(x - firstnoteclock, y) for x, y in events if x]
            track, note_events = events_to_track(index, channel, events)
            if note_events:
                write_track(out_midi, track_type, 0, tpqn, track)
