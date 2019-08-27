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
        aux_user0 = dict(
            type='structure',
            subtype='application',
            name="aux_user0",
            guard=False,
            guard_policy="serverless",
            resources=dict(
                cpu=dict(max=1400, min=200, guard=False),
                mem=dict(max=46080, min=4096, guard=False),
                disk=dict(max=100, min=20, guard=False),
                net=dict(max=100, min=50, guard=False),
                energy=dict(max=120, min=0, shares=10, guard=True)
            ),
            containers=["aux0", "aux1"]
        )
        handler.add_structure(aux_user0)

        pre_user0 = dict(
            type='structure',
            subtype='application',
            name="pre_user0",
            guard=False,
            guard_policy="serverless",
            resources=dict(
                cpu=dict(max=1800, min=300, guard=False),
                mem=dict(max=138240, min=12288, guard=False),
                disk=dict(max=300, min=100, guard=False),
                net=dict(max=300, min=100, guard=False),
                energy=dict(max=120, min=0, shares=10, guard=True)
            ),
            containers=["pre0", "pre1", "pre2", "pre3"]
        )
        handler.add_structure(pre_user0)

        comp_user0 = dict(
            type='structure',
            subtype='application',
            name="comp_user0",
            guard=False,
            guard_policy="serverless",
            resources=dict(
                cpu=dict(max=1800, min=300, guard=False),
                mem=dict(max=138240, min=12288, guard=False),
                disk=dict(max=300, min=100, guard=False),
                net=dict(max=300, min=100, guard=False),
                energy=dict(max=120, min=0, shares=10, guard=True)
            ),
            containers=["comp0", "comp1", "comp2", "comp3", "comp4", "comp5", "comp6", "comp7", "comp8", "comp9"]
        )
        handler.add_structure(comp_user0)


if __name__ == "__main__":
    initializer_utils = couchdb_utils.CouchDBUtils()
    handler = couchDB.CouchDBServer()
    add_multiple_services_as_applications(handler)
