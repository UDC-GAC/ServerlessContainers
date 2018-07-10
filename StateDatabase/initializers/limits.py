# /usr/bin/python
import StateDatabase.couchDB as couchDB
import StateDatabase.initializers.initializer_utils as CouchDB_Utils

initializer_utils = CouchDB_Utils.CouchDB_Utils()
handler = couchDB.CouchDBServer()
database = "limits"
initializer_utils.remove_db(database)
initializer_utils.create_db(database)

containers = ["node0", "node1", "node2", "node3"]
hosts = ["es-udc-dec-jonatan-dante"]
applications = ["app1"]
# CREATE LIMITS
if handler.database_exists("limits"):
    print ("Adding 'limits' documents")
    for c in containers:
        container = dict(
            type='limit',
            name=c,
            resources=dict(
                cpu=dict(upper=170, lower=150, boundary=35),
                mem=dict(upper=8000, lower=6000, boundary=1024),
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


