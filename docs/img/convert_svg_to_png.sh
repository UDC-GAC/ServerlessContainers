#!/bin/bash
for filename in $(find *.svg 2> /dev/null); do
	new_file=$(basename $filename .svg)
	inkscape -z -e $new_file.png -d 600 $filename -D
done
