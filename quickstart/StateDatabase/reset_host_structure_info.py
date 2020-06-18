# /usr/bin/python
import src.StateDatabase.couchdb as couchDB

if __name__ == "__main__":
    handler = couchDB.CouchDBServer()

    host0 = handler.get_structure("host0")
    host0["resources"] = {
        "mem": {
            "max": 400,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"cont0": 100, "free": 0},
                "1": {"cont0": 100, "free": 0},
                "2": {"cont1": 100, "free": 0},
                "3": {"cont1": 100, "free": 0}
            },
            "max": 400,
            "free": 0
        }
    }
    handler.update_structure(host0)