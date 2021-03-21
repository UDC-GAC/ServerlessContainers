# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils

base_container = dict(
    type='structure',
    subtype='container',
    guard_policy="serverless",
    host='host0',
    host_rescaler_ip='host0',
    host_rescaler_port='8000',
    name="base_container",
    guard=False,
    resources=dict(
        cpu=dict(max=400, min=50, guard=True),
        mem=dict(max=8192, min=1024, guard=True)
    )
)

if __name__ == "__main__":
    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()
    database = "structures"
    initializer_utils.remove_db(database)
    initializer_utils.create_db(database)

    containers = [("cont0", "host0"), ("cont1", "host0")]
    # CREATE STRUCTURES
    if handler.database_exists("structures"):
        print("Adding 'structures' documents")
        for (c, h) in containers:
            container = dict(base_container)
            container["name"] = c
            container["host"] = h
            container["host_rescaler_ip"] = h
            handler.add_structure(container)

        host = dict(type='structure',
                    subtype='host',
                    name="host0",
                    host="host0",
                    resources=dict(
                        cpu=dict(max=400, free=0,
                                 core_usage_mapping={
                                     "0": {"cont0": 100, "free": 0},
                                     "1": {"cont0": 100, "free": 0},
                                     "2": {"cont1": 100, "free": 0},
                                     "3": {"cont1": 100, "free": 0}
                                 }),
                        mem=dict(max=16384, free=0)
                    )
                )
        handler.add_structure(host)


        app = dict(
            type='structure',
            subtype='application',
            name="app1",
            guard=True,
            guard_policy="serverless",
            resources=dict(
                cpu=dict(max=400, min=100, guard=False),
                mem=dict(max=8196, min=2048, guard=False)
            ),
            containers=["cont0", "cont1"]
        )
        handler.add_structure(app)
