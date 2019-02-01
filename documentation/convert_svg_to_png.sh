#!/bin/bash
set -e
DPI=300
PARALLELL_DEGREE=4

function convert {
	i=0
	for filename in $(find *.svg 2> /dev/null); do
		new_file=$(basename $filename .svg)
		
		# No parallel option
		#inkscape -z -e $new_file.png -d $DPI $filename -D &> /dev/null
		
		# Parallelized
		inkscape -z -e $new_file.png -d $DPI $filename -D &> /dev/null &
		pids[${i}]=$!
		i=$(($i+1))
		if (( $i % $PARALLELL_DEGREE == 0 ))
		then
			for pid in ${pids[*]}; do
				wait $pid
			done
		fi
	done
	for pid in ${pids[*]}; do
		wait $pid
	done
}

for d in fixwindow_*/ ; do
    echo "Converting figures in $d to $DPI dpi"
    cd $d
    convert
    cd ..
done

echo "FINISHED"
