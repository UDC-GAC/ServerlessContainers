#!/usr/bin/env bash
if [ $# -ne 3 ];
    then echo "illegal number of parameters"
    exit 1
fi

echo "$2 $3" > /sys/fs/cgroup/blkio/lxc/$1/blkio.throttle.read_bps_device
echo "$2 $3" > /sys/fs/cgroup/blkio/lxc/$1/blkio.throttle.write_bps_device

for f in `find /sys/fs/cgroup/blkio/lxc/$1/system.slice/ -maxdepth 1 -mindepth 1 -type d`; do
  echo "$2 $3" > "$f"/blkio.throttle.write_bps_device
  echo "$2 $3" > "$f"/blkio.throttle.read_bps_device
done

for f in `find /sys/fs/cgroup/blkio/lxc/$1/user.slice/ -maxdepth 1 -mindepth 1 -type d`; do
  echo "$2 $3" > "$f"/blkio.throttle.write_bps_device
  echo "$2 $3" > "$f"/blkio.throttle.read_bps_device
done

for f in `find /sys/fs/cgroup/blkio/lxc/$1/user.slice/user-0.slice/ -maxdepth 1 -mindepth 1 -type d`; do
  echo "$2 $3" > "$f"/blkio.throttle.write_bps_device
  echo "$2 $3" > "$f"/blkio.throttle.read_bps_device
done

exit 0