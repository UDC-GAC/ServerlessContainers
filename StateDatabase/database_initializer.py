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
				memory=dict(upper=1024,lower=512), 
				disk=dict(upper=100,lower=100), 
				network=dict(upper=100,lower=100)
			)
		)
		node1 = dict(
			#_id = 'node1', 
			type='limit', 
			node='node1', 
			resources=dict(
				cpu=dict(upper=300,lower=100), 
				memory=dict(upper=2048,lower=1024),
				disk=dict(upper=100,lower=100),
				network=dict(upper=100,lower=100)
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
				memory=dict(max=4096,current=1024,min=512), 
				disk=dict(max=100,current=100,min=100), 
				network=dict(max=100,current=100,min=100)
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
		#exceeded_upper = dict(_id = 'exceeded_upper', type='rule', name='exceeded_upper', rule=dict({"and":[{">":[{"var": "proc.cpu.user"},{"var": "limits.cpu.upper"}]},{"<":[{"var": "limits.cpu.upper"},{"var": "nodes.cpu.max"}]}]}), generates="events", action={"events":["bottCPU"]})
		#dropped_lower = dict(_id = 'dropped_lower', type='rule', name='dropped_lower', rule=dict({"and":[{"<":[{"var": "proc.cpu.user"},{"var": "limits.cpu.lower"}]},{">":[{"var": "limits.cpu.lower"},{"var": "nodes.cpu.min"}]}]}), generates="events", action={"events":["underCPU"]})
		exceeded_upper = dict(_id = 'exceeded_upper', type='rule', name='exceeded_upper', rule=dict({"and":[{">":[{"var": "proc.cpu.user"},{"var": "limits.cpu.upper"}]},{"<":[{"var": "limits.cpu.upper"},{"var": "nodes.cpu.max"}]}]}), generates="events", action={"events":{"scale":{"up":1}}})
		dropped_lower = dict(_id = 'dropped_lower', type='rule', name='dropped_lower', rule=dict({"and":[{"<":[{"var": "proc.cpu.user"},{"var": "limits.cpu.lower"}]},{">":[{"var": "limits.cpu.lower"},{"var": "nodes.cpu.min"}]}]}), generates="events", action={"events":{"scale":{"down":1}}})
		handler.add_doc("rules", exceeded_upper)
		handler.add_doc("rules", dropped_lower)

		rescaleUP = dict(_id = 'rescaleUP', type='rule', name='rescaleUP', rule=dict({">":[{"var": "events.scale.up"},3]}), generates="requests", action={"requests":["rescaleUP"]})
		rescaleDOWN = dict(_id = 'rescaleDOWN', type='rule', name='rescaleDOWN', rule=dict({">":[{"var": "events.scale.down"},3]}), generates="requests", action={"requests":["rescaleDOWN"]})
		handler.add_doc("rules", rescaleUP)
		handler.add_doc("rules", rescaleDOWN)


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
	if handler.database_exists("requests"):
		print ("Adding 'requests' documents")
		ScaleUpCpu = dict(type='request', node='node0', name='ScaleUpCpu')
		ScaleDownCpu = dict(type='request', node='node1', name='ScaleDownCpu')
		handler.add_doc("requests", ScaleUpCpu)
		handler.add_doc("requests", ScaleDownCpu)


initialize()
