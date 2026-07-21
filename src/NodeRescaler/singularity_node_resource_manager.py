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

import urllib3
#from spython.main import Client
import subprocess
import json
import re
import fnmatch
import glob
from datetime import datetime, timedelta

## CGROUPS V1
# Getters
from src.NodeRescaler.node_resource_manager import get_node_cpus
from src.NodeRescaler.node_resource_manager import get_node_mem
from src.NodeRescaler.node_resource_manager import get_node_disks
from src.NodeRescaler.node_resource_manager import get_node_energy
from src.NodeRescaler.node_resource_manager import get_node_networks as cgroups_get_node_networks
# Setters
from src.NodeRescaler.node_resource_manager import set_node_cpus
from src.NodeRescaler.node_resource_manager import set_node_mem
from src.NodeRescaler.node_resource_manager import set_node_disk
from src.NodeRescaler.node_resource_manager import set_node_energy
from src.NodeRescaler.node_resource_manager import set_node_net

## CGROUPS V2
# Getters
from src.NodeRescaler.node_resource_manager_cgroupsv2 import get_node_cpus as get_node_cpus_cgroupsv2
from src.NodeRescaler.node_resource_manager_cgroupsv2 import get_node_mem as get_node_mem_cgroupsv2
from src.NodeRescaler.node_resource_manager_cgroupsv2 import get_node_disks as cgroups_get_node_disks_cgroupsv2
#from src.NodeRescaler.node_resource_manager_cgroupsv2 import get_node_networks as cgroups_get_node_networks_cgroupsv2
# Setters
from src.NodeRescaler.node_resource_manager_cgroupsv2 import set_node_cpus as set_node_cpus_cgroupsv2
from src.NodeRescaler.node_resource_manager_cgroupsv2 import set_node_mem as set_node_mem_cgroupsv2
from src.NodeRescaler.node_resource_manager_cgroupsv2 import set_node_disk as set_node_disk_cgroupsv2
#from src.NodeRescaler.node_resource_manager_cgroupsv2 import set_node_net as set_node_net_cgroupsv2

urllib3.disable_warnings()

DICT_CPU_LABEL = "cpu"
DICT_MEM_LABEL = "mem"
DICT_DISK_READ_LABEL = "disk_read"
DICT_DISK_WRITE_LABEL = "disk_write"
DICT_ENERGY_LABEL = "energy"
DICT_NET_LABEL = "net"

# TODO: get container mount point from vars file
CONTAINER_MOUNT_POINT = "/opt/bind"

INVALID_DISK_TYPES = [
    "tmpfs", "nfs", "nfs4", "cifs", "smbfs", "glusterfs", "ceph", "cephfs",
    "gfs2", "lustre", "gpfs", "ocfs2", "afs", "sshfs",
]

# At the moment, apptainer instances with cgroups V1 can only be started with root/sudo
# TODO properly support Net for cgroups v1 and add support for cgroups v2

