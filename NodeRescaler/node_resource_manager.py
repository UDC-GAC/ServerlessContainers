#!/usr/bin/python
import sys
import os
import subprocess
import urllib3
import json
import pylxd
from pylxd import Client

urllib3.disable_warnings()

CGROUP_PATH = "/sys/fs/cgroup"
LXD_PASSWORD = "testlxd"


### CPU ####
CPU_LIMIT_LABEL_LXD = "limits.cpu"
CPU_ALLOWANCE_LABEL_LXD = "limits.cpu.allowance"

CPU_LIMIT_LABEL = "cpu_limit"

def set_node_cpus(container, cpu_resource):
	limit_type = cpu_resource["limit_type"]
	
	# Assume an integer (e.g.:3), a range (e.g.:3-5) or a limit in the form of 25ms/100ms
	limit = cpu_resource[CPU_LIMIT_LABEL]
	
	if limit_type == "cpus" or limit_type == "cpuset":
		try:
			config = container.config
			config[CPU_LIMIT_LABEL_LXD] = limit
			container.save(config)
			return True
		except Error:
			return False
			
	if limit_type == "cpu_allowance":
		try:
			config = container.config
			config[CPU_ALLOWANCE_LABEL_LXD] = limit
			container.save(config)
			return True
		except Error:
			return False
					

def get_node_cpus(container):
	config = container.expanded_config
	cpu_limit = 100 # no limit
	cpu_num = 0
	
	cpus_path = "/".join([CGROUP_PATH,"cpuset","lxc",container.name,"cpuset.cpus"])
	cpus = ""
	
	## Get info from LXD database
	if CPU_ALLOWANCE_LABEL_LXD in config:
		cpu_limit = config[CPU_ALLOWANCE_LABEL_LXD] #can be 50% or 25ms/200ms
		try:
			# Try for the case of a percentage, get all string except last character, the '%' char
			cpu_limit = int(cpu_limit[:-1])
		except ValueError:
			# If no percentage, then try for fraction
			parts = cpu_limit.split("/")
			(first, second) = parts[0],parts[1]
			cpu_limit =  100 * float(first[:-2])/float(second[:-2]) # considering that the limit is set as Xms/Yms
		
	## Get info from cgroups filesystem
	if os.path.isfile(cpus_path) and os.access(cpus_path,os.R_OK):
		cgroups_cpus_file = open(cpus_path,'r')
		for line in cgroups_cpus_file:
			cpus = line.rstrip("\n") # Just 1 line should be available

		cgroups_cpus_file.close()
	
	
	final_dict = dict()
	final_dict["cpus"] = cpus
	final_dict["cpu_limit"] = cpu_limit
	
	return final_dict
	#return((";").join([CPU_HEADER,container.name,str(cpu_num),str(cpu_limit),cpus]))
#############


### MEM ####
MEM_LIMIT_LABEL_LXD = "limits.memory"
MEM_LIMIT_LABEL = "mem_limit"

def get_node_mem(container):
	config = container.expanded_config
	mem_limit = 0 # no limit
	if MEM_LIMIT_LABEL_LXD in config:
		mem_limit = config[MEM_LIMIT_LABEL_LXD]
		
	final_dict = dict()
	final_dict[MEM_LIMIT_LABEL] = mem_limit
	
	return final_dict
	#return((";").join([MEM_HEADER,container.name,str(mem_limit)]))

def set_node_mem(container, mem_resource):
	# Assume an integer for bytes (e.g.:1024000) or a string like 8G
	value = mem_resource[MEM_LIMIT_LABEL]
	
	try:
		config = container.config
		config[MEM_LIMIT_LABEL_LXD] = value
		container.save(config)
		return True
	except pylxd.exceptions.LXDAPIException as e:
		print(e)
		return False

#############


### DISK ####
DISK_READ_LIMIT_LABEL = "limit_read"
DISK_WRITE_LIMIT_LABEL = "limit_write"

def get_system_mounted_filesystems():
	df = subprocess.Popen(["df","--output=source,target"], stdout=subprocess.PIPE)
	trim = subprocess.Popen(["tr","-s","[:blank:]",","], stdin=df.stdout, stdout=subprocess.PIPE)
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
	dmsetup = subprocess.Popen(["dmsetup","info","-c","-o","major,minor","--separator=,","--noheadings",device_path], stdout=subprocess.PIPE)
	return dmsetup.communicate()[0].strip().split(",")

