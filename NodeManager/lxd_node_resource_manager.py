#!/usr/bin/python
import sys
import os
import subprocess
import urllib3
import json
import pylxd
from pylxd import Client

urllib3.disable_warnings()

LXD_PASSWORD = "testlxd"

# Getters
from node_resource_manager import get_node_cpus
from node_resource_manager import get_node_mem
from node_resource_manager import get_node_disks as cgroups_get_node_disks
from node_resource_manager import get_node_networks as cgroups_get_node_networks

#Setters
from node_resource_manager import set_node_cpus
from node_resource_manager import set_node_mem
from node_resource_manager import set_node_disk
from node_resource_manager import set_node_net

def get_node_disks(container):
	devices = container.devices
	if not devices:
		return {"success":True, "data":[]} 
	else:
		return cgroups_get_node_disks(container.name, devices)


def get_node_networks(container):
	networks = container.state().network
	if not networks:
		return {"success":True, "data":[]} 
	else:
		network_host_interfaces = list()
		for net in networks.keys():
			if net == "lo":
				continue # Skip the internal loopback interface
			network_host_interfaces.append({"container_interface":net, "host_interface":networks[net]["host_name"]})
			
		return cgroups_get_node_networks(network_host_interfaces)


DICT_CPU_LABEL = "cpu"
DICT_MEM_LABEL = "mem"
DICT_DISK_LABEL = "disks"
DICT_NET_LABEL = "networks"

def set_node_resources(node_name, resources):
	client = Client(endpoint='https://192.168.0.10:8443', cert=('/home/jonatan/lxd.crt', '/home/jonatan/lxd.key'), verify=False)
	if resources == None:
		# No resources to set
		return False, {}
	else:
		try:
			container = client.containers.get(node_name)
			if container.status == "Running":
				node_dict = dict()
				(cpu_success, mem_success, disk_success, net_success) = (True,True,True,True)
				if DICT_CPU_LABEL in resources:
					cpu_success, cpu_resources = set_node_cpus(node_name, resources[DICT_CPU_LABEL])
					node_dict[DICT_CPU_LABEL] = cpu_resources
								
				if DICT_MEM_LABEL in resources:
					mem_success, mem_resources = set_node_mem(node_name, resources[DICT_MEM_LABEL])
					node_dict[DICT_MEM_LABEL] = mem_resources
								
				if DICT_DISK_LABEL in resources:
					disks_changed = list()
					for disk in resources[DICT_DISK_LABEL]:
						disk_success, disk_resource = set_node_disk(node_name, disk)
						disks_changed.append(disk_resource)
						node_dict[DICT_DISK_LABEL] = disks_changed
				
				if DICT_NET_LABEL in resources:
					networks_changed = list()
					for net in resources[DICT_NET_LABEL]:
						net_success, net_resource = set_node_net(node_name, net)
						networks_changed.append(net_resource)
						node_dict[DICT_NET_LABEL] = networks_changed
				
				global_success = cpu_success and mem_success and disk_success and net_success
				return global_success, node_dict
			else:
				# If container not running, skip
				return False, {}
		except pylxd.exceptions.NotFound:
			# If node not found, pass
			return False, {}

def get_node_resources(node_name):
	client = Client(endpoint='https://192.168.0.10:8443', cert=('/home/jonatan/lxd.crt', '/home/jonatan/lxd.key'), verify=False)
	#client.authenticate(LXD_PASSWORD)
	try:
		
		container = client.containers.get(node_name)
		if container.status == "Running":
			node_dict = dict()
			
			cpu_success, cpu_resources = get_node_cpus(node_name)
			node_dict[DICT_CPU_LABEL] = cpu_resources
			
			mem_success, mem_resources = get_node_mem(node_name)
			node_dict[DICT_MEM_LABEL] = mem_resources
			
			disk_success, disk_resources = get_node_disks(container) # LXD Dependent
			node_dict[DICT_DISK_LABEL] = disk_resources
			
			net_success, net_resources = get_node_networks(container) # LXD Dependent
			node_dict[DICT_NET_LABEL] = net_resources
						
			return node_dict
		else:
			# If container not running, skip
			pass
	except pylxd.exceptions.NotFound:
		# If node not found, pass
		pass

def get_all_nodes():
	client = Client(endpoint='https://192.168.0.10:8443', cert=('/home/jonatan/lxd.crt', '/home/jonatan/lxd.key'), verify=False)
	containers = client.containers.all()
	containers_dict = dict()
	for c in containers:
		if c.status == "Running":
			containers_dict[c.name] = get_node_resources(c.name)
	return containers_dict

#def main():
	#if sys.argv[1] == "get":
		#for arg in sys.argv[2:]:
			#print json.dumps(get_node_resources(arg))
			
	#if sys.argv[1] == "set":
		### TMP ##
		#resources = dict()
		#set_node_resources("node0",get_node_resources("node0"))
		#set_node_resources("node1",get_node_resources("node1"))
		#set_node_resources("node2",get_node_resources("node2"))
		#set_node_resources("node3",get_node_resources("node3"))
		### TMP ##
		
#if __name__ == "__main__":
    #main()
