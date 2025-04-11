#!/usr/bin/env bash
if [ $# -ne 5 ];
    then echo "illegal number of parameters"
    exit 1
fi

USER_ID=$1
CONTAINER_PID=$2
MAJOR_MINOR=$3
OPERATION=$4 # 0=read, 1=write
IO_LIMIT=$5

## Without sudo
#FILE_PATH=/sys/fs/cgroup/user.slice/user-$USER_ID.slice/user@$USER_ID.service/user.slice/apptainer-$CONTAINER_PID.scope/io.max

## With sudo (currently needed because 'network' parameter in apptainer requires root permissions)
FILE_PATH=/sys/fs/cgroup/system.slice/apptainer-$CONTAINER_PID.scope/io.max

if [ $OPERATION == 0 ];
    then echo "$MAJOR_MINOR rbps=$IO_LIMIT" > $FILE_PATH
elif [ $OPERATION == 1 ];
    then echo "$MAJOR_MINOR wbps=$IO_LIMIT" > $FILE_PATH
else
    echo "operation $OPERATION not recognized; must be 0 for read or 1 for write"
    exit 1
fi

exit 0
