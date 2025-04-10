#!/usr/bin/env bash
if [ $# -ne 3 ];
    then echo "illegal number of parameters"
    exit 1
fi

COMMON_PATH=/sys/fs/cgroup/blkio/system.slice
CONTAINER_PID=$1
MAJOR_MINOR=$2
LIMIT_WRITE=$3

echo "$MAJOR_MINOR $LIMIT_WRITE" > $COMMON_PATH/apptainer-$CONTAINER_PID.scope/blkio.throttle.read_bps_device
echo "$MAJOR_MINOR $LIMIT_WRITE" > $COMMON_PATH/apptainer-$CONTAINER_PID.scope/blkio.throttle.write_bps_device

exit 0