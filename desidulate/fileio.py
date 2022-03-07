# Copyright 2020-2022 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import os
import pandas as pd


def read_csv(*args, **kwargs):
    return pd.read_csv(*args, **kwargs, engine='pyarrow')


def out_path(snd_log_name, new_ext):
    snd_log_name = os.path.expanduser(snd_log_name)
    base = os.path.basename(snd_log_name)
    recogized_exts = {'xz', 'gz', 'dump', 'log', 'sid', 'txt', 'ssf'}
    while True:
        dot = base.rfind('.')
        if dot <= 0:
            break
        ext = base[dot+1:]
        if not ext:
            break
        if ext not in recogized_exts:
            break
        base = base[:dot]
    return os.path.join(os.path.dirname(snd_log_name), '.'.join((base, new_ext)))


def midi_path(snd_log_name):
    return out_path(snd_log_name, 'mid')


def wav_path(snd_log_name, hashid=None):
    if hashid:
        return out_path(snd_log_name, '%d.wav' % hashid)
    return out_path(snd_log_name, 'wav')
