#!/usr/bin/python
import os
import subprocess

CGROUP_PATH = "/sys/fs/cgroup"


def read_cgroup_file_value(file_path):
    # Read only 1 line for these files as they are 'virtual' files
    try:
        if os.path.isfile(file_path) and os.access(file_path, os.R_OK):
            with open(file_path, 'r') as file_handler:
                value = file_handler.readline().rstrip("\n")
            return {"success": True, "data": value}
        else:
            return {"success": False, "error": str("Couldn't access file: " + file_path)}
    except IOError as e:
        return {"success": False, "error": str(e)}


def write_cgroup_file_value(file_path, value):
    # Write only 1 line for these files as they are 'virtual' files
    try:
        if os.path.isfile(file_path) and os.access(file_path, os.W_OK):
            with open(file_path, 'w') as file_handler:
                file_handler.write(str(value))
            return {"success": True, "data": value}
        else:
            return {"success": False, "error": str("Couldn't access file: " + file_path)}
    except IOError as e:
        return {"success": False, "error": str(e)}


# CPU #
CPU_LIMIT_CPUS_LABEL = "cpu_num"
CPU_LIMIT_ALLOWANCE_LABEL = "cpu_allowance_limit"
CPU_EFFECTIVE_CPUS_LABEL = "effective_num_cpus"
CPU_EFFECTIVE_LIMIT = "effective_cpu_limit"
TICKS_PER_CPU_PERCENTAGE = 1000
MAX_TICKS_PER_CPU = 100000


def get_node_cpus(container_name):
    # Get info from cgroups cpuacct subsystem
    cpu_accounting_path = "/".join([CGROUP_PATH, "cpuacct", "lxc", container_name, "cpu.cfs_quota_us"])
    op = read_cgroup_file_value(cpu_accounting_path)
    if op["success"]:
        cpu_limit = int(op["data"])
        if cpu_limit != -1:
            # A limit is set, else leave it untouched
            cpu_limit = int(op["data"]) / TICKS_PER_CPU_PERCENTAGE
    else:
        return False, op

    # Get info from cgroups cpuset subsystem
    cpus_path = "/".join([CGROUP_PATH, "cpuset", "lxc", container_name, "cpuset.cpus"])
    op = read_cgroup_file_value(cpus_path)
    if op["success"]:
        cpus = op["data"]
    else:
        return False, op

    # Get the number of effective, active cores for the container
    # 5-7 equals to 3 cores active
    # 0,1,2,4 equals to 4 cores active
    # 0-3,6 equals to 5 cores active
    effective_cpus = 0
    parts = cpus.split(",")
    for part in parts:
        ranges = part.split("-")
        if len(ranges) == 1:
            effective_cpus += 1  # No range so only 1 core
        else:
            effective_cpus += (int(ranges[1]) - int(ranges[0])) + 1

        # Get the effective limit of the container, if allowance is set, then it
    # is limited by number of cpus available otherwise it is the number of
    # cores multiplied per 100 for percentage
    if cpu_limit == -1:
        effective_limit = effective_cpus * 100
    else:
        effective_limit = min(cpu_limit, effective_cpus * 100)
    # cpu_limit = str(cpu_limit)

    final_dict = dict()
    final_dict[CPU_LIMIT_CPUS_LABEL] = cpus
    final_dict[CPU_EFFECTIVE_CPUS_LABEL] = effective_cpus
    final_dict[CPU_EFFECTIVE_LIMIT] = effective_limit
    final_dict[CPU_LIMIT_ALLOWANCE_LABEL] = cpu_limit

    return True, final_dict


