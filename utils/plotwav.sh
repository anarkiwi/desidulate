#!/bin/sh

inwav=$1

if [ ! -f "$inwav" ] ; then
    exit 1
fi

outpng=$(echo $inwav |sed 's/.wav$/.png/')
title=$(basename $inwav)
ffmpeg -loglevel 0 -i $inwav -ac 1 -filter:a aresample=1000000 -map 0:a -c:a pcm_s16le -f data - | gnuplot -p -e "set terminal png size 2048,512; set output '$outpng'; set xlabel 'us'; set title '$title' noenhanced; plot '<cat' binary filetype=bin format='%int16' endian=little array=1:0 with lines title '';"
