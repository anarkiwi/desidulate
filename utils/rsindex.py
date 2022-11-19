#!/usr/bin/python3

import glob
import os
import re
from collections import defaultdict
import pandas as pd

file_re = os.path.join('**', '*.resample_ssf*.xz')
resample_ssf_re = re.compile(r'^.+\/([^\/]+\/[^\/]+)\.resample_ssf\.\d+\.+([^\.]+).xz$')

waveform_dir = 'waveforms'
if not os.path.exists(waveform_dir):
    os.mkdir(waveform_dir)

files = [file for file in glob.glob(file_re, recursive=True)]
waveforms = defaultdict(list)
for file in files:
    match = resample_ssf_re.match(file)
    waveform = match.group(2)
    waveforms[waveform].append(file)

for waveform, files in sorted(waveforms.items(), key=lambda x: len(x[1])):
    files = sorted(files)
    print(waveform, len(files))
    dfs = [pd.read_csv(file) for file in files]
    for i, file in enumerate(files):
        dfs[i]['file'] = file
    df = pd.concat(dfs)
    df.to_csv(f'{waveform_dir}/{waveform}.csv.xz', index=False)
