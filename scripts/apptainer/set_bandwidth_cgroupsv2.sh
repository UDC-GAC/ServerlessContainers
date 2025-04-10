#!/usr/bin/env bash
if [ $# -ne 4 ];
    then echo "illegal number of parameters"
    exit 1
fi

USER_ID=$1
CONTAINER_PID=$2
MAJOR_MINOR=$3
LIMIT_WRITE=$4

## Without sudo
#FILE_PATH=/sys/fs/cgroup/user.slice/user-$USER_ID.slice/user@$USER_ID.service/user.slice/apptainer-$CONTAINER_PID.scope/io.max

## With sudo (currently needed because 'network' parameter in apptainer requires root permissions)
FILE_PATH=/sys/fs/cgroup/system.slice/apptainer-$CONTAINER_PID.scope/io.max

echo "$MAJOR_MINOR rbps=$LIMIT_WRITE wbps=$LIMIT_WRITE" > $FILE_PATH

exit 0
