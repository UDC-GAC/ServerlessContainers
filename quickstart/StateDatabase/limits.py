# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils

containers = ["cont0", "cont1"]
applications = ["app1"]

base_limits = dict(
        type='limit',
        name="base_container",
        resources=dict(
            cpu=dict(upper=100, lower=50, boundary=25),
            mem=dict(upper=2048, lower=512, boundary=256)
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
                cpu=dict(upper=200, lower=100, boundary=50)
            )
        )
        handler.add_limit(limits)
