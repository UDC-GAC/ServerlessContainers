echo "0,2" > /sys/fs/cgroup/cpuset/lxc/node0/cpuset.cpus
echo "1,3" > /sys/fs/cgroup/cpuset/lxc/node1/cpuset.cpus
echo "4,6" > /sys/fs/cgroup/cpuset/lxc/node2/cpuset.cpus
echo "5,7" > /sys/fs/cgroup/cpuset/lxc/node3/cpuset.cpus

echo "8G" > /sys/fs/cgroup/memory/lxc/node0/memory.limit_in_bytes
echo "8G" > /sys/fs/cgroup/memory/lxc/node1/memory.limit_in_bytes
echo "8G" > /sys/fs/cgroup/memory/lxc/node2/memory.limit_in_bytes
echo "8G" > /sys/fs/cgroup/memory/lxc/node3/memory.limit_in_bytes


echo "253:7 1024000" > /sys/fs/cgroup/blkio/lxc/node0/blkio.throttle.read_bps_device
echo "253:16 1024000" > /sys/fs/cgroup/blkio/lxc/node1/blkio.throttle.read_bps_device
echo "253:17 1024000" > /sys/fs/cgroup/blkio/lxc/node2/blkio.throttle.read_bps_device
echo "253:18 1024000" > /sys/fs/cgroup/blkio/lxc/node3/blkio.throttle.read_bps_device
echo "253:7 1024000" > /sys/fs/cgroup/blkio/lxc/node0/blkio.throttle.write_bps_device
echo "253:16 1024000" > /sys/fs/cgroup/blkio/lxc/node1/blkio.throttle.write_bps_device
echo "253:17 1024000" > /sys/fs/cgroup/blkio/lxc/node2/blkio.throttle.write_bps_device
echo "253:18 1024000" > /sys/fs/cgroup/blkio/lxc/node3/blkio.throttle.write_bps_device
