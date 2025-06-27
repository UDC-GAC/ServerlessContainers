#!/usr/bin/env bash
if [ $# -ne 4 ];
    then echo "illegal number of parameters"
    exit 1
fi

COMMON_PATH=/sys/fs/cgroup/blkio/system.slice
CONTAINER_PID=$1
MAJOR_MINOR=$2
OPERATION=$3 # 0=read, 1=write
IO_LIMIT=$4

if [ $OPERATION == 0 ];
    then echo "$MAJOR_MINOR $IO_LIMIT" > $COMMON_PATH/apptainer-$CONTAINER_PID.scope/blkio.throttle.read_bps_device
elif [ $OPERATION == 1 ];
    then echo "$MAJOR_MINOR $IO_LIMIT" > $COMMON_PATH/apptainer-$CONTAINER_PID.scope/blkio.throttle.write_bps_device
else
    echo "operation $OPERATION not recognized; must be 0 for read or 1 for write"
    exit 1
fi

exit 0