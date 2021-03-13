# Copyright 2020 Josh Bailey (josh@vandervecken.com)

## Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

import gzip
import lzma
import os


def out_path(snd_log_name, new_ext):
    snd_log_name = os.path.expanduser(snd_log_name)
    base = os.path.basename(snd_log_name)
    recogized_exts = {'xz', 'gz', 'dump', 'log', 'sid', 'txt'}
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


def wav_path(snd_log_name):
    return out_path(snd_log_name, 'wav')


def file_reader(snd_log_name):
    snd_log_name = os.path.expanduser(snd_log_name)
    if snd_log_name.endswith('.gz'):
        return gzip.open(snd_log_name, 'rb')
    if snd_log_name.endswith('.xz'):
        return lzma.open(snd_log_name, 'rb')
    return open(snd_log_name)
