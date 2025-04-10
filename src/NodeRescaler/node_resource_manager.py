#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 Universidade da Coruña
# Authors:
#     - Jonatan Enes [main](jonatan.enes@udc.es)
#     - Roberto R. Expósito
#     - Juan Touriño
#
# This file is part of the ServerlessContainers framework, from
# now on referred to as ServerlessContainers.
#
# ServerlessContainers is free software: you can redistribute it
# and/or modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation, either version 3
# of the License, or (at your option) any later version.
#
# ServerlessContainers is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ServerlessContainers. If not, see <http://www.gnu.org/licenses/>.


import os
import subprocess

CGROUP_PATH = "/sys/fs/cgroup"

def get_cgroup_file_path(container_id, resource, cgroup_file, container_engine):
    if container_engine == "lxc":
        container_name = container_id
        return "/".join([CGROUP_PATH, resource, "lxc.payload.{0}".format(container_name), cgroup_file])

    elif container_engine == "apptainer":
        container_pid = container_id
        return "/".join([CGROUP_PATH, resource, "system.slice", "apptainer-{0}.scope".format(container_pid), cgroup_file])

    else:
        raise Exception("Error: a non-valid container engine was specified")

def read_cgroup_file_value(file_path):
    # Read only 1 line for these files as they are 'virtual' files
    try:
        if os.path.isfile(file_path) and os.access(file_path, os.R_OK):
            with open(file_path, 'r') as file_handler:
                value = file_handler.readline().rstrip("\n")
            return {"success": True, "data": value}
        else:
            return {"success": False, "error": "Couldn't access file: {0}".format(file_path)}
    except IOError as e:
        return {"success": False, "error": str(e)}


def write_cgroup_file_value(file_path, value):
    # Write only 1 line for these files as they are 'virtual' files
    try:
        if os.path.isfile(file_path) and os.access(file_path, os.W_OK):
            with open(file_path, 'w') as file_handler:
                # with open(file_path, 'r+') as file_handler:
                file_handler.write(str(value))
            return {"success": True, "data": value}
        else:
            return {"success": False, "error": "Couldn't access file: {0}".format(file_path)}
    except IOError as e:
        return {"success": False, "error": str(e)}


# CPU #
CPU_LIMIT_CPUS_LABEL = "cpu_num"
CPU_LIMIT_ALLOWANCE_LABEL = "cpu_allowance_limit"
CPU_EFFECTIVE_CPUS_LABEL = "effective_num_cpus"
CPU_EFFECTIVE_LIMIT = "effective_cpu_limit"
TICKS_PER_CPU_PERCENTAGE = 1000
MAX_TICKS_PER_CPU = 100000


def get_node_cpus(container_id, container_engine):
    # Get info from cgroups cpuacct subsystem
    #cpu_accounting_path = "/".join([CGROUP_PATH, "cpuacct", "lxc.payload.{0}".format(container_id), "cpu.cfs_quota_us"])
    cpu_accounting_path = get_cgroup_file_path(container_id, "cpuacct", "cpu.cfs_quota_us", container_engine)
    op = read_cgroup_file_value(cpu_accounting_path)
    if op["success"]:
        cpu_limit = int(op["data"])
        if cpu_limit != -1:
            # A limit is set, else leave it untouched
            cpu_limit = int(op["data"]) / TICKS_PER_CPU_PERCENTAGE
    else:
        return False, op

    # Get info from cgroups cpuset subsystem
    #cpus_path = "/".join([CGROUP_PATH, "cpuset", "lxc.payload.{0}".format(container_id), "cpuset.cpus"])
    cpus_path = get_cgroup_file_path(container_id, "cpuset", "cpuset.cpus", container_engine)
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
    # is medium-limit by number of cpus available otherwise it is the number of
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


