#!/bin/bash
while :
do
    wait=`shuf -i 30-60 -n 1`

    cpu_load=`shuf -i 10-80 -n 1`
    cpu_hoggers=`shuf -i 1-8 -n 1`
    echo "Going to hog approximately " $(($cpu_load*$cpu_hoggers)) "% from the cpu with " $cpu_hoggers " hoggers and sleep for: " $wait " seconds"
    stress-ng --cpu $cpu_hoggers --cpu-load $cpu_load --timeout $wait
    if [[ $? -ne 0 ]] ; then
        exit 1
    fi
    sleep 3
done
