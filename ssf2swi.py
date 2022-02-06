#!/usr/bin/python3

import argparse
import struct
from itertools import groupby
import pandas as pd
from sidlib import resampledf_to_pr, get_sid, CONTROL_BITS, timer_args, timer_args, timer_args, timer_args
from ssf import add_freq_notes_df


# -8369400230369463243, C64Music/MUSICIANS/H/Hubbard_Rob/Commando.ssf.xz
# -6332327843409751282, C64Music/MUSICIANS/L/Linus/Ride_the_High_Country.ssf.xz
# -1975247557004053752.wav, C64Music/MUSICIANS/L/Linus/Cauldron_II_Remix.ssf.xz
parser = argparse.ArgumentParser(description='Transcribe SSF to Sid Wizard instrument')
parser.add_argument('--ssffile', help='SSF file', default='C64Music/MUSICIANS/L/Linus/Ride_the_High_Country.ssf.xz')
parser.add_argument('--hashid', type=int, help='hashid to transcribe', default=-6332327843409751282)
timer_args(parser)

args = parser.parse_args()
sid = get_sid(args.pal)


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
                diff *= diffmult
                if diff < 0:
                    diff = ord(struct.pack('b', diff))
                compressed_pairs.append((len_vals, diff))
    lastpair = compressed_pairs[-1]
    if lastpair[0] <= 0x7f and lastpair[1] == 0:
        compressed_pairs = compressed_pairs[:-1]
    compressed_pairs = ['%2.2X%2.2X' % i for i in compressed_pairs]
    compressed_pairs.extend(['0000'] * (len(col) - len(compressed_pairs)))
    return compressed_pairs


def dot0(hexval):
    val = [(hexval[i:i+2]) for i in range(0, len(hexval), 2)]
    val = ['..' if i == '00' else i for i in val]
    return ''.join(val)


def wf_from_row(row):
    val = 0
    for b, col in enumerate(CONTROL_BITS):
        col_val = getattr(row, col + '1', 0)
        if pd.notna(col_val) and col_val:
            val += 2**b
    return '%2.2X' % val


def arp_from_row(row):
    arp = getattr(row, 'freq1', 0)
    val = 0
    if pd.notna(arp):
        val = row.closest_note - 12 + 0x81
    return '%2.2X' % val


def pulse_from_row(row):
    pwduty = getattr(row, 'pwduty1', 0)
    val = 0
    if pd.notna(pwduty):
        val = pwduty | 0x8000
    return '%4.4X' % val


def filter_from_row(row):
    val = 0
    route_map = {
        (0, 0, 0): 0x8,
        (1, 0, 0): 0x9,
        (1, 1, 0): 0xb,
        (0, 0, 1): 0xc,
        (1, 0, 1): 0xd,
        (0, 1, 1): 0xe,
        (1, 1, 1): 0xf,
    }

    if pd.notna(row.flt1) and row.flt1:
        coff = row.fltcoff
        res = row.fltres
        route = route_map.get((row.fltlo, row.fltband, row.flthi)) << 4
        val = ((route | res) << 8) | (coff >> 3)

    return '%4.4X' % val


df = pd.read_csv(args.ssffile, dtype=pd.Int64Dtype())
ssf_df = df[df.hashid == args.hashid].drop(['clock', 'hashid_noclock', 'count', 'rate', 'vol', 'vbi_frame', 'hashid', 'fltext'], axis=1)
ssf_df = resampledf_to_pr(sid, ssf_df).reset_index(drop=True)

atk1, dec1, sus1, rel1, pr_speed, test1_initial = ssf_df[['atk1', 'dec1', 'sus1', 'rel1', 'pr_speed', 'test1']].iloc[0]
ssf_df = ssf_df.drop(['atk1', 'dec1', 'sus1', 'rel1', 'pr_speed'], axis=1)

if atk1 == 0:
    first_freq = ssf_df.index[ssf_df['freq1'].notna()][0]
    ssf_df = ssf_df[first_freq:]
    ssf_df['pr_frame'] = ssf_df['pr_frame'] - ssf_df['pr_frame'].min()
if rel1 == 0:
    ssf_df = ssf_df[ssf_df['gate1'] == 1]

ssf_df = ssf_df.set_index('pr_frame')
ssf_df = add_freq_notes_df(sid, ssf_df)
ssf_df['real_freq'] = ssf_df['real_freq'].round(2)

ssf_df['F'] = ssf_df.apply(lambda x: '%2.2X' % x.name, axis=1)
ssf_df['WF'] = ssf_df.apply(wf_from_row, axis=1)
ssf_df['ARP'] = ssf_df.apply(arp_from_row, axis=1)
ssf_df['PULSE'] = ssf_df.apply(pulse_from_row, axis=1)
ssf_df['FILT'] = ssf_df.apply(filter_from_row, axis=1)
ssf_df['FILT'] = sw_rle_diff(ssf_df['FILT'], diffmult=2**3)
ssf_df['PULSE'] = sw_rle_diff(ssf_df['PULSE'], diffmult=1)
ssf_df[['ARP', 'PULSE', 'FILT']] = ssf_df[['ARP', 'PULSE', 'FILT']].apply(
    lambda row: [dot0(c) for c in row])

print('multispeed: %u' % pr_speed)

adsr = '%X%X%X%X' % (atk1, dec1, sus1, rel1)
print('ADSR: %s' % adsr)

print()
pd.set_option('display.max_rows', None)
print(ssf_df)
