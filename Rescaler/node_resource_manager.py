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


def read_cgroup_file_value(file_path):
	# Read only 1 line for these files as they are 'virtual' files
	try:
		if os.path.isfile(file_path) and os.access(file_path,os.R_OK):
			with open(file_path, 'r') as file_handler:
				value = file_handler.readline().rstrip("\n") 
			return {"success":True, "data": value}
		else:
			return {"success":False, "error": str("Couldn't access file: " + file_path)}
	except IOError as e:
		return {"success":False, "error": str(e)}

def write_cgroup_file_value(file_path, value):
	# Write only 1 line for these files as they are 'virtual' files
	try:
		if os.path.isfile(file_path) and os.access(file_path,os.W_OK):
			with open(file_path, 'w') as file_handler:
				file_handler.write(str(value))
			return {"success":True, "data": value}
		else:
			return {"success":False, "error": str("Couldn't access file: " + file_path)}
	except IOError as e:
		return {"success":False, "error": str(e)}


### CPU ####
CPU_LIMIT_CPUS_LABEL = "cpu_num"
CPU_LIMIT_ALLOWANCE_LABEL = "cpu_allowance_limit"
CPU_EFFECTIVE_CPUS_LABEL="effective_num_cpus"
CPU_EFFECTIVE_LIMIT = "effective_cpu_limit"

TICKS_PER_CPU_PERCENTAGE = 1000

def get_node_cpus(container):
	## Get info from cgroups cpuacct subsystem
	cpu_accounting_path = "/".join([CGROUP_PATH,"cpuacct","lxc",container.name,"cpu.cfs_quota_us"])
	op = read_cgroup_file_value(cpu_accounting_path)
	if op["success"]:
		cpu_limit = int(op["data"])
		if cpu_limit != -1:
			# A limit is set, else leave it untouched
			cpu_limit = int(op["data"]) / TICKS_PER_CPU_PERCENTAGE
	else:
		return op

	## Get info from cgroups cpuset subsystem
	cpus_path = "/".join([CGROUP_PATH,"cpuset","lxc",container.name,"cpuset.cpus"])
	op = read_cgroup_file_value(cpus_path)
	if op["success"]:
		cpus = op["data"]
	else:
		return op
	
	#Get the number of effective, active cores for the container
	#5-7 equals to 3 cores active
	#0,1,2,4 equals to 4 cores active
	#0-3,6 equals to 5 cores active
	effective_cpus = 0
	parts = cpus.split(",")
	for part in parts:
		ranges = part.split("-")
		if len(ranges) == 1:
			effective_cpus += 1 # No range so only 1 core
		else:
			effective_cpus += (int(ranges[1]) - int(ranges[0])) + 1 
	
	# Get the effective limit of the container, if allowance is set, then it 
	# is limited by number of cpus available otherwise it is the number of 
	# cores multiplied per 100 for percentage
	if cpu_limit == -1:
		effective_limit = effective_cpus * 100
	else:
		effective_limit = min(cpu_limit, effective_cpus * 100)
	cpu_limit = str(cpu_limit) 
	
	final_dict = dict()
	final_dict[CPU_LIMIT_CPUS_LABEL] = cpus
	final_dict[CPU_EFFECTIVE_CPUS_LABEL] = str(effective_cpus)
	final_dict[CPU_EFFECTIVE_LIMIT] = str(effective_limit)
	final_dict[CPU_LIMIT_ALLOWANCE_LABEL] = cpu_limit
	
	return ({"success": True, "data": final_dict})

##
def dump(obj):
  for attr in dir(obj):
    print("obj.%s = %r" % (attr, getattr(obj, attr)))
##
	
def set_node_cpus(container, cpu_resource):
	if CPU_LIMIT_ALLOWANCE_LABEL in cpu_resource:
		cpu_accounting_path = "/".join([CGROUP_PATH,"cpuacct","lxc",container.name,"cpu.cfs_quota_us"])
		
		try:
			if cpu_resource[CPU_LIMIT_ALLOWANCE_LABEL] == "-1":
				cpu_limit = -1
			else:
				cpu_limit = int(cpu_resource[CPU_LIMIT_ALLOWANCE_LABEL])
		except ValueError as e:
			return ({"success": False,"error": str(e)})
			
		if cpu_limit == 0:
			quota = -1 # Set to max
		else:
			quota = TICKS_PER_CPU_PERCENTAGE * cpu_limit # Every 1000 period ticks count as 1% of CPU
		
		op = write_cgroup_file_value(cpu_accounting_path, str(quota))
		if not op["success"]:
			#Something happened
			return op
	
	#print dump(container)
				
	if CPU_LIMIT_CPUS_LABEL in cpu_resource:
		#container.config["limits.cpu"] = cpu_resource[CPU_LIMIT_CPUS_LABEL]
		cpu_cpuset_path = "/".join([CGROUP_PATH,"cpuset","lxc",container.name,"cpuset.cpus"])
		
		op = write_cgroup_file_value(cpu_cpuset_path, str(cpu_resource[CPU_LIMIT_CPUS_LABEL]))
		if not op["success"]:
			#Something happened
			return op
	
	# Nothing bad happened
	return {"success":True}

