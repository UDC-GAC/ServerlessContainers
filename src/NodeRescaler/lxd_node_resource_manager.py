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

import urllib3
import pylxd
from pylxd import Client
from pylxd.exceptions import NotFound

# Getters
from src.NodeRescaler.node_resource_manager import get_node_cpus
from src.NodeRescaler.node_resource_manager import get_node_mem
from src.NodeRescaler.node_resource_manager import get_node_disks as cgroups_get_node_disks
from src.NodeRescaler.node_resource_manager import get_node_energy
from src.NodeRescaler.node_resource_manager import get_node_networks as cgroups_get_node_networks
# Setters
from src.NodeRescaler.node_resource_manager import set_node_cpus
from src.NodeRescaler.node_resource_manager import set_node_mem
from src.NodeRescaler.node_resource_manager import set_node_disk
from src.NodeRescaler.node_resource_manager import set_node_energy
from src.NodeRescaler.node_resource_manager import set_node_net


urllib3.disable_warnings()

DICT_CPU_LABEL = "cpu"
DICT_MEM_LABEL = "mem"
DICT_DISK_LABEL = "disk"
DICT_ENERGY_LABEL = "energy"
DICT_NET_LABEL = "net"


class LXDContainerManager:

    def read_keys(self):
        # TODO Improve key handling
        self.LXD_CRT = '/${LXD_KEY_PATH}/${LXD_KEY_NAME}.crt'
        self.LXD_KEY = '/${LXD_KEY_PATH}/${LXD_KEY_NAME}.key'
        self.LXD_ENDPOINT = 'https://localhost:8443'

    def __init__(self, cgroups_version, energy_vcgroup_dir):
        # TODO add support for lxc with cgroups v2
        self.container_engine = "lxc"
        self.cgroups_version = cgroups_version
        self.energy_vcgroup_dir = energy_vcgroup_dir
        self.read_keys()
        # TODO Deal with error if key does not exist
        self.client = Client(
            endpoint=os.path.expandvars(self.LXD_ENDPOINT),
            cert=(os.path.expandvars(self.LXD_CRT),
                  os.path.expandvars(self.LXD_KEY)),
            verify=False)

    def get_node_disks(self, container):
        devices = container.devices
        if not devices:
            return True, []
        else:
            return cgroups_get_node_disks(container.name, devices)

    def get_node_networks(self, container):
        networks = container.state().network
        if not networks:
            return True, []
        else:
            network_host_interfaces = list()
            for net in networks.keys():
                if net == "lo":
                    continue  # Skip the internal loopback interface
                network_host_interfaces.append(
                    {"container_interface": net, "host_interface": networks[net]["host_name"]})

            return cgroups_get_node_networks(network_host_interfaces)

    def set_node_resources(self, node_name, resources):
        if resources is None:
            # No resources to set
            return False, {}
        else:
            try:
                container = self.client.containers.get(node_name)
                if container.status == "Running":
                    node_dict = dict()
                    (cpu_success, mem_success, disk_success, net_success) = (True, True, True, True)
                    if DICT_CPU_LABEL in resources:
                        cpu_success, cpu_resources = set_node_cpus(node_name, resources[DICT_CPU_LABEL], self.container_engine)
                        node_dict[DICT_CPU_LABEL] = cpu_resources

                    if DICT_MEM_LABEL in resources:
                        mem_success, mem_resources = set_node_mem(node_name, resources[DICT_MEM_LABEL], self.container_engine)
                        node_dict[DICT_MEM_LABEL] = mem_resources

                    if DICT_DISK_LABEL in resources:
                        disk_success, disk_resource = set_node_disk(node_name, resources[DICT_DISK_LABEL], self.container_engine)
                        node_dict[DICT_DISK_LABEL] = disk_resource
                        # disks_changed = list()
                        # for disk in resources[DICT_DISK_LABEL]:
                        #     disk_success, disk_resource = set_node_disk(node_name, disk)
                        #     disks_changed.append(disk_resource)
                        #     node_dict[DICT_DISK_LABEL] = disks_changed
                    if DICT_ENERGY_LABEL in resources:
                        energy_success, energy_resource = set_node_energy(node_name, resources[DICT_ENERGY_LABEL], self.energy_vcgroup_dir)
                        node_dict[DICT_ENERGY_LABEL] = energy_resource

                    if DICT_NET_LABEL in resources:
                        net_success, net_resource = set_node_net(resources[DICT_NET_LABEL])
                        node_dict[DICT_NET_LABEL] = net_resource

                        # networks_changed = list()
                        # for net in resources[DICT_NET_LABEL]:
                        #     net_success, net_resource = set_node_net(net)
                        #     networks_changed.append(net_resource)
                        #     node_dict[DICT_NET_LABEL] = networks_changed

                    global_success = cpu_success and mem_success and disk_success and net_success
                    return global_success, node_dict
                else:
                    # If container not running, skip
                    return False, {}
            except pylxd.exceptions.NotFound:
                # If node not found, pass
                return False, {}

    def get_node_resources_by_name(self, container_name):
        container = self.client.containers.get(container_name)
        return self.get_node_resources(container)

    def get_node_resources(self, container):
        try:
            node_name = container.name
            if container.status == "Running":
                node_dict = dict()

                cpu_success, cpu_resources = get_node_cpus(node_name, self.container_engine)
                node_dict[DICT_CPU_LABEL] = cpu_resources

                mem_success, mem_resources = get_node_mem(node_name, self.container_engine)
                node_dict[DICT_MEM_LABEL] = mem_resources

                energy_success, energy_resources = get_node_energy(node_name, self.energy_vcgroup_dir)
                node_dict[DICT_ENERGY_LABEL] = energy_resources

                # disk_success, disk_resources = self.get_node_disks(container)  # LXD Dependent
                # if type(disk_resources) == list and len(disk_resources) > 0:
                #     node_dict[DICT_DISK_LABEL] = disk_resources[0]
                # elif disk_resources:
                #     node_dict[DICT_DISK_LABEL] = disk_resources
                # else:
                #     node_dict[DICT_DISK_LABEL] = []
                # # TODO support multiple disks
                #
                # net_success, net_resources = self.get_node_networks(container)  # LXD Dependent
                # if net_resources:
                #     node_dict[DICT_NET_LABEL] = net_resources[0]
                # else:
                #     node_dict[DICT_NET_LABEL] = []
                # # TODO support multiple networks

                return node_dict
            else:
                # If container not running, skip
                pass
        except pylxd.exceptions.NotFound:
            # If node not found, pass
            pass

    def get_all_nodes(self):
        containers = self.client.containers.all()
        containers_dict = dict()
        # client.authenticate('bogus')
        for c in containers:
            if c.status == "Running":
                containers_dict[c.name] = self.get_node_resources(c)
        return containers_dict