def get_node_disk_limits(node_name):
	blkio_path = "/".join([CGROUP_PATH,"blkio","lxc",node_name])
	devices_read_limit_path = blkio_path + "/blkio.throttle.read_bps_device"
	devices_write_limit_path = blkio_path + "/blkio.throttle.write_bps_device"
	devices_read_limits = dict()
	devices_write_limits = dict()

	if os.path.isfile(devices_read_limit_path) and os.access(devices_read_limit_path,os.R_OK):
		devices_read_limit_file = open(devices_read_limit_path,'r')
		for line in devices_read_limit_file:
			parts = line.rstrip("\n").split()
			major_minor = parts[0]
			limit = parts[1]
			devices_read_limits[major_minor] = limit
		devices_read_limit_file.close()

	if os.path.isfile(devices_write_limit_path) and os.access(devices_write_limit_path,os.R_OK):
		devices_write_limit_file = open(devices_write_limit_path,'r')
		for line in devices_write_limit_file:
			parts = line.rstrip("\n").split()
			major_minor = parts[0]
			limit = parts[1]
			devices_write_limits[major_minor] = limit
		devices_write_limit_file.close()
	
	return devices_read_limits, devices_write_limits

def get_node_disks(container):
	devices = container.devices
	retrieved_disks = list()
	if not devices:
		pass
	else:
		limits_read, limits_write = get_node_disk_limits(container.name)
		for device in devices.keys():
			device_mountpoint = devices[device]["source"]
			device_path = get_device_path_from_mounted_filesystem(device_mountpoint)
			major,minor = get_device_major_minor(device_path)
			
			major_minor_str = major+":"+minor
			
			if major_minor_str in limits_read:
				device_read_limit = limits_read[major_minor_str]
			else:
				device_read_limit = 0
			
			if major_minor_str in limits_write:
				device_write_limit = limits_write[major_minor_str]
			else:
				device_write_limit = 0
			
			disk_dict = dict()
			disk_dict["mountpoint"] = device_mountpoint
			disk_dict["device_path"] = device_path
			disk_dict["major"] = major
			disk_dict["minor"] = minor
			disk_dict[DISK_READ_LIMIT_LABEL] = device_read_limit
			disk_dict[DISK_WRITE_LIMIT_LABEL] = device_write_limit

			
			retrieved_disks.append(disk_dict)
			#print((";").join([DISK_HEADER,container.name,device_mountpoint,device_path,str(major),str(minor), str(device_read_limit), str(device_write_limit)]))
	return retrieved_disks


def set_node_disk(container, disk_resource):
	major = disk_resource["major"]
	minor = disk_resource["minor"]
	node_name = container.name
	blkio_path = "/".join([CGROUP_PATH,"blkio","lxc",node_name])
	
	limits_applied = True
	
	if DISK_READ_LIMIT_LABEL in disk_resource:
		limit_read = disk_resource[DISK_READ_LIMIT_LABEL]
		devices_read_limit_path = blkio_path + "/blkio.throttle.read_bps_device"
		try:
			if os.path.isfile(devices_read_limit_path) and os.access(devices_read_limit_path,os.R_OK):
				devices_read_limit_file = open(devices_read_limit_path,'w')
				devices_read_limit_file.write(major + ":" + minor + " " + limit_read)
				devices_read_limit_file.close()
			else:
				limits_applied = limits_applied and False
		except IOError:
			limits_applied = limits_applied and False
		
	
	if DISK_WRITE_LIMIT_LABEL in disk_resource:
		limit_write = disk_resource[DISK_WRITE_LIMIT_LABEL]
		devices_write_limit_path = blkio_path + "/blkio.throttle.write_bps_device"
		try:
			if os.path.isfile(devices_write_limit_path) and os.access(devices_write_limit_path,os.R_OK):
				devices_write_limit_file = open(devices_write_limit_path,'w')
				devices_write_limit_file.write(major + ":" + minor + " " + limit_write)
				devices_write_limit_file.close()
			else:
				limits_applied = limits_applied and False
		except IOError:
			limits_applied = limits_applied and False

	return limits_applied
	
	
#############

### NET ####

NET_DEVICE_NAME_LABEL = "device_name_in_host"
NET_LIMIT_LABEL = "net_limit"