def set_node_cpus(container_id, cpu_resource, container_engine):
    applied_changes = dict()

    if CPU_LIMIT_ALLOWANCE_LABEL in cpu_resource:
        #cpu_accounting_path = "/".join([CGROUP_PATH, "cpuacct", "lxc.payload.{0}".format(container_id), "cpu.cfs_quota_us"])
        #cpu_quota_path = "/".join([CGROUP_PATH, "cpuacct", "lxc.payload.{0}".format(container_id), "cpu.cfs_period_us"])
        cpu_accounting_path = get_cgroup_file_path(container_id, "cpuacct", "cpu.cfs_quota_us", container_engine)
        cpu_quota_path = get_cgroup_file_path(container_id, "cpuacct", "cpu.cfs_period_us", container_engine)

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
        #cpu_cpuset_path = "/".join([CGROUP_PATH, "cpuset", "lxc.payload.{0}".format(container_id), "cpuset.cpus"])
        cpu_cpuset_path = get_cgroup_file_path(container_id, "cpuset", "cpuset.cpus", container_engine)

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


def get_node_mem(container_id, container_engine):
    final_dict = dict()
    #memory_limit_path = "/".join([CGROUP_PATH, "memory", "lxc.payload.{0}".format(container_id), "memory.limit_in_bytes"])
    memory_limit_path = get_cgroup_file_path(container_id, "memory", "memory.limit_in_bytes", container_engine)

    op = read_cgroup_file_value(memory_limit_path)
    if op["success"]:
        mem_limit = op["data"]
    else:
        return op

    mem_limit_converted = int(mem_limit) / 1048576  # Convert to MB
    if mem_limit_converted > 262144:
        # more than 256G?, probably not medium-limit so set to -1 ('unlimited')
        mem_limit_converted = -1
        final_dict["unit"] = "unlimited"
    else:
        final_dict["unit"] = "M"

    final_dict[MEM_LIMIT_LABEL] = mem_limit_converted
    return True, final_dict


def set_node_mem(container_id, mem_resource, container_engine):
    # Assume an integer for megabytes, add the M and set to cgroups
    if MEM_LIMIT_LABEL in mem_resource:
        value = int(mem_resource[MEM_LIMIT_LABEL])
        value_megabytes_integer = 0
        if value == -1:
            value_megabytes = str(value)
        elif value < LOWER_LIMIT_MEGABYTES:
            # Don't allow values lower than an amount like 64 MB as it will probably block the container
            return False, {"error": "Memory limit is too low, less than {0} MB".format(str(LOWER_LIMIT_MEGABYTES))}
        else:
            value_megabytes_integer = value
            value_megabytes = str(value) + 'M'

        # Set the swap first to the same amount of memory due to centos not allowing less memory than swap
        # swap_limit_path = "/".join([CGROUP_PATH, "memory", "lxc", container_id, "memory.memsw.limit_in_bytes"])
        #memory_limit_path = "/".join([CGROUP_PATH, "memory", "lxc.payload.{0}".format(container_id), "memory.limit_in_bytes"])
        memory_limit_path = get_cgroup_file_path(container_id, "memory", "memory.limit_in_bytes", container_engine)

        # Get the current memory limit in megabytes, that should be equal to the swap space
        success, current_mem_value = get_node_mem(container_id, container_engine)
        current_mem_value = current_mem_value[MEM_LIMIT_LABEL]
        if current_mem_value < value_megabytes_integer:
            # If we are to lower the amount, first memory, then swap
            mem_op = write_cgroup_file_value(memory_limit_path, value_megabytes)
            # swap_op = write_cgroup_file_value(swap_limit_path, value_megabytes)
        else:
            # If we are to increase the amount, first swap, then memory
            # swap_op = write_cgroup_file_value(swap_limit_path, value_megabytes)
            mem_op = write_cgroup_file_value(memory_limit_path, value_megabytes)

        if not mem_op["success"]:
            # Something happened with memory limit
            return False, "Memory error {0}".format(mem_op)
        # if not swap_op["success"]:
        # Something happened with swap limit
        #    return False, "Memory error {0}".format(swap_op)
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
    lines = trim.communicate()[0].decode('utf-8').strip().split('\n')
    return lines


