# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils

containers = ["node0", "node1", "node2", "node3",
              "node4", "node5", "node6", "node7",
              "node8", "node9", "node10", "node11",
              "node12", "node13", "node14", "node15",
              "node16", "node17", "node18", "node19",
              "node20", "node21", "node22", "node23",
              "node24", "node25", "node26", "node27",
              "node28", "node29", "node30", "node31"]
applications = ["app1"]

base_limits = dict(
    type='limit',
    name="base_container",
    resources=dict(
        cpu=dict(upper=500, lower=400, boundary=75),
        mem=dict(upper=44000, lower=40000, boundary=3072),
        disk=dict(upper=100, lower=20, boundary=10),
        net=dict(upper=100, lower=20, boundary=10),
        energy=dict(upper=15, lower=5, boundary=3)
    )
)

if __name__ == "__main__":

    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()
    database = "limits"
    initializer_utils.remove_db(database)
    initializer_utils.create_db(database)

    if handler.database_exists("limits"):
        print("Adding 'limits' documents")
        for c in containers:
            limits = dict(base_limits)
            limits["name"] = c
            handler.add_limit(limits)

        limits = dict(
            type='limit',
            name='app1',
            resources=dict(
                cpu=dict(upper=9600, lower=150, boundary=50),
                mem=dict(upper=700280, lower=2000, boundary=4000),
                disk=dict(upper=100, lower=10, boundary=20),
                net=dict(upper=100, lower=10, boundary=20),
                energy=dict(upper=50, lower=5, boundary=5)
            )
        )
        handler.add_limit(limits)
