# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.initializers.initializer_utils as couchdb_utils


base_container = dict(
    type='structure',
    subtype='container',
    guard_policy="serverless",
    host='es-udc-dec-jonatan-dante',
    host_rescaler_ip='dante',
    host_rescaler_port='8000',
    name="base_container",
    guard=True,
    resources=dict(
        cpu=dict(max=200, min=50, fixed=150, guard=True),
        mem=dict(max=8192, min=1024, fixed=6144, guard=True),
        disk=dict(max=100, min=20, guard=False),
        net=dict(max=200, min=100, guard=False),
        energy=dict(max=20, min=0, guard=False)
    )
)

if __name__ == "__main__":
    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()
    database = "structures"
    initializer_utils.remove_db(database)
    initializer_utils.create_db(database)

    containers = ["node0", "node1", "node2", "node3"]
    hosts = ["es-udc-dec-jonatan-dante"]

    # CREATE STRUCTURES
    if handler.database_exists("structures"):
        print("Adding 'structures' documents")
        for c in containers:
            container = dict(
                type='structure',
                subtype='container',
                guard_policy="serverless",
                host='es-udc-dec-jonatan-dante',
                host_rescaler_ip='dante',
                host_rescaler_port='8000',
                name=c,
                guard=True,
                resources=dict(
                    cpu=dict(max=200, min=50, fixed=150, guard=True),
                    mem=dict(max=8192, min=1024, fixed=6144, guard=True),
                    disk=dict(max=100, min=20, guard=False),
                    net=dict(max=200, min=100, guard=False),
                    energy=dict(max=20, min=0, guard=False)
                )
            )
            handler.add_structure(container)

        for h in hosts:
            host = dict(
                type='structure',
                subtype='host',
                name=h,
                host=h,
                resources=dict(
                    cpu=dict(max=800),
                    mem=dict(max=32768)
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
                cpu=dict(max=800, min=400, guard=False),
                mem=dict(max=32768, min=16384, guard=False),
                disk=dict(max=600, min=120, guard=False),
                net=dict(max=1200, min=600, guard=False),
                energy=dict(max=120, min=0, guard=True)
            ),
            containers=["node0", "node1", "node2", "node3"]
        )
        handler.add_structure(app)