def get_device_path_from_mounted_filesystem(path):
    filesystems = get_system_mounted_filesystems()
    for fs in filesystems:
        parts = fs.split(",")
        if parts[1] == path.rstrip("/"):
            return parts[0]
    return None


def get_device_major_minor_from_volumes(device_path):
    ## With dmsetup (requires root permissions)
    # dmsetup = subprocess.Popen(
    #     ["sudo","dmsetup", "info", "-c", "-o", "major,minor", "--separator=,", "--noheadings", device_path],
    #     stdout=subprocess.PIPE)
    # result = dmsetup.communicate()[0]
    # if dmsetup.returncode == 0:
    #     # TODO check that this still works for volumes
    #     return result.decode('utf-8').strip().split(",")
    # else:
    #     return None

    ## With just ls
    real_device_path = os.path.realpath(device_path)
    ls = subprocess.Popen(
        ["ls", "-l", real_device_path],
        stdout=subprocess.PIPE)
    result = ls.communicate()[0]
    if ls.returncode == 0:
        output = result.decode('utf-8').split()
        return [output[4].strip(','),output[5]]
    else:
        return None


def get_device_major_minor_raw_device(device_path):
    stat = subprocess.Popen(
        ["stat", "-c", "%t,%T", device_path],
        stdout=subprocess.PIPE)

    out, err = stat.communicate()
    if stat.returncode == 0:
        both = out.decode('utf-8').split(",")
        major_hex, minor_hex = both[0], both[1]
        return str(int(major_hex, 16)), str(int(minor_hex, 16))
    else:
        return None


def get_node_disk_limits(container_id, container_engine):
    #blkio_path = "/".join([CGROUP_PATH, "blkio", "lxc.payload.{0}".format(container_id)])
    #devices_read_limit_path = blkio_path + "/blkio.throttle.read_bps_device"
    #devices_write_limit_path = blkio_path + "/blkio.throttle.write_bps_device"
    devices_read_limit_path = get_cgroup_file_path(container_id, "blkio", "blkio.throttle.read_bps_device", container_engine)
    devices_write_limit_path = get_cgroup_file_path(container_id, "blkio", "blkio.throttle.write_bps_device", container_engine)

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


def set_node_disk(container_id, disk_resource, device, container_engine):

    try:
        major, minor = get_device_major_minor(device)
    except TypeError:
        # None was returned
        return False, {"error": "No major and minor found for device {0}".format(device)}

    if DISK_WRITE_LIMIT_LABEL in disk_resource:
        limit_write = int(disk_resource[DISK_WRITE_LIMIT_LABEL]) * 1048576
        try:

            script_dir = os.path.dirname(os.path.realpath(__file__))
            set_bandwidth_script_path = "/".join([script_dir, "..", "..", "scripts", container_engine, "set_bandwidth_cgroupsv1.sh"])
            set_disk_bandwidth = subprocess.Popen(
                ["/bin/bash", set_bandwidth_script_path, str(container_id), "{0}:{1}".format(major, minor), str(limit_write)],
                stderr=subprocess.PIPE)

            out, err = set_disk_bandwidth.communicate()
            if set_disk_bandwidth.returncode == 0:
                pass
            else:
                return False, {"error": "exit code of set_disk_bandwidth was: {0} with error message: {1}".format(str(
                    set_disk_bandwidth.returncode), str(err))}
        except subprocess.CalledProcessError as e:
            return False, {"error": str(e)}

    # Nothing bad happened
    return True, disk_resource

# def set_node_disk(container_id, disk_resource, container_engine):
#     major = disk_resource["major"]
#     minor = disk_resource["minor"]

