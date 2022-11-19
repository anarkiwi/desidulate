#!/usr/bin/python3

import sys
from desidulate.sidinfo import sidinfo


def main():
    for f in sys.argv[1:]:
        print(sidinfo(f))


if __name__ == '__main__':
    main()
