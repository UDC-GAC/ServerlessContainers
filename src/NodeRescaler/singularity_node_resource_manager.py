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

## CGROUPS V1
# Getters
from src.NodeRescaler.node_resource_manager import get_node_cpus
from src.NodeRescaler.node_resource_manager import get_node_mem
from src.NodeRescaler.node_resource_manager import get_node_disks
from src.NodeRescaler.node_resource_manager import get_node_networks as cgroups_get_node_networks
# Setters
from src.NodeRescaler.node_resource_manager import set_node_cpus
from src.NodeRescaler.node_resource_manager import set_node_mem
from src.NodeRescaler.node_resource_manager import set_node_disk
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
DICT_DISK_LABEL = "disk"
DICT_NET_LABEL = "net"

# TODO: get container mount point from vars file
container_mount_point = "/opt/bind"

# At the moment, apptainer instances with cgroups V1 can only be started with root/sudo
# TODO properly support Net for cgroups v1 and add support for cgroups v2

class SingularityContainerManager:

    def __init__(self, singularity_command_alias, cgroups_version):
        self.userid = os.getuid()
        self.container_engine = "apptainer"
        self.singularity_command_alias = singularity_command_alias
        self.cgroups_version = cgroups_version

    def __get_singularity_instances(self):
        if self.cgroups_version == "v1":
            process = subprocess.Popen(["sudo", self.singularity_command_alias, "instance", "list", "-j"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            #process = subprocess.Popen([self.singularity_command_alias, "instance", "list", "-j"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            process = subprocess.Popen(["sudo", self.singularity_command_alias, "instance", "list", "-j"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        stdout, stderr = process.communicate()
        parsed = json.loads(stdout)

        return parsed['instances']

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

    def set_node_resources(self, node_name, resources):
        if resources is None:
            # No resources to set
            return False, {}
        else:
            try:
                container = self.__get_singularity_instance_by_name(node_name)
                node_pid = container['pid']

                node_dict = dict()
                (cpu_success, mem_success, disk_success, net_success) = (True, True, True, True)
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

                if DICT_DISK_LABEL in resources:

                    # TODO: maybe pass disk path as parameter from an HTTP request instead of getting it here
                    command = 'sudo {0} exec instance://{1} bash -c "findmnt -T {2}"'.format(self.singularity_command_alias, container['instance'], container_mount_point)
                    output,error  = subprocess.Popen(
                                        command, universal_newlines=True, shell=True,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
                    source = output.split()[5]
                    if ":" in source:
                        ## Device mounted on NFS
                        device = source.split(":")[0]
                    else:
                        device = source.split("[")[0]

                    if self.cgroups_version == "v1":
                        disk_success, disk_resource = set_node_disk(node_pid, resources[DICT_DISK_LABEL], device, self.container_engine)
                    else:
                        disk_success, disk_resource = set_node_disk_cgroupsv2(self.userid, node_pid, resources[DICT_DISK_LABEL], device, self.container_engine)

                    node_dict[DICT_DISK_LABEL] = disk_resource
                    # disks_changed = list()
                    # for disk in resources[DICT_DISK_LABEL]:
                    #     disk_success, disk_resource = set_node_disk(node_name, disk)
                    #     disks_changed.append(disk_resource)
                    #     node_dict[DICT_DISK_LABEL] = disks_changed

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

                global_success = cpu_success and mem_success and disk_success and net_success
                return global_success, node_dict

            except AttributeError:
                # If node not found, pass
                return False, {}

    def get_node_resources_by_name(self, container_name):
        container = self.__get_singularity_instance_by_name(container_name)
        return self.get_node_resources(container)

    def get_node_resources(self, container):
        try:
            node_pid = container['pid']

            node_dict = dict()

            if self.cgroups_version == "v1":
                cpu_success, cpu_resources = get_node_cpus(node_pid, self.container_engine)
                mem_success, mem_resources = get_node_mem(node_pid, self.container_engine)
            else:
                cpu_success, cpu_resources = get_node_cpus_cgroupsv2(self.userid, node_pid, self.container_engine)
                mem_success, mem_resources = get_node_mem_cgroupsv2(self.userid, node_pid, self.container_engine)

            node_dict[DICT_CPU_LABEL] = cpu_resources
            node_dict[DICT_MEM_LABEL] = mem_resources

            command = 'sudo {0} exec instance://{1} bash -c "findmnt -T {2}"'.format(self.singularity_command_alias, container['instance'], container_mount_point)
            try:
                output = subprocess.run(
                                command, universal_newlines=True, shell=True, capture_output=True, timeout=1).stdout
                source = output.split()[5]
                if ":" in source:
                    ## Device mounted on NFS
                    #device, mount_point = source.split(":")
                    ## Cant' access disk information of a remote disk
                    disk_resources = None
                else:
                    device = source.split("[")[0]
                    mount_point= re.findall(r'\[([^]]*)\]', source)[0]
                    if self.cgroups_version == "v1":
                        disk_success, disk_resources = get_node_disks(node_pid, device, mount_point, self.container_engine)
                        # disk_success, disk_resources = self.get_node_disks(container)  # LXD Dependent
                    else:
                        disk_success, disk_resources = cgroups_get_node_disks_cgroupsv2(self.userid, node_pid, device, mount_point, self.container_engine)

                if type(disk_resources) == list and len(disk_resources) > 0:
                    node_dict[DICT_DISK_LABEL] = disk_resources[0]
                elif disk_resources:
                    node_dict[DICT_DISK_LABEL] = disk_resources
                else:
                    node_dict[DICT_DISK_LABEL] = []

            except (subprocess.TimeoutExpired, PermissionError):
                #print("Timeout")
                pass
            except IndexError:
                # If there are not subscribed containers that don't have a mount point on /opt/bind
                # Subprocess will return an empty string and output.split()[5] will raise an IndexError
                print("Container {0} not subscribed".format(container['instance']))

            # TODO support multiple disks
            #
            # net_success, net_resources = self.get_node_networks(container)  # LXD Dependent
            # if net_resources:
            #     node_dict[DICT_NET_LABEL] = net_resources[0]
            # else:
            #     node_dict[DICT_NET_LABEL] = []
            # # TODO support multiple networks

            return node_dict

        except AttributeError:
            # If node not found, pass
            pass

    def get_all_nodes(self):
        containers = self.__get_singularity_instances()
        containers_dict = dict()

        for c in containers:
            containers_dict[c['instance']] = self.get_node_resources(c)
        return containers_dict