class SingularityContainerManager:

    def __init__(self, singularity_command_alias, cgroups_version, energy_vcgroup_dir):
        self.userid = os.getuid()
        self.container_engine = "apptainer"
        self.singularity_command_alias = singularity_command_alias
        self.cgroups_version = cgroups_version
        self.energy_vcgroup_dir = energy_vcgroup_dir

    def __get_singularity_instances(self, containers_to_ignore=[]):
        if self.cgroups_version == "v1":
            process = subprocess.Popen(["sudo", self.singularity_command_alias, "instance", "list", "-j"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            #process = subprocess.Popen([self.singularity_command_alias, "instance", "list", "-j"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            process = subprocess.Popen(["sudo", self.singularity_command_alias, "instance", "list", "-j"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        stdout, stderr = process.communicate()
        instances = json.loads(stdout)['instances']

        filtered_instances = [
            item for item in instances
            if not any(fnmatch.fnmatch(item['instance'], pattern) for pattern in containers_to_ignore)
        ]

        return filtered_instances

    def __get_singularity_instance_by_name(self, instance_name):
        if self.cgroups_version == "v1":
            process = subprocess.Popen(["sudo", self.singularity_command_alias, "instance", "list", "-j", instance_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            #process = subprocess.Popen([self.singularity_command_alias, "instance", "list", "-j", instance_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            process = subprocess.Popen(["sudo", self.singularity_command_alias, "instance", "list", "-j", instance_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        stdout, stderr = process.communicate()
        parsed = json.loads(stdout)

        try:
            instance = parsed['instances'][0]
            return instance
        except IndexError:
            # If node not found, pass
            return {}

    def __get_disk_device(self, instance_name):
        device, mount_point, fstype = None, None, None
        command = 'sudo {0} exec instance://{1} bash -c "findmnt -nrT {2}"'.format(self.singularity_command_alias, instance_name, CONTAINER_MOUNT_POINT)

        try:
            output = subprocess.run(command, universal_newlines=True, shell=True, capture_output=True, timeout=3).stdout.split()
            source = output[1]
            fstype = output[2]

            if fstype not in INVALID_DISK_TYPES:
                device = source.split("[")[0]
                mount_point = re.findall(r'\[([^]]*)\]', source)[0]

        except (subprocess.TimeoutExpired, PermissionError):
            #print("Timeout")
            pass
        except IndexError:
            # If there are not subscribed containers that don't have a mount point on /opt/bind
            # Subprocess will return an empty string and output[1] will raise an IndexError
            print("Container {0} not subscribed".format(instance_name))

        return device, mount_point, fstype

    def set_node_resources(self, node_name, resources):
        if resources is None:
            # No resources to set
            return False, {}
        else:
            try:

                container = self.__get_singularity_instance_by_name(node_name)
                node_pid = container['pid']

                node_dict = dict()
                (cpu_success, mem_success, disk_read_success, disk_write_success, energy_success, net_success) = (True, True, True, True, True, True)
                if DICT_CPU_LABEL in resources:
                    if self.cgroups_version == "v1":
                        cpu_success, cpu_resources = set_node_cpus(node_pid, resources[DICT_CPU_LABEL], self.container_engine)
                    else:
                        cpu_success, cpu_resources = set_node_cpus_cgroupsv2(self.userid, node_pid, resources[DICT_CPU_LABEL], self.container_engine)

                    node_dict[DICT_CPU_LABEL] = cpu_resources

                if DICT_MEM_LABEL in resources:
                    if self.cgroups_version == "v1":
                        mem_success, mem_resources = set_node_mem(node_pid, resources[DICT_MEM_LABEL], self.container_engine)
                    else:
                        mem_success, mem_resources = set_node_mem_cgroupsv2(self.userid, node_pid, resources[DICT_MEM_LABEL], self.container_engine)

                    node_dict[DICT_MEM_LABEL] = mem_resources

                if DICT_DISK_READ_LABEL in resources or DICT_DISK_WRITE_LABEL in resources:

                    # TODO: maybe pass disk path as parameter from an HTTP request instead of getting it here
                    device, _, fstype = self.__get_disk_device(container['instance'])
                    if not device:
                        if DICT_DISK_READ_LABEL in resources:
                            disk_read_success = False
                            node_dict[DICT_DISK_READ_LABEL] = {"error": "Requested device is not valid, fstype={0}".format(fstype)}
                        if DICT_DISK_WRITE_LABEL in resources:
                            disk_write_success = False
                            node_dict[DICT_DISK_WRITE_LABEL] = {"error": "Requested device is not valid, fstype={0}".format(fstype)}
                    else:
                        if DICT_DISK_READ_LABEL in resources:
                            if self.cgroups_version == "v1":
                                disk_read_success, disk_read_resource = set_node_disk(node_pid, resources[DICT_DISK_READ_LABEL], device, self.container_engine)
                            else:
                                disk_read_success, disk_read_resource = set_node_disk_cgroupsv2(self.userid, node_pid, resources[DICT_DISK_READ_LABEL], device, self.container_engine)
                            node_dict[DICT_DISK_READ_LABEL] = disk_read_resource

                        if DICT_DISK_WRITE_LABEL in resources:
                            if self.cgroups_version == "v1":
                                disk_write_success, disk_write_resource = set_node_disk(node_pid, resources[DICT_DISK_WRITE_LABEL], device, self.container_engine)
                            else:
                                disk_write_success, disk_write_resource = set_node_disk_cgroupsv2(self.userid, node_pid, resources[DICT_DISK_WRITE_LABEL], device, self.container_engine)
                            node_dict[DICT_DISK_WRITE_LABEL] = disk_write_resource

                    # disks_changed = list()
                    # for disk in resources[DICT_DISK_LABEL]:
                    #     disk_success, disk_resource = set_node_disk(node_name, disk)
                    #     disks_changed.append(disk_resource)
                    #     node_dict[DICT_DISK_LABEL] = disks_changed
                if DICT_ENERGY_LABEL in resources:
                    energy_success, energy_resource = set_node_energy(node_pid, resources[DICT_ENERGY_LABEL], self.energy_vcgroup_dir)
                    node_dict[DICT_ENERGY_LABEL] = energy_resource

                if DICT_NET_LABEL in resources:
                    if self.cgroups_version == "v1":
                        net_success, net_resource = set_node_net(resources[DICT_NET_LABEL])
                    else:
                        #net_success, net_resource = set_node_net_cgroupsv2(resources[DICT_NET_LABEL])
                        pass
                    node_dict[DICT_NET_LABEL] = net_resource

                    # networks_changed = list()
                    # for net in resources[DICT_NET_LABEL]:
                    #     net_success, net_resource = set_node_net(net)
                    #     networks_changed.append(net_resource)
                    #     node_dict[DICT_NET_LABEL] = networks_changed

                global_success = cpu_success and mem_success and disk_read_success and disk_write_success and energy_success and net_success
                return global_success, node_dict

            except AttributeError:
                # If node not found, pass
                return False, {}

    def get_node_resources(self, container, needed_resources=None):
        if needed_resources is None:
            needed_resources = {"cpu": True, "mem": True, "disk": True, "energy": True, "net": True}
        try:
            node_pid = container['pid']
            node_dict = {}

            # CPU
            if needed_resources.get("cpu", False):
                if self.cgroups_version == "v1":
                    cpu_success, cpu_resources = get_node_cpus(node_pid, self.container_engine)
                else:
                    cpu_success, cpu_resources = get_node_cpus_cgroupsv2(self.userid, node_pid, self.container_engine)
                node_dict[DICT_CPU_LABEL] = cpu_resources

            # Memory
            if needed_resources.get("mem", False):
                if self.cgroups_version == "v1":
                    mem_success, mem_resources = get_node_mem(node_pid, self.container_engine)
                else:
                    mem_success, mem_resources = get_node_mem_cgroupsv2(self.userid, node_pid, self.container_engine)
                node_dict[DICT_MEM_LABEL] = mem_resources

            # Disk
            if needed_resources.get("disk", False) or needed_resources.get("disk_read", False) or needed_resources.get("disk_write", False):
                device, mount_point, _ = self.__get_disk_device(container['instance'])
                if not device or not mount_point:
                    disk_resources = None
                else:
                    if self.cgroups_version == "v1":
                        disk_success, disk_resources = get_node_disks(node_pid, device, mount_point, self.container_engine)
                        # disk_success, disk_resources = self.get_node_disks(container)  # LXD Dependent
                    else:
                        disk_success, disk_resources = cgroups_get_node_disks_cgroupsv2(self.userid, node_pid, device, mount_point, self.container_engine)

                if type(disk_resources) == list and len(disk_resources) > 0:
                    node_dict[DICT_DISK_READ_LABEL] = disk_resources[0][DICT_DISK_READ_LABEL]
                    node_dict[DICT_DISK_WRITE_LABEL] = disk_resources[0][DICT_DISK_WRITE_LABEL]
                elif disk_resources:
                    node_dict[DICT_DISK_READ_LABEL] = disk_resources[DICT_DISK_READ_LABEL]
                    node_dict[DICT_DISK_WRITE_LABEL] = disk_resources[DICT_DISK_WRITE_LABEL]
                else:
                    node_dict[DICT_DISK_READ_LABEL] = {}
                    node_dict[DICT_DISK_WRITE_LABEL] = {}
                # TODO support multiple disks
                #
            if needed_resources.get("energy", False):
                energy_success, energy_resources = get_node_energy(node_pid, self.energy_vcgroup_dir)
                node_dict[DICT_ENERGY_LABEL] = energy_resources

            # if needed_resources.get("net", False):
            #   net_success, net_resources = self.get_node_networks(container)  # LXD Dependent
            #   if net_resources:
            #       node_dict[DICT_NET_LABEL] = net_resources[0]
            #   else:
            #       node_dict[DICT_NET_LABEL] = []
            # # TODO support multiple networks

            return node_dict

        except AttributeError:
            # If node not found, pass
            pass

    def get_node_resources_by_name(self, container_name, needed_resources=None):
        container = self.__get_singularity_instance_by_name(container_name)
        if container:
            return self.get_node_resources(container, needed_resources)
        return None

    def get_all_nodes(self, needed_resources=None, containers_to_ignore=[]):
        containers = self.__get_singularity_instances(containers_to_ignore)
        containers_dict = dict()
        for c in containers:
            containers_dict[c['instance']] = self.get_node_resources(c, needed_resources)
        return containers_dict

    def get_node_tcp_connections(self, containers_to_ignore=[]):

        window_delay = 15

        # 1: get container - PID mapping
        containers = self.__get_singularity_instances(containers_to_ignore)
        container_ip_mapped = {d["ip"]: d["instance"] for d in containers}

        # 2: get TCP lines
        tcp_logs_folder = os.environ["TCP_TRACKER_LOG_PATH"]
        list_of_files = glob.glob(f'{tcp_logs_folder}/*.log')
        latest_file = max(list_of_files, key=os.path.getctime)

        lines = self.__get_last_log_lines(latest_file, window_delay)

        # 3: match lines with container info
        result = {}
        for line in lines:
            parts = line.split(" ")
            source_address = parts[-3] ## get indexes backwards to avoid problems when the process name (2nd column) has spaces in between
            dest_address = parts[-2]
            port = parts[-1]
            if int(port) == 9866 and source_address in container_ip_mapped and dest_address in container_ip_mapped:
                source_container = container_ip_mapped[source_address]
                dest_container = container_ip_mapped[dest_address]
                if source_container not in result:
                    result[source_container] = []
                if dest_container not in result[source_container]:
                    result[source_container].append(dest_container)

        return result

    def __get_last_log_lines(self, file_path, window_timelapse):
        """
        Returns a list of lines whose relative timestamp (in seconds)
        is within the last <window_timelapse> seconds relative to the system clock.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if not lines:
            return []

        # 1) Extract the start date from the first line
        # Format: "Starting log at DD-MM-YY HH:MM:SS"
        m = re.match(r"Starting TCPConnect at (\d{2}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", lines[0].strip())
        if not m:
            raise ValueError(f"The first line is not formatted as expected: {lines[0].strip()}.")

        initial_date = datetime.strptime(m.group(1), "%d-%m-%y %H:%M:%S")
        initial_date = initial_date + timedelta(seconds=5) ## add the 5 seconds waited before running first curl

        # 2) Current system time
        current_date = datetime.now()
        t_ini = current_date - timedelta(seconds=window_timelapse)

        result = []
        # 3) Process lines with relative timestamps in seconds
        for line in lines[1:]:
            line = line.strip()
            line = re.sub(' +', ' ', line) ## remove intermediate extra whitespaces
            if not line:
                continue

            # Extract the timestamp corresponding to the start of the line (e.g., "12.345")
            m_ts = re.match(r"([0-9]+(?:\.[0-9]+)?)", line)
            if not m_ts:
                continue

            relative_seconds = float(m_ts.group(1))
            line_timestamp = initial_date + timedelta(seconds=relative_seconds)

            if t_ini <= line_timestamp <= current_date:
                result.append(line)

        return result