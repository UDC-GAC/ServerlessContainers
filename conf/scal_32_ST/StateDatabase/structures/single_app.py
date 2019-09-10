# /usr/bin/python
import src.StateDatabase.couchdb as couchDB
import src.StateDatabase.utils as couchdb_utils


def add_single_application(handler):
    if handler.database_exists("structures"):
        print("Removing any previous 'structure application' documents")
        apps = handler.get_structures("application")
        for app in apps:
            handler.delete_structure(app)

        print("Adding 'structure application' documents")
        fixwindow_user0 = dict(
            type='structure',
            subtype='application',
            name="fixwindow_user0",
            guard=False,
            guard_policy="serverless",
            resources=dict(
                cpu=dict(max=4900, min=1400, guard=False),
                mem=dict(max=46080, min=4096, guard=False),
                disk=dict(max=100, min=20, guard=False),
                net=dict(max=100, min=50, guard=False),
                energy=dict(max=120, min=0, shares=10, guard=False)
            ),
            containers=[
                "kafka0", "kafka1", "kafka2", "kafka3", "kafka4", "kafka5", "kafka6", "kafka7",
                "hibench0", "hibench1", "hibench2", "hibench3",
                "slave0", "slave1", "slave2", "slave3", "slave4", "slave5", "slave6", "slave7", "slave8", "slave9",
                "slave10", "slave11", "slave12", "slave13", "slave14", "slave15", "slave16", "slave17", "slave18",
                "slave19"
            ]
        )
        handler.add_structure(fixwindow_user0)


if __name__ == "__main__":
    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()
    add_single_application(handler)
