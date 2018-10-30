# /usr/bin/python
import StateDatabase.couchDB as couchDB

if __name__ == "__main__":
    handler = couchDB.CouchDBServer()
    dante = handler.get_structure("c14-13")
    dante["resources"] = {
        "mem": {
            "max": 61440,
            "free": 0
        },
        "cpu": {
            "core_usage_mapping": {
                "0": {
                    "node0": 100,
                    "free": 0
                },
                "1": {
                    "node0": 100,
                    "free": 0
                },
                "2": {
                    "node1": 100,
                    "free": 0
                },
                "3": {
                    "node1": 100,
                    "free": 0
                },
                "4": {
                    "node2": 100,
                    "free": 0
                },
                "5": {
                    "node2": 100,
                    "free": 0
                },
                "6": {
                    "node3": 100,
                    "free": 0
                },
                "7": {
                    "node3": 100,
                    "free": 0
                },
                "8": {
                    "node4": 100,
                    "free": 0
                },
                "9": {
                    "node4": 100,
                    "free": 0
                },
                "10": {
                    "node5": 100,
                    "free": 0
                },
                "11": {
                    "node5": 100,
                    "free": 0
                }
            },
            "max": 1200,
            "free": 0
        }
    }
    handler.update_structure(dante)


