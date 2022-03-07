#!/usr/bin/python3

# Copyright 2020-2022 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.


import csv
import hashlib
import multiprocessing
import os
import pathlib
import re
import subprocess
import concurrent.futures
import numpy as np
import pandas as pd

MAX_WORKERS = multiprocessing.cpu_count()
UNKNOWNS = pd.DataFrame([{'val': val} for val in ('<?>', 'UNKNOWN')])

fields_re = re.compile(r'^\|\s+([^:]+)\s+:\s+([^:]+)\s*$')
subfields_re = re.compile(r'(.+)\s+\=\s+(.+)')
year_re = re.compile(r'^([12][0-9]{3,3})\b.+')
playlist_re = re.compile(r'\d+/\d+ \(tune (\d+)/(\d+)\[(\d+)\]\)')
tunelength_re = re.compile(r'([a-z\d]+)=([\d+\s+\:\.]+)$')
tunelength_time_re = re.compile(r'(\d+)\:(\d+)\.*(\d*)$')


def scrape_sidinfo(sidfile, all_tunelengths):
    with open(sidfile, 'rb') as f:
        md5_hash = hashlib.md5(f.read()).hexdigest()
    tunelengths = all_tunelengths[md5_hash]
    assert md5_hash in all_tunelengths, (md5_hash, sidfile)

    result = {
        'path': str(os.path.normpath(sidfile)),
        'mtime': sidfile.stat().st_mtime,
        'md5': md5_hash,
    }
    cmd = ['/usr/bin/sidplayfp', '-w/dev/null', '-t1', '-v', str(sidfile)]
    with subprocess.Popen(cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            shell=False,
            errors='ignore') as process:
        _, err = process.communicate()
        for line in err.splitlines():
            fields_match = fields_re.match(line.strip())
            if not fields_match:
                continue
            field, val = fields_match.group(1).strip(), fields_match.group(2).strip()
            field = field.replace(' ', '')

            if field == 'Released':
                year_match = year_re.match(val)
                year_val = pd.NA
                if year_match:
                    year_val = year_match.group(1)
                result['ReleasedYear'] = year_val

            if field in ('Title', 'Author', 'Released'):
                result[field] = val
                continue

            subfields_match = subfields_re.match(val)
            if subfields_match:
                for subfield in val.split(','):
                    subfield_match = subfields_re.match(subfield.strip())
                    field, val = subfield_match.group(1).strip(), subfield_match.group(2).strip()
                    result[field] = val
                continue

            if val.startswith('None'):
                val = pd.NA

            if field == 'Playlist':
                playlist_match = playlist_re.match(val)
                result.update({
                    'TuneMin': playlist_match.group(1),
                    'TuneMax': playlist_match.group(2),
                    'TuneDefault': playlist_match.group(3)})
                for tune, tune_length in tunelengths.items():
                    result['TuneLength%u' % tune] = tune_length
                continue

            result[field] = val
    speed = result.get('SongSpeed', '')
    result['pal'] = int('PAL' in speed)
    int_result = {}
    for field, val in result.items():
        if isinstance(val, str):
            if len(val) == 0:
                val = pd.NA
            else:
                try:
                    val = int(val)
                except ValueError:
                    pass
        int_result[field] = val
    return int_result


def scrape_tunelengths(tunelengthfile):
    all_tunelengths = {}
    with open(tunelengthfile) as f:
        for line in f:
            if line.startswith(';') or line.startswith('['):
                continue
            tunelength_match = tunelength_re.match(line)
            md5_hash = tunelength_match.group(1)
            tunelength_raw = tunelength_match.group(2).split()
            tunelengths = {}
            for song, raw in enumerate(tunelength_raw, start=1):
                raw_match = tunelength_time_re.match(raw)
                tunelength = int(raw_match.group(1)) * 60
                tunelength += int(raw_match.group(2))
                if raw_match.group(3):
                    tunelength += 1
                tunelengths[song] = tunelength
            all_tunelengths[md5_hash] = tunelengths
    return all_tunelengths


def scrape_sids():
    current = pathlib.Path(r'.')
    currentdocs = pathlib.Path(r'./C64Music/DOCUMENTS')
    sidfiles = current.rglob(r'*.sid')
    all_tunelengths = {}
    for tunelengthfile in currentdocs.rglob(r'Songlengths.md5'):
        all_tunelengths.update(scrape_tunelengths(tunelengthfile))

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        result_futures = map(lambda x: executor.submit(scrape_sidinfo, x, all_tunelengths), sidfiles)
        results = [future.result() for future in concurrent.futures.as_completed(result_futures)]
    subprocess.check_call(['stty', 'sane'])

    df = pd.DataFrame(results)
    drops = ['Filename(s)']
    non_tunelengths = []

    for col, col_type in df.dtypes.items():
        if col_type is np.dtype('object'):
            n = df[col].nunique()
            if n == 1:
                drops.append(col)
            else:
                df.loc[df[col].isin(UNKNOWNS.val), [col]] = pd.NA
        if col in drops:
            continue
        if not col.startswith('TuneLength'):
            non_tunelengths.append(col)

    if drops:
        df = df.drop(drops, axis=1)

    tunemax = df['TuneMax'].max()
    tunelengths = ['TuneLength%u' % i for i in range(1, tunemax + 1)]
    df = df[non_tunelengths + tunelengths]

    return df

df = scrape_sids()
df.to_csv('sidinfo.csv', index=False, quoting=csv.QUOTE_NONNUMERIC)
