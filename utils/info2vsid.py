#!/usr/bin/python3


import os
import sys
from pyresidfp import SoundInterfaceDevice
import pandas as pd
from desidulate.fileio import read_csv

TUNEDEFAULT = True
VICEIMAGE = 'anarkiwi/headlessvice'

csv = sys.argv[1]
df = read_csv(csv)
cwd = os.getcwd()

for row in df.itertuples():
    if row.pal:
        clock_freq = SoundInterfaceDevice.PAL_CLOCK_FREQUENCY
    else:
        clock_freq = SoundInterfaceDevice.NTSC_CLOCK_FREQUENCY
    tunemax = getattr(row, 'TuneMax')
    tunedefault = getattr(row, 'TuneDefault')

    def make_cmd(tune, add_tune, row):
        tunelength = getattr(row, 'TuneLength%u' % tune)
        cycles = int(clock_freq * (tunelength + 1))
        dname = os.path.join(cwd, os.path.dirname(row.path))
        bname = os.path.basename(row.path)
        if add_tune:
            dbname = '%s-%u.dump' % (bname, tune)
        else:
            dbname = '%s.dump' % bname
        vice_cmd = [
            'docker', 'run', '--rm', '-v', '%s:/vice' % dname, '-i', VICEIMAGE,
            'vsid', '-warp', '-console', '-silent', '-sounddev', 'dump',
            '-soundarg', os.path.join('/vice', dbname),
            '-limit', str(cycles),
            '-tune', str(tune),
            os.path.join('/vice', bname)]
        print(' '.join(vice_cmd))


    if TUNEDEFAULT:
        make_cmd(tunedefault, False, row)
    else:
        for tune in range(1, tunemax + 1):
            make_cmd(tune, True, row)
