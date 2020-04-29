#!/usr/bin/python3

# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

from sidlib import get_reg_changes, get_reg_writes, real_sid_freq
from sidwav import get_sid, make_wav_from_reg


sid = get_sid()
reg_writes = get_reg_changes(get_reg_writes('vicesnd.sid'))
make_wav_from_reg(sid, reg_writes, 'sid.wav')
