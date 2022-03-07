#!/usr/bin/python3

# Copyright 2020-2022 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

# https://codebase64.org/doku.php?id=base:building_a_music_routine
# http://www.ucapps.de/howto_sid_wavetables_1.html

import argparse
import logging
from desidulate.fileio import out_path
from desidulate.sidlib import get_sid, reg2state, state2ssfs, timer_args


def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(message)s')

    parser = argparse.ArgumentParser(description='Convert vicesnd.sid log into SSF log files')
    parser.add_argument('logfile', default='vicesnd.sid', help='log file to read')
    parser.add_argument('--maxstates', default=int(10 * 1e6), help='maximum number of SID states to analyze')
    parser.add_argument('--dfext', default='xz', help='default dataframe extension')
    timer_args(parser)
    args = parser.parse_args()

    sid = get_sid(args.pal)
    df = reg2state(args.logfile, nrows=int(args.maxstates))
    ssf_log_df, ssf_df = state2ssfs(sid, df)

    for ext, filedf in (
            ('.'.join(('log', args.dfext)), ssf_log_df),
            ('.'.join(('ssf', args.dfext)), ssf_df)):
        filename = out_path(args.logfile, ext)
        logging.debug('writing %s', filename)
        filedf.to_csv(filename)


if __name__ == '__main__':
    main()
