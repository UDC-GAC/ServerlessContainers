# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils

# DEPRECATED

base_container = dict(
    type='structure',
    subtype='container',
    name="base_container",
    guard=False,
    resources=dict(
        cpu=dict(guard=False),
        mem=dict(guard=False),
        disk=dict(guard=False),
        net=dict(guard=False),
        energy=dict(guard=False)
    )
)

base_host = dict(
    type='structure',
    subtype='host',
    name="host0",
    host="host0",
    resources=dict(
        cpu=dict(max=800),
        mem=dict(max=8192)
    )
)

if __name__ == "__main__":
    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()
    database = "structures"
    initializer_utils.remove_db(database)
    initializer_utils.create_db(database)

    hosts = list()
    containers = list()

    host = "host0"
    hosts.append(host)
    containers.append(("node0", host))
    containers.append(("node1", host))
    containers.append(("node2", host))
    containers.append(("node3", host))

    host = "host1"
    hosts.append(host)
    containers.append(("node4", host))
    containers.append(("node5", host))
    containers.append(("node6", host))
    containers.append(("node7", host))


    # CREATE STRUCTURES
    if handler.database_exists("structures"):
        print("Adding 'structures' documents")
        for (c, h) in containers:
            container = dict(base_container)
            container["name"] = c
            container["host"] = h
            container["host_rescaler_ip"] = h
            container["host_rescaler_port"] = "8000"
            handler.add_structure(container)

        for h in hosts:
            host = dict(base_host)
            host["name"] = h
            host["host"] = h
            handler.add_structure(host)

        app = dict(
            type='structure',
            subtype='application',
            name="app1",
            guard=True,
            guard_policy="serverless",
            resources=dict(
                cpu=dict(guard=False),
                mem=dict(guard=False),
                disk=dict(guard=False),
                net=dict(guard=False),
                energy=dict(guard=False)
            ),
            containers=["node0", "node1", "node2", "node3",
                        "node4", "node5", "node6", "node7"]
        )
        handler.add_structure(app)
