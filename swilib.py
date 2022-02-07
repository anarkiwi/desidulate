#!/usr/bin/python3

import struct
from itertools import groupby


def dot0(hexval):
    val = [(hexval[i:i+2]) for i in range(0, len(hexval), 2)]
    val = ['..' if i == '00' else i for i in val]
    return ''.join(val)


def sw_rle_diff(col, diffmult):
    pairs = [(int(pair[:2], 16), int(pair[2:], 16)) for pair in col]
    compressed_pairs = []
    while pairs and pairs[0][0] == 0:
        compressed_pairs.append((0, 0))
        pairs = pairs[1:]
    for prefix, pairs in groupby(pairs, key=lambda x: x[0]):
        suffixes = [pair[1] for pair in pairs]
        diffs = [0]
        for i, x in enumerate(suffixes[1:]):
            diffs.append(x - suffixes[i])
        for diff, vals in groupby(zip(suffixes, diffs), key=lambda x: x[1]):
            vals = list(vals)
            len_vals = len(vals)
            if len_vals == 1:
                compressed_pairs.append(((prefix, vals[0][0])))
            else:
                if not compressed_pairs:
                    compressed_pairs.append(((prefix, vals[0][0])))
                diff *= diffmult
                if diff < 0:
                    diff = ord(struct.pack('b', diff))
                compressed_pairs.append((len_vals, diff))
    while len(compressed_pairs) > 1:
        lastpair = compressed_pairs[-1]
        if lastpair[0] > 0x7f or lastpair[1] > 0:
            break
        compressed_pairs = compressed_pairs[:-1]
    compressed_pairs = ['%2.2X%2.2X' % i for i in compressed_pairs]
    compressed_pairs.extend(['0000'] * (len(col) - len(compressed_pairs)))
    return compressed_pairs
