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
CPU_LIMIT_CPUS_LABEL = "cpu_num_limit"
CPU_LIMIT_ALLOWANCE_LABEL = "cpu_allowance_limit"
CPU_EFFECTIVE_CPUS_LABEL="effective_num_cpus"

def set_node_cpus(container, cpu_resource):
	limits_applied = True
	if CPU_LIMIT_CPUS_LABEL in cpu_resource:
		cpu_accounting_path = "/".join([CGROUP_PATH,"cpuacct","lxc",container.name,"cpu.cfs_quota_us"])
		cpu_limit = int(cpu_resource[CPU_LIMIT_ALLOWANCE_LABEL][:-1]) # Strip the percentage char and cast to int
		quota = 100 * cpu_limit # Every 100 period ticks count as 1% of CPU
		if quota == 0:
			quota = -1 # Set to max
		
		limit = str(quota)
		
		try:
			if os.path.isfile(cpu_accounting_path) and os.access(cpu_accounting_path,os.W_OK):
				cgroups_cpuacct_file = open(cpu_accounting_path,'w')
				cgroups_cpuacct_file.write(limit)
				cgroups_cpuacct_file.close()
				limits_applied = limits_applied and True
			else:
				limits_applied = limits_applied and False
		except IOError as e:
			print e
			limits_applied = limits_applied and False
			
	if CPU_LIMIT_ALLOWANCE_LABEL in cpu_resource:
		cpu_cpuset_path = "/".join([CGROUP_PATH,"cpuset","lxc",container.name,"cpuset.cpus"])
		try:
			if os.path.isfile(cpu_cpuset_path) and os.access(cpu_cpuset_path,os.W_OK):
				cgroups_cpuset_file = open(cpu_cpuset_path,'w')
				cgroups_cpuset_file.write(str(cpu_resource[CPU_LIMIT_CPUS_LABEL]))
				cgroups_cpuset_file.close()
				limits_applied = limits_applied and True
			else:
				limits_applied = limits_applied and False
		except IOError as e:
			print e
			limits_applied = limits_applied and False
	
	return limits_applied

def get_node_cpus(container):
	## Get info from cgroups cpuacct subsystem
	cpu_accounting_path = "/".join([CGROUP_PATH,"cpuacct","lxc",container.name,"cpu.cfs_quota_us"])
	cpu_limit = ""
	if os.path.isfile(cpu_accounting_path) and os.access(cpu_accounting_path,os.R_OK):
		cgroups_cpuacct_file = open(cpu_accounting_path,'r')
		for line in cgroups_cpuacct_file:
			cpu_limit = line.rstrip("\n") # Just 1 line should be available
		cgroups_cpuacct_file.close()
		cpu_limit = int(cpu_limit) / 100
		if cpu_limit < 2:
			cpu_limit = 0

			
	## Get info from cgroups cpuset subsystem
	cpus_path = "/".join([CGROUP_PATH,"cpuset","lxc",container.name,"cpuset.cpus"])
	cpus = ""
	if os.path.isfile(cpus_path) and os.access(cpus_path,os.R_OK):
		cgroups_cpus_file = open(cpus_path,'r')
		for line in cgroups_cpus_file:
			cpus = line.rstrip("\n") # Just 1 line should be available
		cgroups_cpus_file.close()
	
	#Get the number of effective, active cores for the container
	effective_cpus = 0
	parts = cpus.split(",")
	for part in parts:
		ranges = part.split("-")
		if len(ranges) == 1:
			effective_cpus += 1 # No range so only 1 core
		else:
			effective_cpus += (int(ranges[1]) - int(ranges[0])) + 1 #5-7 equals to 3 cores active
			
	final_dict = dict()
	final_dict[CPU_LIMIT_CPUS_LABEL] = cpus
	final_dict[CPU_EFFECTIVE_CPUS_LABEL] = str(effective_cpus)
	final_dict[CPU_LIMIT_ALLOWANCE_LABEL] = str(cpu_limit) + "%"
	
	return final_dict
	#return((";").join([CPU_HEADER,container.name,str(cpu_num),str(cpu_limit),cpus]))
#############


### MEM ####
MEM_LIMIT_LABEL_LXD = "limits.memory"
MEM_LIMIT_LABEL = "mem_limit"

def get_node_mem(container):
	mem_limit = 0 # no limit
	
	## Get info from memory cpuset subsystem
	memory_limit_path = "/".join([CGROUP_PATH,"memory","lxc",container.name,"memory.limit_in_bytes"])
	if os.path.isfile(memory_limit_path) and os.access(memory_limit_path,os.R_OK):
		cgroups_mem_file = open(memory_limit_path,'r')
		for line in cgroups_mem_file:
			mem_limit = line.rstrip("\n") # Just 1 line should be available
		cgroups_mem_file.close()
	
	
	mem_limit_converted = float(mem_limit) / 1073741824
	if mem_limit_converted < 1:
		# Less than 1 GB, report in MB
		mem_limit_converted = int(mem_limit_converted * 1024)
		mem_limit_converted = str(mem_limit_converted) + 'M'
	elif mem_limit_converted > 128:
		# more than 128G?, probably not limited so set to 0 ('unlimited')
		mem_limit_converted = str(0)
	else:
		# Report in GB
		mem_limit_converted = int(mem_limit_converted)
		mem_limit_converted = str(mem_limit_converted)  + 'G'
	
	final_dict = dict()
	final_dict[MEM_LIMIT_LABEL] = mem_limit_converted
	
	return final_dict

