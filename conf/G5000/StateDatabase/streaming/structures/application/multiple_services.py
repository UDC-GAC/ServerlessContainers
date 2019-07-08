# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils


def add_multiple_services_as_applications(handler):
    if handler.database_exists("structures"):
        print("Removing any previous 'structure application' documents")
        apps = handler.get_structures("application")
        for app in apps:
            handler.delete_structure(app)

        print("Adding 'structure application' documents")
        kafkas_user0 = dict(
            type='structure',
            subtype='application',
            name="kafkas_user0",
            guard=True,
            guard_policy="serverless",
            resources=dict(
                cpu=dict(max=1200, min=200, guard=False),
                mem=dict(max=92160, min=8192, guard=False),
                disk=dict(max=200, min=100, guard=False),
                net=dict(max=200, min=100, guard=False),
                energy=dict(max=120, min=0, shares=10, guard=True)
            ),
            containers=["kafka0", "kafka1"]
        )
        handler.add_structure(kafkas_user0)

        kafkas_user1 = dict(
            type='structure',
            subtype='application',
            name="kafkas_user1",
            guard=True,
            guard_policy="serverless",
            resources=dict(
                cpu=dict(max=1200, min=200, guard=False),
                mem=dict(max=92160, min=8192, guard=False),
                disk=dict(max=200, min=100, guard=False),
                net=dict(max=200, min=100, guard=False),
                energy=dict(max=120, min=0, shares=10, guard=True)
            ),
            containers=["kafka2", "kafka3"]
        )
        handler.add_structure(kafkas_user1)

        hibenches_user0 = dict(
            type='structure',
            subtype='application',
            name="hibenches_user0",
            guard=True,
            guard_policy="serverless",
            resources=dict(
                cpu=dict(max=600, min=100, guard=False),
                mem=dict(max=46080, min=4096, guard=False),
                disk=dict(max=100, min=20, guard=False),
                net=dict(max=100, min=50, guard=False),
                energy=dict(max=120, min=0, shares=10, guard=True)
            ),
            containers=["hibench0"]
        )
        handler.add_structure(hibenches_user0)

        hibenches_user1 = dict(
            type='structure',
            subtype='application',
            name="hibenches_user1",
            guard=True,
            guard_policy="serverless",
            resources=dict(
                cpu=dict(max=600, min=100, guard=False),
                mem=dict(max=46080, min=4096, guard=False),
                disk=dict(max=100, min=20, guard=False),
                net=dict(max=100, min=50, guard=False),
                energy=dict(max=120, min=0, shares=10, guard=True)
            ),
            containers=["hibench1"]
        )
        handler.add_structure(hibenches_user1)

        spark_user0 = dict(
            type='structure',
            subtype='application',
            name="spark_user0",
            guard=True,
            guard_policy="serverless",
            resources=dict(
                cpu=dict(max=3000, min=500, guard=False),
                mem=dict(max=230400, min=20480, guard=False),
                disk=dict(max=500, min=100, guard=False),
                net=dict(max=500, min=100, guard=False),
                energy=dict(max=120, min=0, shares=10, guard=True)
            ),
            containers=["slave0", "slave1", "slave2", "slave3", "slave4"]
        )
        handler.add_structure(spark_user0)

        spark_user1 = dict(
            type='structure',
            subtype='application',
            name="spark_user1",
            guard=True,
            guard_policy="serverless",
            resources=dict(
                cpu=dict(max=3000, min=500, guard=False),
                mem=dict(max=230400, min=20480, guard=False),
                disk=dict(max=500, min=100, guard=False),
                net=dict(max=500, min=100, guard=False),
                energy=dict(max=120, min=0, shares=10, guard=True)
            ),
            containers=["slave5", "slave6", "slave7", "slave8", "slave9"]
        )
        handler.add_structure(spark_user1)


if __name__ == "__main__":
    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()
    add_multiple_services_as_applications(handler)