#     if DISK_WRITE_LIMIT_LABEL in disk_resource:
#         limit_write = disk_resource[DISK_WRITE_LIMIT_LABEL]
#         try:
#             # TODO FIX the path issue
#             # TODO and use function to differentiate between container engines
#             # set_bandwidth_script_path = "/".join([os.getcwd(), "NodeRescaler"])
#             set_bandwidth_script_path = "/".join([os.getcwd()])
#             set_disk_bandwidth = subprocess.Popen(
#                 ["/bin/bash", "{0}/set_bandwidth.sh".format(set_bandwidth_script_path), container_id,
#                  "{0}:{1}".format(major, minor),
#                  limit_write], stderr=subprocess.PIPE)
#             out, err = set_disk_bandwidth.communicate()
#             if set_disk_bandwidth.returncode == 0:
#                 pass
#             else:
#                 return False, {"error": "exit code of set_disk_bandwidth was: {0} with error message: {1}".format(str(
#                     set_disk_bandwidth.returncode), str(err))}
#         except subprocess.CalledProcessError as e:
#             return False, {"error": str(e)}

#     # blkio_path = "/".join([CGROUP_PATH, "blkio", "lxc", container_id])
#     # if DISK_READ_LIMIT_LABEL in disk_resource:
#     #     limit_read = disk_resource[DISK_READ_LIMIT_LABEL]
#     #     devices_read_limit_path = blkio_path + "/blkio.throttle.read_bps_device"
#     #
#     #     op = write_cgroup_file_value(devices_read_limit_path, str(major + ":" + minor + " " + limit_read))
#     #     if not op["success"]:
#     #         # Something happened
#     #         return False, op
#     #
#     # if DISK_WRITE_LIMIT_LABEL in disk_resource:
#     #     limit_write = disk_resource[DISK_WRITE_LIMIT_LABEL]
#     #     devices_write_limit_path = blkio_path + "/blkio.throttle.write_bps_device"
#     #
#     #     op = write_cgroup_file_value(devices_write_limit_path, str(major + ":" + minor + " " + limit_write))
#     #     if not op["success"]:
#     #         # Something happened
#     #         return False, op

#     # Nothing bad happened
#     return True, disk_resource


def get_device_major_minor(device_path):
    # Try next for partitions or devices
    major_minor = get_device_major_minor_raw_device(device_path)
    if major_minor and major_minor != ("0", "0"):
        # TODO FIX this or find a solution, partitions can't be limited, only devices
        if device_path.startswith("/dev/sd"):
            device_path = device_path[0:8]
            major_minor = get_device_major_minor_raw_device(device_path)
            if major_minor and major_minor != ("0", "0"):
                return major_minor[0], major_minor[1]

    # Try first for volume devices
    major_minor = get_device_major_minor_from_volumes(device_path)
    if major_minor:
        return major_minor[0], major_minor[1]

    return None


def get_node_disks(container_id, device, device_mountpoint, container_engine):
    retrieved_disks = list()
    limits_read, limits_write = get_node_disk_limits(container_id, container_engine)

    try:
        major, minor = get_device_major_minor(device)
    except TypeError:
        # None was returned
        return False, retrieved_disks

    major_minor_str = major + ":" + minor

    if major_minor_str in limits_read:
        # Convert the limits to Mbits/s
        device_read_limit = int(limits_read[major_minor_str])
        device_read_limit = int(device_read_limit / 1048576)
    else:
        device_read_limit = -1

    if major_minor_str in limits_write:
        # Convert the limits to Mbits/s
        device_write_limit = int(limits_write[major_minor_str])
        device_write_limit = int(device_write_limit / 1048576)
    else:
        device_write_limit = -1

    disk_dict = {
        "mountpoint": device_mountpoint,
        "device_path": device,
        "major": major,
        "minor": minor,
        "unit": "Mbit",
        DISK_READ_LIMIT_LABEL: device_read_limit,
        DISK_WRITE_LIMIT_LABEL: device_write_limit
    }

    retrieved_disks.append(disk_dict)

    return True, retrieved_disks

