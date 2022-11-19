#!/usr/bin/python3

# https://hvsc.c64.org/download/C64Music/DOCUMENTS/SID_file_format.txt
import os
import re
import struct
import time
import docker
import pandas as pd


SIDPLAYFP_IMAGE = 'anarkiwi/sidplayfp'
CIA_TIMER_RE = re.compile('^.+\s+ST([AXY])a\s+dc0([45])$')
INSTRUCTION_RE = re.compile('^.+Instruction\s+\((\d+)\)$')


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
    return bitsdecode(x, {0: None, 1: '6581', 2: '8580', 3: '6581+8580'})


def clock(x):
    return bitsdecode(x, {0: 'Unknown', 1: 'PAL', 2: 'NTSC', 3: 'PAL+NTSC'})


def binformat(x):
    return bitsdecode(x, {0: 'built-in', 1: 'MUS'})


def psidspecific(rsid, x):
    if rsid:
        return bitsdecode(x, {0: 'c64', 1: 'basic'})
    else:
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


def decodespeed(rsid, x):
    x = int(x)
    if not rsid:
        # assume all same speed scheme
        if x:
            return 'CIA'
    return 'VBI'


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
        ('speed', 'I', decodespeed),
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


def scrape_cia_timer(sidfile, cutoff_time=0.5):
    siddir = os.path.realpath(os.path.dirname(sidfile))
    client = docker.from_env()
    timer_low = 0
    timer_high = 0
    instruction_cutoff = cutoff_time * 1e6 / 2
    instructions = 0
    # TODO: the defaut tune, only
    cmd = [
        f'-t{cutoff_time}', '-q', '--none', '--cpu-debug', '-os', '--delay=0',
        os.path.join('tmp', os.path.basename(sidfile))]
    sidplayfp = client.containers.run(
        SIDPLAYFP_IMAGE, cmd,
        remove=True, stdout=True, detach=True,
        volumes=[f'{siddir}:/tmp:ro'],
        ulimits=[docker.types.Ulimit(name='cpu', hard=round(cutoff_time*2))])
    for line in sidplayfp.logs(stream=True, stdout=True, stderr=False):
        line = line.decode('utf8').strip()
        if not line:
            continue
        match = INSTRUCTION_RE.match(line)
        if match:
            instructions = int(match.group(1))
            continue
        if instructions > instruction_cutoff:
            continue
        match = CIA_TIMER_RE.match(line)
        if not match:
            continue
        cpu_reg = match.group(1)
        cia_reg = int(match.group(2))
        cpu_reg_map = {'A': 2, 'X': 3, 'Y': 4}
        raw_val = line.split()[cpu_reg_map[cpu_reg]]
        val = int(raw_val, 16)
        if cia_reg == 4:
            timer_low = val
        else:
            timer_high = val
    client.close()
    if not instructions:
        raise ValueError('saw no instructions')
    timer = (timer_high << 8) + timer_low
    if not timer:
        raise ValueError('CIA timer 0')
    return timer


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

    decoded['pal'] = int('PAL' in decoded['clock'])

    decoded['sids'] = 1
    for sid in ('secondSIDAddress', 'thirdSIDAddress'):
        if decoded[sid]:
            decoded['sids'] += 1

    decoded['cia'] = 0
    if rsid:
        decoded['cia'] = 1
    else:
        decoded['cia'] = int(decoded['speed'] == 'CIA')
    if decoded['cia']:
        decoded['cia'] = scrape_cia_timer(sidfile)

    return decoded
