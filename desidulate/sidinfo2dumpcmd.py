#!/usr/bin/python3

import argparse
import os
from pyresidfp import SoundInterfaceDevice
from desidulate.fileio import read_csv

VICEIMAGE = 'anarkiwi/headlessvice'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('sidinfo', type=str)
    parser.add_argument('--hvscdir', default='/local/hvsc', type=str)
    args = parser.parse_args()

    df = read_csv(args.sidinfo)

    for row in df.itertuples():
        if row.pal:
            clock_freq = SoundInterfaceDevice.PAL_CLOCK_FREQUENCY
        else:
            clock_freq = SoundInterfaceDevice.NTSC_CLOCK_FREQUENCY
        path = row.path

        cycles = int(clock_freq * (row.length + 1))
        dname = os.path.join(args.hvscdir, os.path.dirname(path))
        bname = os.path.basename(path)
        dbname = '%s/%u/%s' % (bname, row.song, bname)
        dbname = dbname.replace('.sid', '')
        dbname = dbname + '-%u.dump' % row.song
        dbpath = os.path.join(dname, os.path.dirname(dbname))
        vice_cmd = [
            'docker', 'run', '--rm', '-v', '%s:/vice' % dname, '-i', VICEIMAGE,
            'vsid', '-warp', '-console', '-silent', '-sounddev', 'dump',
            '-soundarg', os.path.join('/vice', dbname),
            '-limit', str(cycles),
            '-tune', str(row.song),
            os.path.join('/vice', bname)]
        if not os.path.exists(dbpath):
            os.makedirs(dbpath)
        print(' '.join(vice_cmd))


if __name__ == '__main__':
    main()