#############


### MEM ####
MEM_LIMIT_LABEL_LXD = "limits.memory"
MEM_LIMIT_LABEL = "mem_limit"
LOWER_LIMIT_MEGABYTES = 64
def get_node_mem(container):
	memory_limit_path = "/".join([CGROUP_PATH,"memory","lxc",container.name,"memory.limit_in_bytes"])
	
	op = read_cgroup_file_value(memory_limit_path)
	if op["success"]:
		mem_limit = op["data"]
	else:
		return op
		
	mem_limit_converted = int(mem_limit) / 1048576 # Convert to MB
	if mem_limit_converted > 65536:
		# more than 64G?, probably not limited so set to -1 ('unlimited')
		mem_limit_converted = str(-1)
	
	final_dict = dict()
	final_dict[MEM_LIMIT_LABEL] = mem_limit_converted
	final_dict["unit"] = "M"
	
	return ({"success": True, "data": final_dict})

def set_node_mem(container, mem_resource):
	# Assume an integer for megabytes, add the M and set to cgroups
	if MEM_LIMIT_LABEL in mem_resource:
		try:
			value = int(mem_resource[MEM_LIMIT_LABEL])
			if value < LOWER_LIMIT_MEGABYTES:
				# Don't allow values lower than an amount like 64 MB as it will probably block the container
				return {"success":False, "error": "Memory limit is too low, less than " + LOWER_LIMIT_MEGABYTES + " MB"}
		except ValueError:
			# Try for a possible string value or the "-1" value that is unlimited
			# CAUTION, very low values like 1M are not checked and will go through
			value = mem_resource[MEM_LIMIT_LABEL]
			if value == "-1" or value == "":
				value = -1
		
		memory_limit_path = "/".join([CGROUP_PATH,"memory","lxc",container.name,"memory.limit_in_bytes"])
		op = write_cgroup_file_value(memory_limit_path, str(value))
		if not op["success"]:
			#Something happened
			return op
		
	# Nothing bad happened
	return {"success":True}
#############


### DISK ####
DISK_READ_LIMIT_LABEL = "disk_read_limit"
DISK_WRITE_LIMIT_LABEL = "disk_write_limit"

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
				device_read_limit = str(0)
			
			if major_minor_str in limits_write:
				device_write_limit = limits_write[major_minor_str]
			else:
				device_write_limit = str(0)
			
			disk_dict = dict()
			disk_dict["mountpoint"] = device_mountpoint
			disk_dict["device_path"] = device_path
			disk_dict["major"] = major
			disk_dict["minor"] = minor
			disk_dict[DISK_READ_LIMIT_LABEL] = device_read_limit
			disk_dict[DISK_WRITE_LIMIT_LABEL] = device_write_limit

			retrieved_disks.append(disk_dict)
	return {"success":True, "data":retrieved_disks}


def set_node_disk(container, disk_resource):
	major = disk_resource["major"]
	minor = disk_resource["minor"]
	node_name = container.name
	blkio_path = "/".join([CGROUP_PATH,"blkio","lxc",node_name])
		
	if DISK_READ_LIMIT_LABEL in disk_resource:
		limit_read = disk_resource[DISK_READ_LIMIT_LABEL]
		devices_read_limit_path = blkio_path + "/blkio.throttle.read_bps_device"
		
		op = write_cgroup_file_value(devices_read_limit_path, str(major + ":" + minor + " " + limit_read))
		if not op["success"]:
			#Something happened
			return op
		
	if DISK_WRITE_LIMIT_LABEL in disk_resource:
		limit_write = disk_resource[DISK_WRITE_LIMIT_LABEL]
		devices_write_limit_path = blkio_path + "/blkio.throttle.write_bps_device"
		
		op = write_cgroup_file_value(devices_write_limit_path, str(major + ":" + minor + " " + limit_write))
		if not op["success"]:
			#Something happened
			return op
	
	# Nothing bad happened
	return {"success":True}
	
	
#############

### NET ####

NET_DEVICE_HOST_NAME_LABEL = "device_name_in_host"
NET_DEVICE_NAME_LABEL = "device_name_in_container"
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
			net_dict[NET_DEVICE_NAME_LABEL] = net
			net_dict[NET_DEVICE_HOST_NAME_LABEL] = interface_host_name
			net_dict[NET_LIMIT_LABEL] = get_interface_limit(interface_host_name)

			retrieved_nets.append(net_dict)
	
	return {"success":True, "data":retrieved_nets}


def unset_interface_limit(interface_name):
	try:
		tc = subprocess.Popen(["tc","qdisc","del","dev",interface_name,"root"],stderr=subprocess.PIPE)
		tc.wait()
		if tc.returncode == 0:
			return {"success":True}
		else:
			return {"success":False,"error": "exit code of tc was: " + str(tc.returncode)}
	except subprocess.CalledProcessError as e:
		return {"success":False,"error": str(e)}

