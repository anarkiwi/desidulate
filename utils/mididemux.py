#!/usr/bin/python3

# Copyright 2020-2022 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.


import os
import sys
from collections import defaultdict
from music21 import midi
from desidulate.sidmidi import add_end_of_track, add_event, write_midi, read_midi


TSGRAN = 10
DRUMCHAN = 10
BASSCHAN = 1
LEADCHAN = 2
PARTITIONBARS = 2
NOTE_SPLIT = 60
TRACK_TYPES = {
  BASSCHAN: 'bass',
  LEADCHAN: 'lead',
  DRUMCHAN: 'drum',
}

in_midi = sys.argv[1]
if not in_midi or not os.path.exists(in_midi):
    sys.exit(1)
in_midi = os.path.realpath(in_midi)
out_midi = in_midi.replace('.mid', '')

input_mf = read_midi(in_midi)
tpqn = input_mf.ticksPerQuarterNote

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
    assert track.events[-1].type == midi.MetaEvents.END_OF_TRACK, track.events[-1]
    for event in track.events[:-1]:
        if event.isDeltaTime():
            offset = round(event.time / TSGRAN) * TSGRAN
            offsets.add(offset)
            clock += offset
        else:
            assert event.time == 0
            event.channel = channel
            input_track_events[index].append((clock, event))
            if event.isNoteOn() and event.pitch:
                track_notes[index].add(event.pitch)


output_track_events = defaultdict(list)
for index, events in input_track_events.items():
    notes = sorted(track_notes[index])
    if notes and track_channel[index] != DRUMCHAN:
        track_channel[BASSCHAN] = BASSCHAN
        track_channel[LEADCHAN] = LEADCHAN
        for clock, event in events:
            if event.isNoteOn() or event.isNoteOff():
                if event.pitch <= NOTE_SPLIT:
                    chans = [BASSCHAN]
                else:
                    chans = [LEADCHAN]
            else:
                chans = [BASSCHAN, LEADCHAN]
            for chan in chans:
                output_track_events[chan].append((clock, event))
    else:
        output_track_events[index] = events

for index in output_track_events:
    output_track_events[index] = sorted(output_track_events[index], key=lambda t: t[0])


def events_to_track(index, channel, events):
    track = midi.MidiTrack(index=index)
    last_clock = 0
    for clock, event in sorted(events, key=lambda t: t[0]):
        delta_clock = clock - last_clock
        last_clock = clock
        add_event(track, event, delta_clock, channel)

    add_end_of_track(track, channel)
    return track


def write_track(basename, track_type, index, track):
    write_midi('%s-%s-%u.mid' % (basename, track_type, index), tpqn, [track])


for index, events in output_track_events.items():
    if index:
        channel = track_channel[index]
        track_type = TRACK_TYPES[channel]
        non_notes = [(clock, event) for clock, event in events if not (event.isNoteOn() or event.isNoteOff())]
        partitions = []
        notes_playing = set()
        last_clock = events[0][0]
        noteevents = 0
        firstnoteclock = None
        for i, pair in enumerate(events):
            clock, event = pair
            # assume 4/4
            event_gap = (clock - last_clock) / tpqn / 4
            if not notes_playing and noteevents and (event_gap > PARTITIONBARS):
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
                track = events_to_track(index, channel, partevents)
                write_track(out_midi, track_type, n, track)
        else:
            events = non_notes + [(x - firstnoteclock, y) for x, y in events if x]
            track = events_to_track(index, channel, events)
            write_track(out_midi, track_type, 0, track)
