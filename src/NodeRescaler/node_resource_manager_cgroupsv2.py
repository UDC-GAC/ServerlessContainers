#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 Universidade da Coruña
# Authors:
#     - Óscar Castellanos-Rodríguez [main] (oscar.castellanos@udc.es)
#     - Jonatan Enes
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

# TODO add support for lxc with cgroups v2
# TODO add support for Net

def get_cgroup_file_path(userid, container_id, cgroup_parameter, container_engine):
    if container_engine == "apptainer":
        container_pid = container_id

        ## Without sudo
        #cgroup_file_path = "/".join([CGROUP_PATH, "user.slice", "user-{0}.slice".format(userid), "user@{0}.service".format(userid), "user.slice", "apptainer-{0}.scope".format(container_pid), cgroup_parameter])

        ## With sudo (currently needed because 'network' parameter in apptainer required root permissions)
        cgroup_file_path = "/".join([CGROUP_PATH, "system.slice", "apptainer-{0}.scope".format(container_pid), cgroup_parameter])

        return cgroup_file_path

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


def get_node_cpus(userid, container_id, container_engine):
    # Get info from cgroups cpuacct subsystem
    cpu_accounting_path = get_cgroup_file_path(userid, container_id, "cpu.max", container_engine)
    op = read_cgroup_file_value(cpu_accounting_path)
    if op["success"]:
        cpu_limit = op["data"].split(" ")[0]
        if cpu_limit != "max":
            # A limit is set, else leave it untouchedset_node_mem
            cpu_limit = int(op["data"].split(" ")[0]) / TICKS_PER_CPU_PERCENTAGE
        else:
            cpu_limit = -1
    else:
        return False, op

    # Get info from cgroups cpuset subsystem
    cpus_path = get_cgroup_file_path(userid, container_id, "cpuset.cpus", container_engine)
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


def set_node_cpus(userid, container_id, cpu_resource, container_engine):
    applied_changes = dict()

    if CPU_LIMIT_ALLOWANCE_LABEL in cpu_resource:
        cpu_accounting_path = get_cgroup_file_path(userid, container_id, "cpu.max", container_engine)

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

        # Write the quota for this container in ticks and number of ticks per second
        quota_str = quota
        if quota_str == -1:
            quota_str = "max"
        cpu_max_value = str(quota_str) + " " + str(MAX_TICKS_PER_CPU)
        op = write_cgroup_file_value(cpu_accounting_path, cpu_max_value)
        if not op["success"]:
            # Something happened
            return False, op

        # This change was applied successfully
        applied_changes[CPU_LIMIT_ALLOWANCE_LABEL] = str(quota / TICKS_PER_CPU_PERCENTAGE)

    if CPU_LIMIT_CPUS_LABEL in cpu_resource:
        # container.config["limits.cpu"] = cpu_resource[CPU_LIMIT_CPUS_LABEL]
        cpu_cpuset_path = get_cgroup_file_path(userid, container_id, "cpuset.cpus", container_engine)

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


def get_node_mem(userid, container_id, container_engine):
    final_dict = dict()
    memory_limit_path = get_cgroup_file_path(userid, container_id, "memory.max", container_engine)

    op = read_cgroup_file_value(memory_limit_path)
    if op["success"]:
        mem_limit = op["data"]
    else:
        return op

    if (mem_limit == "max"):
        mem_limit_converted = -1
        final_dict["unit"] = "unlimited"
    else:
        mem_limit_converted = int(mem_limit) / 1048576  # Convert to MB
        final_dict["unit"] = "M"

    final_dict[MEM_LIMIT_LABEL] = mem_limit_converted
    return True, final_dict


def set_node_mem(userid, container_id, mem_resource, container_engine):
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
        # swap_limit_path = "/".join([CGROUP_PATH, "memory", "lxc", container_name, "memory.memsw.limit_in_bytes"])
        memory_limit_path = get_cgroup_file_path(userid, container_id, "memory.max", container_engine)

        # Get the current memory limit in megabytes, that should be equal to the swap space
        success, current_mem_value = get_node_mem(userid, container_id, container_engine)
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


def get_node_disk_limits(userid, container_id, container_engine):
    devices_io_limit_path = get_cgroup_file_path(userid, container_id, "io.max", container_engine)

    devices_read_limits = dict()
    devices_write_limits = dict()

    if os.path.isfile(devices_io_limit_path) and os.access(devices_io_limit_path, os.R_OK):
        devices_io_limit_file = open(devices_io_limit_path, 'r')
        for line in devices_io_limit_file:
            parts = line.rstrip("\n").split()
            major_minor = parts[0]
            read_limit = parts[1].strip("rbps=")
            write_limit = parts[2].strip("wbps=")
            devices_read_limits[major_minor] = read_limit
            devices_write_limits[major_minor] = write_limit
        devices_io_limit_file.close()

    return devices_read_limits, devices_write_limits


def set_node_disk(userid, container_id, disk_resource, device, container_engine):

    try:
        major, minor = get_device_major_minor(device)
    except TypeError:
        # None was returned
        return False, {"error": "No major and minor found for device {0}".format(device)}

    for label, operation in [(DISK_READ_LIMIT_LABEL, 0), (DISK_WRITE_LIMIT_LABEL, 1)]:
        if label in disk_resource:
            io_limit = int(disk_resource[label]) * 1048576
            try:

                script_dir = os.path.dirname(os.path.realpath(__file__))
                set_bandwidth_script_path = "/".join([script_dir, "..", "..", "scripts", container_engine, "set_bandwidth_cgroupsv2.sh"])
                set_disk_bandwidth = subprocess.Popen(
                    ["/bin/bash", set_bandwidth_script_path, str(userid), str(container_id), "{0}:{1}".format(major, minor), operation, str(io_limit)],
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


def get_node_disks(userid, container_id, device, device_mountpoint, container_engine):
    retrieved_disks = list()
    limits_read, limits_write = get_node_disk_limits(userid, container_id, container_engine)

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

    disk_dict = dict()

    disk_dict["disk_read"] = dict()
    disk_dict["disk_read"]["mountpoint"] = device_mountpoint
    disk_dict["disk_read"]["device_path"] = device
    disk_dict["disk_read"]["major"] = major
    disk_dict["disk_read"]["minor"] = minor
    disk_dict["disk_read"]["unit"] = "Mbit"
    disk_dict["disk_read"][DISK_READ_LIMIT_LABEL] = device_read_limit

    disk_dict["disk_write"] = dict()
    disk_dict["disk_write"]["mountpoint"] = device_mountpoint
    disk_dict["disk_write"]["device_path"] = device
    disk_dict["disk_write"]["major"] = major
    disk_dict["disk_write"]["minor"] = minor
    disk_dict["disk_write"]["unit"] = "Mbit"
    disk_dict["disk_write"][DISK_WRITE_LIMIT_LABEL] = device_write_limit

    retrieved_disks.append(disk_dict)

    return True, retrieved_disks
