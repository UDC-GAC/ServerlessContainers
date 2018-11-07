# /usr/bin/python
import StateDatabase.couchdb as couchDB
import StateDatabase.initializers.initializer_utils as couchdb_utils

containers = ["node0", "node1", "node2", "node3", "node4", "node5"]
hosts = ["c14-13"]
applications = ["app1"]

base_limits = dict(
        type='limit',
        name="base_container",
        resources=dict(
            cpu=dict(upper=170, lower=150, boundary=25),
            mem=dict(upper=8000, lower=6000, boundary=2048),
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
            container = dict(
                type='limit',
                name=c,
                resources=dict(
                    cpu=dict(upper=170, lower=150, boundary=25),
                    mem=dict(upper=8000, lower=6000, boundary=2048),
                    disk=dict(upper=100, lower=20, boundary=10),
                    net=dict(upper=100, lower=20, boundary=10),
                    energy=dict(upper=15, lower=5, boundary=3)
                )
            )
            handler.add_limit(container)

        application = dict(
            type='limit',
            name='app1',
            resources=dict(
                cpu=dict(upper=200, lower=150, boundary=50),
                mem=dict(upper=14000, lower=2000, boundary=4000),
                disk=dict(upper=100, lower=10, boundary=20),
                net=dict(upper=100, lower=10, boundary=20),
                energy=dict(upper=50, lower=5, boundary=5)
            )
        )
        handler.add_limit(application)
