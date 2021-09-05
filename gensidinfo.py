#!/usr/bin/python3

# Copyright 2021 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.


import csv
import pathlib
import re
import subprocess
import concurrent.futures
import pandas as pd

MAX_WORKERS = 64
fields_re = re.compile(r'^\|\s+([^:]+)\s+:\s+([^:]+)\s*$')
subfields_re = re.compile(r'(.+)\s+\=\s+(.+)')

current = pathlib.Path(r'./')
sidfiles = current.rglob(r'*.sid')

def scrape_sidinfo(sidfile):
    result = {
        'path': str(sidfile),
        'mtime': sidfile.stat().st_mtime,
    }
    cmd = ['/usr/bin/sidplayfp', '-w/dev/null', '-t1', '-v', str(sidfile)]
    with subprocess.Popen(cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            shell=False,
            universal_newlines=True,
            errors='ignore') as process:
        _, err = process.communicate()
        for line in err.splitlines():
            fields_match = fields_re.match(line.strip())
            if fields_match:
                field, val = fields_match.group(1).strip(), fields_match.group(2).strip()
                subfields_match = subfields_re.match(val)
                if subfields_match and field not in ('Title', 'Author', 'Released'):
                    for subfield in val.split(','):
                        subfield_match = subfields_re.match(subfield.strip())
                        field, val = subfield_match.group(1).strip(), subfield_match.group(2).strip()
                        result[field] = val
                else:
                    result[field] = val
    speed = result.get('Song Speed', '')
    result['pal'] = 'PAL' in speed
    return result

with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    result_futures = map(lambda x: executor.submit(scrape_sidinfo, x), sidfiles)
    results = [future.result() for future in concurrent.futures.as_completed(result_futures)]

df = pd.DataFrame(results)
df[df.pal == True].drop(['pal'], axis=1).to_csv('sidinfo-pal.csv', index=0, quoting=csv.QUOTE_ALL)
df[df.pal == False].drop(['pal'], axis=1).to_csv('sidinfo-ntsc.csv', index=0, quoting=csv.QUOTE_ALL)
