# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils

containers = ["node0", "node1", "node2", "node3", "node4", "node5", "node6", "node7"]
applications = ["app1"]

base_limits = dict(
        type='limit',
        name="base_container",
        resources=dict(
            cpu=dict(),
            mem=dict(),
            disk=dict(),
            net=dict(),
            energy=dict()
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
                cpu=dict(),
                mem=dict(),
                disk=dict(),
                net=dict(),
                energy=dict()
            )
        )
        handler.add_limit(limits)
