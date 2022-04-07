# /usr/bin/python
import src.StateDatabase.couchdb as couchDB

if __name__ == "__main__":
    handler = couchDB.CouchDBServer()

    host0 = handler.get_structure("host0")
    host0["resources"] = {
        "mem": {
            "max": 8192,
            "free": 8192
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"free": 100},
                "1": {"free": 100},
                "2": {"free": 100},
                "3": {"free": 100},
                "4": {"free": 100},
                "5": {"free": 100},
                "6": {"free": 100},
                "7": {"free": 100}
            },
            "max": 800,
            "free": 800
        }
    }
    handler.update_structure(host0)

    host1 = handler.get_structure("host1")
    host1["resources"] = {
        "mem": {
            "max": 8192,
            "free": 8192
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {"free": 100},
                "1": {"free": 100},
                "2": {"free": 100},
                "3": {"free": 100},
                "4": {"free": 100},
                "5": {"free": 100},
                "6": {"free": 100},
                "7": {"free": 100}
            },
            "max": 800,
            "free": 800
        }
    }
    handler.update_structure(host1)