def get_interface_limit(interface_name):
	tc = subprocess.Popen(["tc","-d","qdisc","show","dev",interface_name], stdout=subprocess.PIPE)
	lines = tc.communicate()[0].strip().split(",")
	for line in lines:
		parts = line.rstrip("\n").split() # Just 1 line should be available
		break
	if len(parts) > 6:
		return parts[7]
	else:
		return "0"

def get_node_networks(container):
	networks = container.state().network
	retrieved_nets = list()
	if not networks:
		pass
	else:
		for net in networks.keys():
			if net == "lo":
				continue
			interface_host_name = networks[net]["host_name"]
			
			net_dict = dict()
			net_dict["net"] = net
			net_dict[NET_DEVICE_NAME_LABEL] = interface_host_name
			net_dict["limit"] = get_interface_limit(interface_host_name)

			#return((";").join([NET_HEADER, container.name, net, interface_host_name, get_interface_limit(interface_host_name)]))
			retrieved_nets.append(net_dict)
	return retrieved_nets


def set_interface_limit(interface_name, limit):
	try:
		tc = subprocess.Popen(["tc","qdisc","add","dev",interface_name,"root","tbf","rate",limit,"burst","1000kb","latency","100ms"],stderr=subprocess.PIPE)
		tc.wait()
		if tc.returncode == 0:
			return True
		else:
			return False
	except subprocess.CalledProcessError as e:
		return False
	
def set_node_net(container, net):
	return set_interface_limit(net[NET_DEVICE_NAME_LABEL], net[NET_LIMIT_LABEL])
	
	

#############			


def set_node_resources(node_name, resources):
	client = Client(endpoint='https://192.168.0.10:8443', cert=('/home/jonatan/lxd.crt', '/home/jonatan/lxd.key'), verify=False)
	try:
		container = client.containers.get(node_name)
		if container.status == "Running":
			if "cpu" in resources:
				print "CPU UPDATED: " + str(set_node_cpus(container, resources["cpu"]))	
			
			if "mem" in resources:
				print "MEM UPDATED: " + str(set_node_mem(container, resources["mem"]))
				
			if "disks" in resources:
				for disk in resources["disks"]:
					print "DISK UPDATED: " + str(set_node_disk(container, disk))
			
			if "networks" in resources:
				for net in resources["networks"]:
					print "NET UPDATED: " + str(set_node_net(container, net))
		else:
			# If container not running, skip
			pass
	except pylxd.exceptions.NotFound:
		# If node not found, pass
		pass
		
	

def get_node_resources(node_name):
	client = Client(endpoint='https://192.168.0.10:8443', cert=('/home/jonatan/lxd.crt', '/home/jonatan/lxd.key'), verify=False)
	#client.authenticate(LXD_PASSWORD)
	try:
		container = client.containers.get(node_name)
		if container.status == "Running":
			node_dict = dict()
			node_dict["cpu"] = get_node_cpus(container)
			node_dict["mem"] = get_node_mem(container)
			node_dict["disks"] = get_node_disks(container)
			node_dict["networks"] = get_node_networks(container)
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

def main():
	if sys.argv[1] == "get":
		for arg in sys.argv[2:]:
			get_node_resources(arg)
			
	if sys.argv[1] == "set":
		for arg in sys.argv[2:]:
			## TMP ##
			resources = dict()
			
			#resources["cpu"] = {"limit_type" : "cpus", CPU_LIMIT_LABEL : "4"}
			resources["cpu"] = {"limit_type" : "cpus", CPU_LIMIT_LABEL : "0-4"}
			resources["cpu"] = {"limit_type" : "cpu_allowance", CPU_LIMIT_LABEL : "25ms/100ms"}
			resources["mem"] = {MEM_LIMIT_LABEL : "8GB"}
			resources["disks"] = [{DISK_WRITE_LIMIT_LABEL: "1024000", DISK_READ_LIMIT_LABEL: "1024000", "major":"253", "minor":"7"},{DISK_WRITE_LIMIT_LABEL: "1024000", DISK_READ_LIMIT_LABEL: "1024000", "major":"253", "minor":"21"}]
			resources["networks"] = [{NET_LIMIT_LABEL: "10mbit", NET_DEVICE_NAME_LABEL : "vethNWC856"}]
			set_node_resources(arg, resources)
			## TMP ##
		
		
if __name__ == "__main__":
    main()
