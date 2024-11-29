#!/usr/bin/python3

# https://hvsc.c64.org/download/C64Music/DOCUMENTS/SID_file_format.txt
import copy
import os
import re
import struct
import docker


SIDPLAYFP_IMAGE = 'anarkiwi/sidplayfp'
CIA1_TIMERA_RE = re.compile(r'^.+\s+ST([AXY])a\s+dc0([45e])$')
INSTRUCTION_RE = re.compile(r'^.+Instruction\s+\((\d+)\)$')


def intdecode(_, x):
    return int(x)


def strdecode(_, x):
    return x.decode('latin1').rstrip('\x00')


def sidaddr(_, x):
    x = int(x) << 4
    if x:
        x += 0xd000
    return x


def bitsdecode(x, d):
    return d[x & max(d.keys())]


def sidmodel(x):
    return bitsdecode(x, {0: 'Unknown', 1: '6581', 2: '8580', 3: '6581+8580'})


def clock(x):
    return bitsdecode(x, {0: 'Unknown', 1: 'PAL', 2: 'NTSC', 3: 'PAL+NTSC'})


def binformat(x):
    return bitsdecode(x, {0: 'built-in', 1: 'MUS'})


def psidspecific(rsid, x):
    if rsid:
        return bitsdecode(x, {0: 'c64', 1: 'basic'})
    return bitsdecode(x, {0: 'c64', 1: 'psid'})


def decodeflags(rsid, x):
    x = int(x)
    return {
        'binformat': binformat(x),
        'psidSpecific': psidspecific(rsid, x),
        'clock': clock((x >> 2)),
        'sidmodel': sidmodel((x >> 4)),
        'sidmodel2': sidmodel((x >> 6)),
        'sidmodel3': sidmodel((x >> 8)),
    }


SID_HEADER_LEN = 0x7C
SID_HEADERS = (
        # +00    STRING magicID: 'PSID' or 'RSID'
        ('magicID', '4s', strdecode),
        # +04    WORD version
        ('version', 'H', intdecode),
        # +06    WORD dataOffset
        ('dataOffset', 'H', intdecode),
        # +08    WORD loadAddress
        ('loadAddress', 'H', intdecode),
        # +0A    WORD initAddress
        ('initAddress', 'H', intdecode),
        # +0C    WORD playAddress
        ('playAddress', 'H', intdecode),
        # +0E    WORD songs
        ('songs', 'H', intdecode),
        # +10    WORD startSong
        ('startSong', 'H', intdecode),
        # +12    LONGWORD speed
        ('speed', 'I', intdecode),
        # +16    STRING ``<name>''
        ('name', '32s', strdecode),
        # +36    STRING ``<author>''
        ('author', '32s', strdecode),
        # +56    STRING ``<released>''
        ('released', '32s', strdecode),
        # +76    WORD flags
        ('flags', 'H', decodeflags),
        # +78    BYTE startPage (relocStartPage)
        ('startPage', 'B', intdecode),
        # +79    BYTE pageLength (relocPages)
        ('pageLength', 'B', intdecode),
        # +7A    BYTE secondSIDAddress
        ('secondSIDAddress', 'B', intdecode),
        # +7B    BYTE thirdSIDAddress
        ('thirdSIDAddress', 'B', intdecode),
)


def scrape_cia_timer(sidfile, validate_ctrl, tune, cutoff_time=1):
    siddir = os.path.realpath(os.path.dirname(sidfile))
    client = docker.from_env()
    timer_low = 0
    timer_high = 0
    timer = 0
    ctrl = 0
    instruction_cutoff = cutoff_time * 1e6
    instructions = 0
    cmd = [
        f'-t{cutoff_time}', '-q', '--cpu-debug', '--delay=0', f'-os{tune}', '-w/dev/null',
        os.path.join('tmp', os.path.basename(sidfile))]
    sidplayfp = client.containers.run(
        SIDPLAYFP_IMAGE, cmd,
        remove=True, stdout=True, detach=True, network='none',
        volumes=[f'{siddir}:/tmp:ro'],
        ulimits=[docker.types.Ulimit(name='cpu', hard=round(cutoff_time*2))])
    timer_starts = 0
    for line in sidplayfp.logs(stream=True, stdout=True, stderr=False):
        # need to drain log buffer to avoid docker client socket leak.
        if instructions > instruction_cutoff:
            continue
        line = line.decode('utf8').strip()
        if not line:
            continue
        match = INSTRUCTION_RE.match(line)
        if match:
            instructions = int(match.group(1))
            continue
        match = CIA1_TIMERA_RE.match(line)
        if not match:
            continue
        cpu_reg = match.group(1)
        cia_reg = int(match.group(2), 16)
        cpu_reg_map = {'A': 2, 'X': 3, 'Y': 4}
        raw_val = line.split()[cpu_reg_map[cpu_reg]]
        val = int(raw_val, 16)
        if cia_reg == 0xe:
            ctrl = val
            if ctrl & 2**0:
                timer_starts += 1
        else:
            if cia_reg == 4:
                timer_low = val
            elif cia_reg == 5:
                timer_high = val
            timer = (timer_high << 8) + timer_low
    client.close()
    if validate_ctrl:
        if not timer_starts:
            raise ValueError(f'{sidfile}: CIA timer not started: {ctrl}')
        one_shot = ctrl & 2**3
        if one_shot:
            raise ValueError(f'{sidfile}: CIA timer was set to one-shot: {ctrl}')
    if not instructions:
        raise ValueError(f'{sidfile}: saw no instructions')
    if not timer:
        raise ValueError(f'{sidfile}: CIA timer 0 after {instructions} instructions')
    return timer



def sidinfo_song(sidfile, song, decoded, rsid, raw_speed):
    decoded_song = copy.deepcopy(decoded)
    decoded_song['song'] = song

    if not rsid:
        if raw_speed & 2**min((song-1), 31):
            decoded_song['speed'] = 'CIA'
        decoded_song['cia'] = int(decoded_song['speed'] == 'CIA')

    if decoded_song['cia']:
        decoded_song['cia'] = scrape_cia_timer(sidfile, not rsid, song)
    return decoded_song



def sidinfo(sidfile):
    with open(sidfile, 'rb') as f:
        data = f.read()[:SID_HEADER_LEN]
    unpack_format = '>' + ''.join((field_type for _, field_type, _ in SID_HEADERS))
    results = struct.unpack(unpack_format, data)
    rsid = results[0] == b'RSID'
    decoded = {'path': sidfile}
    for header_data, field_data in zip(SID_HEADERS, results):
        field, _, decode = header_data
        decoded_field = decode(rsid, field_data)
        if isinstance(decoded_field, dict):
            decoded.update(decoded_field)
        else:
            decoded[field] = decoded_field

    raw_speed = decoded['speed']
    decoded['speed'] = 'VBI'
    decoded['pal'] = int('PAL' in decoded['clock'])
    decoded['sids'] = 1
    for sid, sidmodel in (('secondSIDAddress', 'sidmodel2'), ('thirdSIDAddress', 'sidmodel3')):
        if decoded[sid]:
            decoded['sids'] += 1
            if decoded[sidmodel] == 'Unknown':
                decoded[sidmodel] = decoded['sidmodel']
    decoded['cia'] = int(rsid)

    decoded_songs = []
    for song in range(1, decoded['songs']+1):
        decoded_songs.append(sidinfo_song(sidfile, song, decoded, rsid, raw_speed))

    return decoded_songs
