#!/usr/bin/python3

import sys
from desidulate.sidinfo import sidinfo

for f in sys.argv[1:]:
    print(sidinfo(f))
