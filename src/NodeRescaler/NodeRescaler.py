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

import json

from flask import Flask
from flask import Response
from flask import abort
from flask import jsonify
from flask import request
from werkzeug.serving import WSGIRequestHandler

from src.NodeRescaler.lxd_node_resource_manager import LXDContainerManager
from src.NodeRescaler.singularity_node_resource_manager import SingularityContainerManager
from functools import wraps

import yaml
import os
import psutil

node_resource_manager = None

node_rescaler = Flask(__name__)

def initialize_ContainerEngine(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        serverless_path = os.environ['SERVERLESS_PATH']
        config_file = serverless_path + "/services_config.yml"
        with open(config_file, "r") as cf:
            config = yaml.load(cf, Loader=yaml.FullLoader)

        container_engine = config['CONTAINER_ENGINE']
        singularity_command_alias = config['SINGULARITY_COMMAND_ALIAS']
        cgroups_version = config['CGROUPS_VERSION']

        # Create directory to manage an energy virtual cgroup
        energy_vcgroup_dir = serverless_path + "/energy_vcgroup"
        os.makedirs(energy_vcgroup_dir, exist_ok=True, mode=0o700)

        if container_engine == "lxc":
            initialize_LXD(cgroups_version, energy_vcgroup_dir)
        elif container_engine == "apptainer":
            initialize_Singularity(singularity_command_alias, cgroups_version, energy_vcgroup_dir)
        else:
            raise Exception("Error: a non-valid container engine was specified")

        return f(*args, **kwargs)

    return wrap

def initialize_Singularity(singularity_command_alias, cgroups_version, energy_vcgroup_dir):

    global node_resource_manager
    if not node_resource_manager:
        node_resource_manager = SingularityContainerManager(singularity_command_alias, cgroups_version, energy_vcgroup_dir)
        if not node_resource_manager:
            raise Exception("Could not instantiate Singularity Manager")
    else:
        pass


def initialize_LXD(cgroups_version, energy_vcgroup_dir):

    global node_resource_manager
    if not node_resource_manager:
        node_resource_manager = LXDContainerManager(cgroups_version, energy_vcgroup_dir)
        if not node_resource_manager:
            raise Exception("Could not instantiate LXD Manager")
    else:
        pass


def __get_topology_from_psutil(core_numbering="first-physical"):
    logical_cores = psutil.cpu_count(logical=True)
    physical_cores = psutil.cpu_count(logical=False)
    multithreading = logical_cores > physical_cores
    # Workaround to get number of sockets using psutil
    num_sockets = len([sensor for sensor in psutil.sensors_temperatures()['coretemp']
                       if 'Package id' in sensor.label or 'Physical id' in sensor.label])
    cores_per_cpu = physical_cores // num_sockets

    # TODO: Guess core_numbering from SO, now first-physical is assumed
    #   Maybe read /sys/devices/system/cpu/cpu0/topology/core_siblings_list
    topology = {}
    for socket in range(num_sockets):
        topology[socket] = {}
        for c in range(cores_per_cpu * socket, cores_per_cpu * (socket + 1)):
            topology[socket][c] = [c]
            if multithreading:
                if core_numbering == "first-physical":
                    # First all physical cores are numbered, then all logical cores
                    topology[socket][c].append(c + cores_per_cpu * num_sockets)
                if core_numbering == "per-socket":
                    # All socket cores are numbered in a row (physical and logical)
                    topology[socket][c].append(c + cores_per_cpu)

    return topology


def __get_topology_from_procfs():
    # Parse /proc/cpuinfo to get CPU topology
    cpus, current_cpu = [], {}
    with open("/proc/cpuinfo") as f:
        for line in f:
            line = line.strip()
            # Get processor information
            if ":" in line:
                key, val = line.split(":", 1)
                if key.strip() in ["processor", "physical id", "core id"]:
                    current_cpu[key.strip()] = val.strip()

            # Empty line indicates end of a CPU entry
            if not line and current_cpu:
                cpus.append(current_cpu)
                current_cpu = {}
        if current_cpu:
            cpus.append(current_cpu)

    # Build mapping between sockets, physical cores and logical cores
    topology = {}
    for cpu in cpus:
        phys_id = int(cpu.get("physical id", 0))
        core_id = int(cpu.get("core id", 0))
        proc_id = int(cpu.get("processor", 0))
        topology.setdefault(phys_id, {}).setdefault(core_id, []).append(proc_id)
        # Sort threads by number
        if len(topology[phys_id][core_id]) > 1:
            topology[phys_id][core_id].sort()

    return topology


def __get_needed_resources(_request):
    needed_resources = {"cpu": False, "mem": False, "disk": False, "energy": False, "net": False}
    for resource in needed_resources.keys():
        if resource in _request.args:
            needed_resources[resource] = True
    return needed_resources


@node_rescaler.route("/host/cpu_topology", methods=['GET'])
def get_cpu_topology():
    if os.path.exists("/proc/cpuinfo"):
        cpu_topology = __get_topology_from_procfs()
    else:
        cpu_topology = __get_topology_from_psutil()

    return jsonify(cpu_topology)


@node_rescaler.route("/container/", methods=['GET'])
@initialize_ContainerEngine
def get_containers_resources():
    try:
        container_name = request.form['name']
    except KeyError:
        container_name = request.args.get('name')

    if container_name is not None:
        return jsonify(node_resource_manager.get_node_resources_by_name(container_name))
    else:
        return jsonify(node_resource_manager.get_all_nodes())

@node_rescaler.route("/container/resources/", methods=['GET'])
@initialize_ContainerEngine
def get_container_specific_resources():
    try:
        container_name = request.form['name']
    except KeyError:
        container_name = request.args.get('name')

    needed_resources = __get_needed_resources(request)
    if container_name is not None:
        return jsonify(node_resource_manager.get_node_resources_by_name(container_name, needed_resources))
    else:
        return jsonify(node_resource_manager.get_all_nodes(needed_resources))

@node_rescaler.route("/container/resources/<container_name>", methods=['GET'])
@initialize_ContainerEngine
def get_container_specific_resources_by_name(container_name):
    needed_resources = __get_needed_resources(request)
    if container_name != "":
        data = node_resource_manager.get_node_resources_by_name(container_name, needed_resources)
        if data is not None:
            return jsonify(data)
        else:
            return abort(404)
    else:
        return jsonify(node_resource_manager.get_all_nodes())


@node_rescaler.route("/container/<container_name>", methods=['PUT'])
@initialize_ContainerEngine
def set_container_resources(container_name):
    if container_name != "":
        success, applied_config = node_resource_manager.set_node_resources(container_name, request.json)
        if not success:
            # TODO Improve the failure detection, filter out which set process failed and report it
            return Response(json.dumps(applied_config), status=500, mimetype='application/json')
        else:
            applied_config = node_resource_manager.get_node_resources_by_name(container_name)
            if applied_config is not None:
                return Response(json.dumps(applied_config), status=201, mimetype='application/json')
            else:
                return abort(404)
    else:
        abort(400)


@node_rescaler.route("/container/<container_name>", methods=['GET'])
@initialize_ContainerEngine
def get_container_resources_by_name(container_name):
    if container_name != "":
        data = node_resource_manager.get_node_resources_by_name(container_name)
        if data is not None:
            return jsonify(data)
        else:
            return abort(404)
    else:
        return jsonify(node_resource_manager.get_all_nodes())


@node_rescaler.route("/heartbeat", methods=['GET'])
def heartbeat():
    return Response(json.dumps({"status": "alive"}), status=200, mimetype='application/json')


if __name__ == "__main__":

    serverless_path = os.environ['SERVERLESS_PATH']
    config_file = serverless_path + "/services_config.yml"
    with open(config_file, "r") as cf:
        config = yaml.load(cf, Loader=yaml.FullLoader)

    container_engine = config['CONTAINER_ENGINE']
    singularity_command_alias = config['SINGULARITY_COMMAND_ALIAS']
    cgroups_version = config['CGROUPS_VERSION']

    # Create directory to manage an energy virtual cgroup
    energy_vcgroup_dir = serverless_path + "/energy_vcgroup"
    os.makedirs(energy_vcgroup_dir, exist_ok=True, mode=0o700)

    if container_engine == "lxc":
        node_resource_manager = LXDContainerManager(cgroups_version, energy_vcgroup_dir)
    elif container_engine == "apptainer":
        node_resource_manager = SingularityContainerManager(singularity_command_alias, cgroups_version, energy_vcgroup_dir)
    else:
        raise Exception("Error: a non-valid container engine was specified")

    WSGIRequestHandler.protocol_version = "HTTP/1.1"
    node_rescaler.run(host='0.0.0.0', port=8000)