def set_node_cpus(container_name, cpu_resource):
    applied_changes = dict()

    if CPU_LIMIT_ALLOWANCE_LABEL in cpu_resource:
        cpu_accounting_path = "/".join([CGROUP_PATH, "cpuacct", "lxc", container_name, "cpu.cfs_quota_us"])
        cpu_quota_path = "/".join([CGROUP_PATH, "cpuacct", "lxc", container_name, "cpu.cfs_period_us"])

        try:
            if cpu_resource[CPU_LIMIT_ALLOWANCE_LABEL] == "-1":
                cpu_limit = -1
            else:
                cpu_limit = int(cpu_resource[CPU_LIMIT_ALLOWANCE_LABEL])
        except ValueError as e:
            return False, {"error": str(e)}

        if cpu_limit == 0:
            quota = -1  # Set to max
        else:
            quota = TICKS_PER_CPU_PERCENTAGE * cpu_limit  # Every 1000 period ticks count as 1% of CPU

        # Write the number of ticks per second
        op = write_cgroup_file_value(cpu_quota_path, str(MAX_TICKS_PER_CPU))
        if not op["success"]:
            # Something happened
            return False, op

        # Write the quota for this container in ticks
        op = write_cgroup_file_value(cpu_accounting_path, str(quota))
        if not op["success"]:
            # Something happened
            return False, op

        # This change was applied successfully
        applied_changes[CPU_LIMIT_ALLOWANCE_LABEL] = str(quota / TICKS_PER_CPU_PERCENTAGE)

    if CPU_LIMIT_CPUS_LABEL in cpu_resource:
        # container.config["limits.cpu"] = cpu_resource[CPU_LIMIT_CPUS_LABEL]
        cpu_cpuset_path = "/".join([CGROUP_PATH, "cpuset", "lxc", container_name, "cpuset.cpus"])

        op = write_cgroup_file_value(cpu_cpuset_path, str(cpu_resource[CPU_LIMIT_CPUS_LABEL]))
        if not op["success"]:
            # Something happened
            return False, op

        # This change was applied successfully
        applied_changes[CPU_LIMIT_CPUS_LABEL] = str(cpu_resource[CPU_LIMIT_CPUS_LABEL])

    # Nothing bad happened
    return True, applied_changes


# MEM #
MEM_LIMIT_LABEL = "mem_limit"
LOWER_LIMIT_MEGABYTES = 64


def get_node_mem(container_name):
    final_dict = dict()
    memory_limit_path = "/".join([CGROUP_PATH, "memory", "lxc", container_name, "memory.limit_in_bytes"])

    op = read_cgroup_file_value(memory_limit_path)
    if op["success"]:
        mem_limit = op["data"]
    else:
        return op

    mem_limit_converted = int(mem_limit) / 1048576  # Convert to MB
    if mem_limit_converted > 65536:
        # more than 64G?, probably not limited so set to -1 ('unlimited')
        mem_limit_converted = str(-1)
        final_dict["unit"] = "unlimited"
    else:
        final_dict["unit"] = "M"

    final_dict[MEM_LIMIT_LABEL] = mem_limit_converted
    return True, final_dict


def set_node_mem(container_name, mem_resource):
    # Assume an integer for megabytes, add the M and set to cgroups
    if MEM_LIMIT_LABEL in mem_resource:
        value = int(mem_resource[MEM_LIMIT_LABEL])
        if value is -1:
            value_megabytes = str(value)
        elif value < LOWER_LIMIT_MEGABYTES:
            # Don't allow values lower than an amount like 64 MB as it will probably block the container
            return False, {"error": "Memory limit is too low, less than " + str(LOWER_LIMIT_MEGABYTES) + " MB"}
        else:
            value_megabytes = str(value) + 'M'

        memory_limit_path = "/".join([CGROUP_PATH, "memory", "lxc", container_name, "memory.limit_in_bytes"])
        op = write_cgroup_file_value(memory_limit_path, value_megabytes)
        if not op["success"]:
            # Something happened
            return False, op
        # Nothing bad happened
        return True, {MEM_LIMIT_LABEL: value}
    else:
        return True, {}


# DISK #
DISK_READ_LIMIT_LABEL = "disk_read_limit"
DISK_WRITE_LIMIT_LABEL = "disk_write_limit"


