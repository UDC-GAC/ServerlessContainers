#!/bin/bash
while :
do
	wait=`shuf -i 30-400 -n 1`
	
	memory_size=`shuf -i 100-4096 -n 1`
	echo "Going to hog approximately " $memory_size "MB of memory and sleep for: " $wait " seconds"
	stress-ng -m 4 --vm-bytes $((256*1024*$memory_size)) --timeout $wait
	
	#cpu_load=`shuf -i 10-80 -n 1`
	#cpu_hoggers=`shuf -i 1-3 -n 1`
	#echo "Going to hog approximately " $cpu_load "% from the cpu with " $cpu_hoggers " hoggers and sleep for: " $wait " seconds"
	#stress-ng --cpu $cpu_hoggers --cpu-load $cpu_load --timeout $wait
	
	# Wait a little bit to let memory be reclaimed
	sleep 10
done
