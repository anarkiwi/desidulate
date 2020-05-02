#!/usr/bin/python3

# https://codebase64.org/doku.php?id=base:building_a_music_routine
# http://www.ucapps.de/howto_sid_wavetables_1.html

from sidlib import get_reg_changes, get_reg_writes, get_consolidated_changes, clock_to_qn, get_gate_events
from sidmidi import get_midi_file, get_midi_notes_from_events
from sidwav import get_sid


bpm = 125
voicemask = {1, 2, 3}

sid = get_sid()
reg_writes = get_reg_changes(get_reg_writes('vicesnd.sid'), voicemask)
reg_writes_changes = get_consolidated_changes(reg_writes, voicemask)
mainevents, voiceevents = get_gate_events(reg_writes_changes, voicemask)

smf = get_midi_file(bpm, max(voicemask))

for voicenum, gated_voice_events in voiceevents.items():
    for event_start, events in gated_voice_events:
        midi_notes = get_midi_notes_from_events(sid, events)
        for clock, pitch, duration in midi_notes:
            qn_clock = clock_to_qn(sid, clock, bpm)
            qn_duration = clock_to_qn(sid, duration, bpm)
            if qn_duration > 0.1:
                smf.addNote(voicenum-1, voicenum, pitch, qn_clock, qn_duration, 100)

with open('sid.mid', 'wb') as midi_f:
    smf.writeFile(midi_f)