def get_system_mounted_filesystems():
    df = subprocess.Popen(["df", "--output=source,target"], stdout=subprocess.PIPE)
    trim = subprocess.Popen(["tr", "-s", "[:blank:]", ","], stdin=df.stdout, stdout=subprocess.PIPE)
    lines = trim.communicate()[0].strip().split('\n')
    return lines


def get_device_path_from_mounted_filesystem(path):
    filesystems = get_system_mounted_filesystems()
    for fs in filesystems:
        parts = fs.split(",")
        if parts[1] == path.rstrip("/"):
            return parts[0]
    return "not-found"


def get_device_major_minor(device_path):
    dmsetup = subprocess.Popen(
        ["dmsetup", "info", "-c", "-o", "major,minor", "--separator=,", "--noheadings", device_path],
        stdout=subprocess.PIPE)
    return dmsetup.communicate()[0].strip().split(",")


def get_node_disk_limits(container_name):
    blkio_path = "/".join([CGROUP_PATH, "blkio", "lxc", container_name])
    devices_read_limit_path = blkio_path + "/blkio.throttle.read_bps_device"
    devices_write_limit_path = blkio_path + "/blkio.throttle.write_bps_device"
    devices_read_limits = dict()
    devices_write_limits = dict()

    if os.path.isfile(devices_read_limit_path) and os.access(devices_read_limit_path, os.R_OK):
        devices_read_limit_file = open(devices_read_limit_path, 'r')
        for line in devices_read_limit_file:
            parts = line.rstrip("\n").split()
            major_minor = parts[0]
            limit = parts[1]
            devices_read_limits[major_minor] = limit
        devices_read_limit_file.close()

    if os.path.isfile(devices_write_limit_path) and os.access(devices_write_limit_path, os.R_OK):
        devices_write_limit_file = open(devices_write_limit_path, 'r')
        for line in devices_write_limit_file:
            parts = line.rstrip("\n").split()
            major_minor = parts[0]
            limit = parts[1]
            devices_write_limits[major_minor] = limit
        devices_write_limit_file.close()

    return devices_read_limits, devices_write_limits


def set_node_disk(container_name, disk_resource):
    major = disk_resource["major"]
    minor = disk_resource["minor"]
    blkio_path = "/".join([CGROUP_PATH, "blkio", "lxc", container_name])
    if DISK_READ_LIMIT_LABEL in disk_resource:
        limit_read = disk_resource[DISK_READ_LIMIT_LABEL]
        devices_read_limit_path = blkio_path + "/blkio.throttle.read_bps_device"

        op = write_cgroup_file_value(devices_read_limit_path, str(major + ":" + minor + " " + limit_read))
        if not op["success"]:
            # Something happened
            return False, op

    if DISK_WRITE_LIMIT_LABEL in disk_resource:
        limit_write = disk_resource[DISK_WRITE_LIMIT_LABEL]
        devices_write_limit_path = blkio_path + "/blkio.throttle.write_bps_device"

        op = write_cgroup_file_value(devices_write_limit_path, str(major + ":" + minor + " " + limit_write))
        if not op["success"]:
            # Something happened
            return False, op

    # Nothing bad happened
    return True, disk_resource


def get_node_disks(container_name, devices):
    retrieved_disks = list()
    limits_read, limits_write = get_node_disk_limits(container_name)
    for device in devices.keys():
        device_mountpoint = devices[device]["source"]
        device_path = get_device_path_from_mounted_filesystem(device_mountpoint)
        major, minor = get_device_major_minor(device_path)

        major_minor_str = major + ":" + minor

        if major_minor_str in limits_read:
            device_read_limit = limits_read[major_minor_str]
        else:
            device_read_limit = -1

        if major_minor_str in limits_write:
            device_write_limit = limits_write[major_minor_str]
        else:
            device_write_limit = -1

        disk_dict = dict()
        disk_dict["mountpoint"] = device_mountpoint
        disk_dict["device_path"] = device_path
        disk_dict["major"] = major
        disk_dict["minor"] = minor
        disk_dict[DISK_READ_LIMIT_LABEL] = device_read_limit
        disk_dict[DISK_WRITE_LIMIT_LABEL] = device_write_limit

        retrieved_disks.append(disk_dict)

    return True, retrieved_disks