# def get_node_disks(container_id, devices):
#     SKIP_DISKS = ["bdev", "development", "production", "root"]
#     retrieved_disks = list()
#     limits_read, limits_write = get_node_disk_limits(container_id)
#     for device in devices.keys():
#         # TODO FIX, ignored devices should be obtained from a file
#         if device in SKIP_DISKS:
#             continue
#         device_mountpoint = devices[device]["source"]
#         device_path = get_device_path_from_mounted_filesystem(device_mountpoint)

#         if not device_path:
#             print("Disk {0} not found for container {1}".format(device, container_id))
#             continue

#         try:
#             major, minor = get_device_major_minor(device_path)
#         except TypeError:
#             # None was returned
#             continue

#         major_minor_str = major + ":" + minor

#         if major_minor_str in limits_read:
#             # Convert the limits to Mbits/s
#             device_read_limit = int(limits_read[major_minor_str])
#             device_read_limit = int(device_read_limit / 1048576)
#         else:
#             device_read_limit = -1

#         if major_minor_str in limits_write:
#             # Convert the limits to Mbits/s
#             device_write_limit = int(limits_write[major_minor_str])
#             device_write_limit = int(device_write_limit / 1048576)
#         else:
#             device_write_limit = -1

#         disk_dict = dict()
#         disk_dict["mountpoint"] = device_mountpoint
#         disk_dict["device_path"] = device_path
#         disk_dict["major"] = major
#         disk_dict["minor"] = minor
#         disk_dict["unit"] = "Mbit"
#         disk_dict[DISK_READ_LIMIT_LABEL] = device_read_limit
#         disk_dict[DISK_WRITE_LIMIT_LABEL] = device_write_limit

#         retrieved_disks.append(disk_dict)

#     return True, retrieved_disks


# NET #
NET_UNIT_NAME_LABEL = "unit"
NET_DEVICE_HOST_NAME_LABEL = "device_name_in_host"
NET_DEVICE_NAME_LABEL = "device_name_in_container"
NET_LIMIT_LABEL = "net_limit"


def get_interface_limit(interface_name):
    tc = subprocess.Popen(["tc", "-d", "qdisc", "show", "dev", interface_name], stdout=subprocess.PIPE)
    # TODO make sure to add the decode line everywhere necessary (where communicate is used)
    lines = tc.communicate()[0].decode('utf-8').strip().split(",")
    parts = list()
    for line in lines:
        parts = line.rstrip("\n").split()  # Just 1 line should be available
        break
    if len(parts) > 6:
        if parts[7].endswith("Mbit"):
            return int(parts[7].strip("Mbit"))
        elif parts[7].endswith("Kbit"):
            return int(parts[7].strip("Kbit")) / 1024

    else:
        return -1


def unset_interface_limit(interface_name):
    try:
        tc = subprocess.Popen(["tc", "qdisc", "del", "dev", interface_name, "root"], stderr=subprocess.PIPE)
        tc.wait()
        if tc.returncode == 0:
            return True
        else:
            return False, {"error": "exit code of tc was: {0}".format(str(tc.returncode))}
    except subprocess.CalledProcessError as e:
        return False, {"error": "error trying to execute command: {0}".format(str(e))}


# tc qdisc add dev veth6UQ01E root tbf rate 100Mbit burst 1000kb latency 100ms
def set_interface_limit(interface_name, net):
    try:
        net_limit = str(net[NET_LIMIT_LABEL]) + "Mbit"
        tc = subprocess.Popen(
            ["tc", "qdisc", "add", "dev", interface_name, "root", "tbf", "rate", net_limit, "burst",
             "1000kb", "latency", "100ms"], stderr=subprocess.PIPE)
        # tc.wait()
        out, err = tc.communicate()
        if tc.returncode == 0:
            return True, net
        else:
            return False, {"error": "exit code of tc was: {0} with error: {1}".format(str(tc.returncode), str(err))}
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
