#!/usr/bin/python3

import argparse
from desidulate.sidinfo import sidinfo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('sidfile', nargs='+')
    args = parser.parse_args()

    for f in args.sidfile:
        print(sidinfo(f))


if __name__ == '__main__':
    main()