# NET #
NET_UNIT_NAME_LABEL = "unit"
NET_DEVICE_HOST_NAME_LABEL = "device_name_in_host"
NET_DEVICE_NAME_LABEL = "device_name_in_container"
NET_LIMIT_LABEL = "net_limit"


def get_interface_limit(interface_name):
    tc = subprocess.Popen(["tc", "-d", "qdisc", "show", "dev", interface_name], stdout=subprocess.PIPE)
    lines = tc.communicate()[0].strip().split(",")
    parts = list()
    for line in lines:
        parts = line.rstrip("\n").split()  # Just 1 line should be available
        break
    if len(parts) > 6:
        return int(parts[7].strip("Mbit"))
    else:
        return -1


def unset_interface_limit(interface_name):
    try:
        tc = subprocess.Popen(["tc", "qdisc", "del", "dev", interface_name, "root"], stderr=subprocess.PIPE)
        tc.wait()
        if tc.returncode == 0:
            return True
        else:
            return False, {"error": "exit code of tc was: " + str(tc.returncode)}
    except subprocess.CalledProcessError as e:
        return False, {"error": "error trying to execute command:  " + str(e)}


# tc qdisc add dev veth6UQ01E root tbf rate 100Mbit burst 1000kb latency 100ms
def set_interface_limit(interface_name, net):
    try:
        net_limit = str(net[NET_LIMIT_LABEL]) + "Mbit"
        tc = subprocess.Popen(
            ["tc", "qdisc", "add", "dev", interface_name, "root", "tbf", "rate", net_limit, "burst",
             "1000kb", "latency", "100ms"], stderr=subprocess.PIPE)
        tc.wait()
        if tc.returncode == 0:
            return True, net
        else:
            return False, {"error": "exit code of tc was: " + str(tc.returncode)}
    except subprocess.CalledProcessError as e:
        return False, {"error": str(e)}


def set_node_net(net):
    if NET_LIMIT_LABEL in net:

        if NET_DEVICE_HOST_NAME_LABEL in net:
            # host network interface available (e.g., vethWMPX65)
            interface_in_host = net[NET_DEVICE_HOST_NAME_LABEL]
        else:
            # If no host interface name is available, it is not possible to do anything
            return False, {"error": "No host network interface name was provided"}

        if net[NET_LIMIT_LABEL] != -1 and net[NET_LIMIT_LABEL] != "":
            # Unset old limit and set new
            unset_interface_limit(interface_in_host)
            return set_interface_limit(interface_in_host, net)
        else:
            # Unset the limit, if it was not set before trying to unset it will give an error so skip it
            unset_interface_limit(interface_in_host)
            # Nothing bad happened
            return True, net

    else:
        # No limit to set, leave untouched
        # Nothing bad happened
        return True, net


def get_node_networks(networks):
    retrieved_nets = list()
    for net in networks:
        interface_host_name = net["host_interface"]

        net_dict = dict()
        net_dict[NET_DEVICE_NAME_LABEL] = net["container_interface"]
        net_dict[NET_DEVICE_HOST_NAME_LABEL] = interface_host_name
        net_dict[NET_LIMIT_LABEL] = get_interface_limit(interface_host_name)
        if net_dict[NET_LIMIT_LABEL] == -1:
            net_dict[NET_UNIT_NAME_LABEL] = "unlimited"
        else:
            net_dict[NET_UNIT_NAME_LABEL] = "Mbit"


        retrieved_nets.append(net_dict)

    return True, retrieved_nets
