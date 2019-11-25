# /usr/bin/python
import src.StateDatabase.couchdb as couchDB

if __name__ == "__main__":
    handler = couchDB.CouchDBServer()

    host0 = handler.get_structure("host0")
    host0["resources"] = {
        "mem": {
            "max": 32768,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"node0": 100, "free": 0},
                "1": {"node0": 100, "free": 0},
                "2": {"node1": 100, "free": 0},
                "3": {"node1": 100, "free": 0},
                "4": {"node2": 100, "free": 0},
                "5": {"node2": 100, "free": 0},
                "6": {"node3": 100, "free": 0},
                "7": {"node3": 100, "free": 0}
            },
            "max": 800,
            "free": 0
        }
    }
    handler.update_structure(host0)



