#!/usr/bin/python3

# Copyright 2020-2022 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import argparse
import csv
import hashlib
import json
import logging
import multiprocessing
import os
import pathlib
import re
import random
import concurrent.futures
import numpy as np
import pandas as pd

from desidulate.sidinfo import sidinfo

MAX_WORKERS = int(multiprocessing.cpu_count() / 2)
UNKNOWNS = pd.DataFrame([{'val': val} for val in ('<?>', 'UNKNOWN')])
tunename_re = re.compile(r'^; (.+.sid)$')
tunelength_re = re.compile(r'([a-z\d]+)=([\d+\s+\:\.]+)$')
tunelength_time_re = re.compile(r'(\d+)\:(\d+)\.*(\d*)$')


def scrape_sidinfo(i, sidfile, tunelengths, cache):
    logging.info('scraping %u: %s', i, sidfile)
    sidinfo_file = str(sidfile)
    sidinfo_file = sidinfo_file[:sidinfo_file.rfind(".")]
    sidinfo_file = os.path.basename(sidinfo_file) + ".sidinfo"
    sidinfo_dir = os.path.dirname(sidinfo_file)
    if not os.path.exists(sidinfo_dir):
        os.makedirs(sidinfo_dir)
    if not os.path.exists(sidinfo_file) or not cache:
        with open(sidfile, 'rb') as f:
            md5_hash = hashlib.md5(f.read()).hexdigest()
        results = []
        path = str(os.path.normpath(sidfile))
        mtime = sidfile.stat().st_mtime
        for result in sidinfo(path):
            result.update({
                'path': path,
                'mtime': mtime,
                'md5': md5_hash,
                'length': tunelengths[result['song']]})
            results.append(result)
        sidinfo_file_tmp = sidinfo_file.replace(
            os.path.basename(sidinfo_file), '.' + os.path.basename(sidinfo_file))

        with open(sidinfo_file_tmp, 'w', encoding='utf8') as f:
            f.write(json.dumps(results))
        os.rename(sidinfo_file_tmp, sidinfo_file)
    with open(sidinfo_file, 'r', encoding='utf8') as f:
        results = json.loads(f.read())
        logging.info('%s: %s', sidfile, results)
        return results


def scrape_tunelengths(tunelengthfile):
    all_tunelengths = {}
    tunename = None
    with open(tunelengthfile, encoding='utf8') as f:
        for line in f:
            tunename_match = tunename_re.match(line)
            if tunename_match:
                tunename = os.path.join('C64Music', tunename_match.group(1)[1:])
                continue
            tunelength_match = tunelength_re.match(line)
            if not tunelength_match:
                continue
            assert tunename
            md5_hash = tunelength_match.group(1)
            tunelength_raw = tunelength_match.group(2).split()
            tunelengths = {}
            for song, raw in enumerate(tunelength_raw, start=1):
                raw_match = tunelength_time_re.match(raw)
                if raw_match is None:
                    raise ValueError(raw)
                tunelength = int(raw_match.group(1)) * 60
                tunelength += int(raw_match.group(2))
                if raw_match.group(3):
                    tunelength += 1
                tunelengths[song] = tunelength
            all_tunelengths[md5_hash] = tunelengths
            all_tunelengths[tunename] = tunelengths
            tunename = None
    return all_tunelengths


def scrape_sids(hvscdir, cache):
    current = pathlib.Path(hvscdir)
    currentdocs = pathlib.Path(os.path.join(current, 'C64Music/DOCUMENTS'))
    sidfiles = list(sorted(current.rglob('*.sid')))
    random.shuffle(sidfiles)
    logging.info('scraping %u sidfiles', len(sidfiles))
    all_tunelengths = {}
    for tunelengthfile in currentdocs.rglob(r'Songlengths.md5'):
        all_tunelengths.update(scrape_tunelengths(tunelengthfile))
    missing_sidfiles = {str(sidfile) for sidfile in sidfiles} - set(all_tunelengths)
    if missing_sidfiles:
        print('no tunelengths for %s' % missing_sidfiles)
        for sidfile in missing_sidfiles:
            sidfiles.remove(pathlib.Path(sidfile))
    assert len(all_tunelengths) / 2 == len(sidfiles), (len(all_tunelengths), len(sidfiles))

    with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        result_futures = []
        for i, sidfile in enumerate(sidfiles, start=1):
            result_futures.append(executor.submit(scrape_sidinfo, i, sidfile, all_tunelengths[str(sidfile)], cache))
        results = []
        for future in concurrent.futures.as_completed(result_futures):
            results.extend(future.result())

    df = pd.DataFrame(results)
    drops = []

    for col, col_type in df.dtypes.items():
        if col_type is np.dtype('object'):
            n = df[col].nunique()
            if n == 1:
                drops.append(col)
            else:
                df.loc[df[col].isin(UNKNOWNS.val), [col]] = pd.NA
        if col in drops:
            continue

    if drops:
        df = df.drop(drops, axis=1)

    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--hvscdir', default='.', type=str)
    cache_parser = parser.add_mutually_exclusive_group(required=False)
    cache_parser.add_argument('--cache', dest='cache', action='store_true', help='Use cache')
    cache_parser.add_argument('--nocache', dest='cache', action='store_false', help='Do not cache')
    parser.set_defaults(cache=True)

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    df = scrape_sids(args.hvscdir, args.cache)
    df.to_csv(os.path.join(args.hvscdir, 'sidinfo.csv'), index=False, quoting=csv.QUOTE_NONNUMERIC)


if __name__ == '__main__':
    main()
