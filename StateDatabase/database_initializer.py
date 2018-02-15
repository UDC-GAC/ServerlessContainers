#/usr/bin/python
import couchDB

def initialize():

	handler = couchDB.CouchDBServer()
	handler.remove_all_dbs()
	handler.create_all_dbs()

	# CREATE LIMITS
	if handler.database_exists("limits"):
		print ("Adding 'limits' documents")
		node0 = dict(
			#_id = 'node0', 
			type='limit', 
			node='node0', 
			resources=dict(
				cpu=dict(upper=150,lower=70), 
				mem=dict(upper=1024,lower=512), 
				disk=dict(upper=100,lower=100), 
				net=dict(upper=100,lower=100)
			)
		)
		node1 = dict(
			#_id = 'node1', 
			type='limit', 
			node='node1', 
			resources=dict(
				cpu=dict(upper=300,lower=100), 
				mem=dict(upper=2048,lower=1024),
				disk=dict(upper=100,lower=100),
				net=dict(upper=100,lower=100)
			)
		)
		handler.add_doc("limits", node0)
		handler.add_doc("limits", node1)

	# CREATE NODES
	if handler.database_exists("nodes"):
		print ("Adding 'nodes' documents")
		node0 = dict(
			#_id = 'node0', 
			type='node', 
			node='node0', 
			resources=dict(
				cpu=dict(max=300,current=100,min=50), 
				mem=dict(max=4096,current=1024,min=256), 
				disk=dict(max=100,current=100,min=100), 
				net=dict(max=100,current=100,min=100)
			)
		)
		node1 = dict(
			#_id = 'node2', 
			type='node', 
			node='node1', 
			resources=dict(
				cpu=dict(max=400,current=200,min=100), 
				memory=dict(max=4096,current=1024,min=512), 
				disk=dict(max=100,current=100,min=100), 
				network=dict(max=100,current=100,min=100)
			)
		)
		handler.add_doc("nodes", node0)
		#handler.add_doc("nodes", node1)
		
	# CREATE RULES
	if handler.database_exists("rules"):
		print ("Adding 'rules' documents")

		# CPU
		cpu_exceeded_upper = dict(_id = 'cpu_exceeded_upper', type='rule', resource="cpu", name='cpu_exceeded_upper', rule=dict({"and":[{">":[{"var": "proc.cpu.user"},{"var": "limits.cpu.upper"}]},{"<":[{"var": "limits.cpu.upper"},{"var": "nodes.cpu.max"}]}]}), generates="events", action={"events":{"scale":{"up":1}}})
		cpu_dropped_lower = dict(_id = 'cpu_dropped_lower', type='rule', resource="cpu", name='cpu_dropped_lower', rule=dict({"and":[{"<":[{"var": "proc.cpu.user"},{"var": "limits.cpu.lower"}]},{">":[{"var": "limits.cpu.lower"},{"var": "nodes.cpu.min"}]}]}), generates="events", action={"events":{"scale":{"down":1}}})
		handler.add_doc("rules", cpu_exceeded_upper)
		handler.add_doc("rules", cpu_dropped_lower)

		CpuRescaleUp = dict(_id = 'CpuRescaleUp', type='rule', resource="cpu", name='CpuRescaleUp', rule=dict({">":[{"var": "events.scale.up"},3]}), events_to_remove=3, generates="requests", action={"requests":["CpuRescaleUp"]}, amount=100)
		CpuRescaleDown = dict(_id = 'CpuRescaleDown', type='rule', resource="cpu", name='CpuRescaleDown', rule=dict({">":[{"var": "events.scale.down"},3]}), events_to_remove=3, generates="requests", action={"requests":["CpuRescaleDown"]}, amount=100)
		handler.add_doc("rules", CpuRescaleUp)
		handler.add_doc("rules", CpuRescaleDown)
		
		# MEM
		mem_exceeded_upper = dict(_id = 'mem_exceeded_upper', type='rule', resource="mem", name='mem_exceeded_upper', rule=dict({"and":[{">":[{"var": "proc.mem.resident"},{"var": "limits.mem.upper"}]},{"<":[{"var": "limits.mem.upper"},{"var": "nodes.mem.max"}]}]}), generates="events", action={"events":{"scale":{"up":1}}})
		mem_dropped_lower = dict(_id = 'mem_dropped_lower', type='rule', resource="mem", name='mem_dropped_lower', rule=dict({"and":[{"<":[{"var": "proc.mem.resident"},{"var": "limits.mem.lower"}]},{">":[{"var": "limits.mem.lower"},{"var": "nodes.mem.min"}]}]}), generates="events", action={"events":{"scale":{"down":1}}})
		handler.add_doc("rules", mem_exceeded_upper)
		handler.add_doc("rules", mem_dropped_lower)

		MemRescaleUp = dict(_id = 'MemRescaleUp', type='rule', resource="mem", name='MemRescaleUp', rule=dict({">":[{"var": "events.scale.up"},3]}), generates="requests", events_to_remove=3, action={"requests":["MemRescaleUp"]}, amount=256)
		MemRescaleDown = dict(_id = 'MemRescaleDown', type='rule', resource="mem", name='MemRescaleDown', rule=dict({">":[{"var": "events.scale.down"},3]}), generates="requests", events_to_remove=3, action={"requests":["MemRescaleDown"]}, amount=256)
		handler.add_doc("rules", MemRescaleUp)
		handler.add_doc("rules", MemRescaleDown)


	# INIT CONFIG
	if handler.database_exists("config"):
		print ("Adding 'config' document")
		config = dict(_id='config', type='config', name='config', 
			guardian_config=dict(
				WINDOW_TIMELAPSE = 10, 
				WINDOW_DELAY = 10,
				TRIGGER_WINDOW_TIME = 40)
			)
		handler.add_doc("config", config)
		
		
	## CREATE EVENTS
	#if handler.database_exists("rules"):
		#print ("Adding 'events' documents")
		#bottCPU = dict(type='event', node='node0', name='bottCPU')
		#underCPU = dict(type='event', node='node1', name='underCPU')
		#handler.add_doc("events", bottCPU)
		#handler.add_doc("events", bottCPU)
		#handler.add_doc("events", underCPU)
		#handler.add_doc("events", underCPU)
		#handler.add_doc("events", underCPU)

	# CREATE REQUESTS
	#if handler.database_exists("requests"):
		#print ("Adding 'requests' documents")
		#ScaleUpCpu = dict(type='request', node='node0', name='ScaleUpCpu')
		#ScaleDownCpu = dict(type='request', node='node1', name='ScaleDownCpu')
		#handler.add_doc("requests", ScaleUpCpu)
		#handler.add_doc("requests", ScaleDownCpu)


initialize()
