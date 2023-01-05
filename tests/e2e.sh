#!/bin/bash

set -e

SID=$1

for DIR in $2 $3 ; do
    mkdir $DIR
    wget $SID -O$DIR/test.sid
    docker run --rm -v $(realpath $DIR):/vice -ti anarkiwi/headlessvice vsid -verbose -sounddev dump -soundarg /vice/test.dump -warp -limit 60000000 /vice/test.sid || true
    zstd --rm $DIR/test.dump
    reg2ssf --pal $DIR/test.dump.zst
    ssf2wav --pal $DIR/test.ssf.zst
    ssf2midi --pal $DIR/test.log.zst
done