def set_node_mem(container, mem_resource):
	# Assume an integer for bytes (e.g.:1024000) or a string like 8G
	if MEM_LIMIT_LABEL in mem_resource:
		try:
			value = int(mem_resource[MEM_LIMIT_LABEL])
			if value == 0:
				# Set to -1 so a 'no limit' is applied, 0 is a no valid cgroups value for memory
				value = -1 
		except ValueError:
			# Try for the string limit
			# Strip the last character as it is a suffix, for mem subsystem valid values are e.g., 1024M, 1G...
			try:
				value = int(mem_resource[MEM_LIMIT_LABEL][:-1])
			except ValueError as e:
				print e
				# No valid value was given
				return False
		try:
			memory_limit_path = "/".join([CGROUP_PATH,"memory","lxc",container.name,"memory.limit_in_bytes"])
			if os.path.isfile(memory_limit_path) and os.access(memory_limit_path,os.W_OK):
				cgroups_mem_file = open(memory_limit_path,'w')
				cgroups_mem_file.write(str(value))
				cgroups_mem_file.close()
				return True
			else:
				# Can't access the file
				return False
		except IOError as e:
			print e
			return False
	else:
		# No limit was set
		return False
	

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
			if os.path.isfile(devices_read_limit_path) and os.access(devices_read_limit_path,os.W_OK):
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
			if os.path.isfile(devices_write_limit_path) and os.access(devices_write_limit_path,os.W_OK):
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
	return retrieved_nets


def unset_interface_limit(interface_name):
	try:
		tc = subprocess.Popen(["tc","qdisc","del","dev",interface_name,"root"],stderr=subprocess.PIPE)
		tc.wait()
		if tc.returncode == 0:
			return True
		else:
			return False
	except subprocess.CalledProcessError as e:
		return False

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
	def set_limit_with_host_interface(interface_in_host):
		if net[NET_LIMIT_LABEL] != "0" and net[NET_LIMIT_LABEL] != "":
			# Unset old limit and set new
			unset_interface_limit(net[NET_DEVICE_HOST_NAME_LABEL])
			return set_interface_limit(interface_in_host, net[NET_LIMIT_LABEL])
		else:
			# Unset the limit
			unset_interface_limit(interface_in_host)
			return True
	
	if NET_LIMIT_LABEL in net:
		if NET_DEVICE_HOST_NAME_LABEL in net:
			# host network interface available
			return set_limit_with_host_interface(net[NET_DEVICE_HOST_NAME_LABEL])
		else:
			# Retrieve the host interface using the internal container interface
			return False
	else:
		# No limit to set, leave untouched
		return True
	# Just check that it is set correctly, as trying to unset if it was not set will return an error (not idempotent)
	#return unset_interface_limit(net[NET_DEVICE_NAME_LABEL]) and set_interface_limit(net[NET_DEVICE_NAME_LABEL], net[NET_LIMIT_LABEL])
	
	

#############			


DICT_CPU_LABEL = "cpu"
DICT_MEM_LABEL = "mem"
DICT_DISK_LABEL = "disks"
DICT_NET_LABEL = "networks"

def set_node_resources(node_name, resources):
	client = Client(endpoint='https://192.168.0.10:8443', cert=('/home/jonatan/lxd.crt', '/home/jonatan/lxd.key'), verify=False)
	try:
		container = client.containers.get(node_name)
		if container.status == "Running":
			if DICT_CPU_LABEL in resources:
				print "CPU UPDATED: " + str(set_node_cpus(container, resources[DICT_CPU_LABEL]))	
			
			if DICT_MEM_LABEL in resources:
				print "MEM UPDATED: " + str(set_node_mem(container, resources[DICT_MEM_LABEL]))
				
			if DICT_DISK_LABEL in resources:
				for disk in resources[DICT_DISK_LABEL]:
					print "DISK UPDATED: " + str(set_node_disk(container, disk))
			
			if DICT_NET_LABEL in resources:
				for net in resources[DICT_NET_LABEL]:
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
			node_dict[DICT_CPU_LABEL] = get_node_cpus(container)
			node_dict[DICT_MEM_LABEL] = get_node_mem(container)
			node_dict[DICT_DISK_LABEL] = get_node_disks(container)
			node_dict[DICT_NET_LABEL] = get_node_networks(container)
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
