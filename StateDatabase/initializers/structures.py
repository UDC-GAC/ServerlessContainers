# /usr/bin/python
import StateDatabase.couchDB as couchDB
import StateDatabase.initializers.initializer_utils as CouchDB_Utils

initializer_utils = CouchDB_Utils.CouchDB_Utils()
handler = couchDB.CouchDBServer()
database = "structures"
initializer_utils.remove_db(database)
initializer_utils.create_db(database)

containers = ["node0", "node1", "node2", "node3", "node4", "node5"]
hosts = ["c14-13"]

# CREATE STRUCTURES
if handler.database_exists("structures"):
    print ("Adding 'structures' documents")
    for c in containers:
        container = dict(
            type='structure',
            subtype='container',
            guard_policy="serverless",
            host='c14-13',
            name=c,
            guard=True,
            resources=dict(
                cpu=dict(max=300, min=30, fixed=50, guard=True),
                mem=dict(max=8192, min=1024, fixed=2048, guard=True),
                disk=dict(max=100, min=10, guard=False),
                net=dict(max=100, min=10, guard=False),
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
                mem=dict(max=46000)
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
            cpu=dict(max=1800, min=300, guard=False),
            mem=dict(max=49176, min=12288, guard=False),
            disk=dict(max=600, min=60, guard=False),
            net=dict(max=600, min=60, guard=False),
            energy=dict(max=120, min=0, guard=True)
        ),
        containers=["node0","node1","node2","node3","node4","node5"]
    )
    handler.add_structure(app)