def set_interface_limit(interface_name, limit):
	try:
		tc = subprocess.Popen(["tc","qdisc","add","dev",interface_name,"root","tbf","rate",limit,"burst","1000kb","latency","100ms"],stderr=subprocess.PIPE)
		tc.wait()
		if tc.returncode == 0:
			return {"success":True}
		else:
			return {"success":False,"error": "exit code of tc was: " + str(tc.returncode)}
	except subprocess.CalledProcessError as e:
		return {"success":False,"error": str(e)}

def set_node_net(container, net):
	if NET_LIMIT_LABEL in net:
		if NET_DEVICE_HOST_NAME_LABEL in net:
			# host network interface available (e.g., vethWMPX65)
			interface_in_host = net[NET_DEVICE_HOST_NAME_LABEL]
		else:
			# Retrieve the host interface using the internal container interface
			#  (e.g., eth0)
			if NET_DEVICE_NAME_LABEL in net:
				node_nets = get_node_networks(container)["data"]
				for n in node_nets:
					if n[NET_DEVICE_NAME_LABEL] == net[NET_DEVICE_NAME_LABEL]:
						interface_in_host = n[NET_DEVICE_HOST_NAME_LABEL]
			else:
				# If no host or container interface name is available, it is not possible to do anything
				return {"success":False,"error": "No interface name, either host bridge or container interface name, was provided"}
		if net[NET_LIMIT_LABEL] != "0" and net[NET_LIMIT_LABEL] != "":
			# Unset old limit and set new
			unset_interface_limit(interface_in_host)
			return set_interface_limit(interface_in_host, net[NET_LIMIT_LABEL])
		else:
			# Unset the limit
			unset_interface_limit(interface_in_host)
			# Nothing bad happened
			return {"success":True}
		
	else:
		# No limit to set, leave untouched
		# Nothing bad happened
		return {"success":True}
	# Just check that it is set correctly, as trying to unset if it was not set will return an error (not idempotent)
	#return unset_interface_limit(net[NET_DEVICE_NAME_LABEL]) and set_interface_limit(net[NET_DEVICE_NAME_LABEL], net[NET_LIMIT_LABEL])
	
	

#############			


DICT_CPU_LABEL = "cpu"
DICT_MEM_LABEL = "mem"
DICT_DISK_LABEL = "disks"
DICT_NET_LABEL = "networks"

def set_node_resources(node_name, resources):
	client = Client(endpoint='https://192.168.0.10:8443', cert=('/home/jonatan/lxd.crt', '/home/jonatan/lxd.key'), verify=False)
	if resources == None:
		# No resources to set
		return False
	else:
		try:
			container = client.containers.get(node_name)
			if container.status == "Running":
				if DICT_CPU_LABEL in resources:
					set_node_cpus(container, resources[DICT_CPU_LABEL])
				
				if DICT_MEM_LABEL in resources:
					set_node_mem(container, resources[DICT_MEM_LABEL])
					
				if DICT_DISK_LABEL in resources:
					for disk in resources[DICT_DISK_LABEL]:
						set_node_disk(container, disk)
				
				if DICT_NET_LABEL in resources:
					for net in resources[DICT_NET_LABEL]:
						if NET_DEVICE_HOST_NAME_LABEL in net:
							del net[NET_DEVICE_HOST_NAME_LABEL]
						set_node_net(container, net)
				return True
			else:
				# If container not running, skip
				return False
		except pylxd.exceptions.NotFound:
			# If node not found, pass
			return False

def get_node_resources(node_name):
	client = Client(endpoint='https://192.168.0.10:8443', cert=('/home/jonatan/lxd.crt', '/home/jonatan/lxd.key'), verify=False)
	#client.authenticate(LXD_PASSWORD)
	try:
		
		container = client.containers.get(node_name)
		if container.status == "Running":
			node_dict = dict()
			
			cpu_resources = get_node_cpus(container)
			if cpu_resources["success"]:
				node_dict[DICT_CPU_LABEL] = cpu_resources["data"]
			else:
				node_dict[DICT_CPU_LABEL] = cpu_resources
			
			mem_resources = get_node_mem(container)
			if mem_resources["success"]:
				node_dict[DICT_MEM_LABEL] = mem_resources["data"]
			else:
				node_dict[DICT_MEM_LABEL] = mem_resources
				
			disk_resources = get_node_disks(container)
			if disk_resources["success"]:
				node_dict[DICT_DISK_LABEL] = disk_resources["data"]
			else:
				node_dict[DICT_DISK_LABEL] = disk_resources
			
			net_resources = get_node_networks(container)
			if net_resources["success"]:
				node_dict[DICT_NET_LABEL] = net_resources["data"]
			else:
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

def main():
	if sys.argv[1] == "get":
		for arg in sys.argv[2:]:
			print json.dumps(get_node_resources(arg))
			
	if sys.argv[1] == "set":
		## TMP ##
		resources = dict()
		set_node_resources("node0",get_node_resources("node0"))
		set_node_resources("node1",get_node_resources("node1"))
		set_node_resources("node2",get_node_resources("node2"))
		set_node_resources("node3",get_node_resources("node3"))
		## TMP ##
		
if __name__ == "__main__":
    main()
