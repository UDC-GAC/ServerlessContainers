#!/bin/bash
while :
do
	wait=`shuf -i 30-400 -n 1`
	size=`shuf -i 100-8192 -n 1`
	echo "Going to hog approx· " $size "MB of memory and sleep for: " $wait " seconds"
	stress -m 1 --vm-bytes $((1024*1024*$size)) --vm-stride 16 -t $wait
done
