#!/usr/bin/python
import sys
import os
import subprocess
import urllib3
import pylxd
from pylxd import Client


urllib3.disable_warnings()

CPU_HEADER = "CPU"
MEM_HEADER = "MEM"
DISK_HEADER = "DISK"
NET_HEADER = "NET"


CGROUP_PATH = "/sys/fs/cgroup"
LXD_PASSWORD = "testlxd"


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
	

def get_node_cpus(container):
	config = container.expanded_config
	cpu_limit = 100 # no limit
	cpu_num = 0
	
	cpus_path = "/".join([CGROUP_PATH,"cpuset","lxc",container.name,"cpuset.cpus"])
	cpus = ""
	
	## Get info from LXD database
	if "limits.cpu.allowance" in config:
		cpu_limit = config["limits.cpu.allowance"] #can be 50% or 25ms/200ms
		try:
			# Try for the case of a percentage, get all string except last character, the '%' char
			cpu_limit = int(cpu_limit[:-1])
		except ValueError:
			# If no percentage, then try for fraction
			parts = cpu_limit.split("/")
			(first, second) = parts[0],parts[1]
			cpu_limit =  100 * float(first[:-2])/float(second[:-2]) # considering that the limit is set as Xms/Yms
		
	if "limits.cpu" in config:
		cpu_num = int(config["limits.cpu"])
	
	## Get info from cgroups filesystem
	if os.path.isfile(cpus_path) and os.access(cpus_path,os.R_OK):
		cgroups_cpus_file = open(cpus_path,'r')
		for line in cgroups_cpus_file:
			cpus = line.rstrip("\n") # Just 1 line should be available

		cgroups_cpus_file.close()
	
	print((";").join([CPU_HEADER,container.name,str(cpu_num),str(cpu_limit),cpus]))


def get_node_mem(container):
	config = container.expanded_config
	mem_limit = 0 # no limit
	if "limits.memory" in config:
		mem_limit = config["limits.memory"]
	
	print((";").join([MEM_HEADER,container.name,str(mem_limit)]))
	

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


def get_node_disks_map(container):
	devices = container.devices
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
			
			print((";").join([DISK_HEADER,container.name,device_mountpoint,device_path,str(major),str(minor), str(device_read_limit), str(device_write_limit)]))
			

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
	if not networks:
		pass
	else:
		for net in networks.keys():
			if net == "lo":
				continue
			interface_host_name = networks[net]["host_name"]
			print((";").join([NET_HEADER, container.name, net,interface_host_name, get_interface_limit(interface_host_name)]))
			

def get_node_resources(node_name):
	client = Client(endpoint='https://192.168.0.10:8443', cert=('/home/jonatan/lxd.crt', '/home/jonatan/lxd.key'), verify=False)
	#client.authenticate(LXD_PASSWORD)
	try:
		container = client.containers.get(node_name)
		if container.status == "Running":
			get_node_cpus(container)
			get_node_mem(container)
			get_node_disks_map(container)
			get_node_networks(container)
		else:
			# If container not running, skip
			pass
	except pylxd.exceptions.NotFound:
		# If node not found, pass
		pass


def main():
	for arg in sys.argv[1:]:
		get_node_resources(arg)
		
if __name__ == "__main__":
    main()
